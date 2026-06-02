"""Engine orchestration: signals → rules → narration → card.

Transforms raw campaign metric payloads into structured decisions with
optional LLM-generated narrative explanations. The pipeline is:

    CampaignMetrics → sanitize → evaluate → decide → narrate → EngineResult

The narration layer is intentionally optional and isolated behind a
circuit breaker so that any LLM infrastructure failure degrades
gracefully to deterministic template output rather than crashing the
engine. Semantic validation runs *inside* the circuit breaker scope so
that contract violations are never mis-attributed as infrastructure
faults.
"""

from __future__ import annotations

import functools
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, TypeVar

from drip.engine.rules import Decision, decide
from drip.engine.signals import CampaignMetrics, SignalVector, Thresholds, evaluate

if TYPE_CHECKING:
    from drip.engine.rules import Action

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])  # fix: 'bindable=' is not a valid TypeVar kwarg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt constant — defined at the top so every reader sees it before the
# classes that reference it.
# ---------------------------------------------------------------------------

_NARRATE_SYSTEM = (
    "You are a concise campaign analysis assistant. "
    "You will receive serialized signal matrices and a deterministic decision. "
    "Write exactly two sentences explaining the operational reason behind the decision. "
    "Use only the numbers present in the input. "
    "Never contradict or invert the stated action."
)


# ===========================================================================
# 1. DATA CONTRACTS
# ===========================================================================

@dataclass(frozen=True, slots=True)
class NarrationFlags:
    """Typed record of narration-layer telemetry.

    Using a proper dataclass instead of Dict[str, Any] makes typos a
    compile-time error and keeps IDE auto-complete working.
    """
    circuit_state: str
    contract_verified: bool
    fallback_triggered: bool
    fallback_reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class TelemetryMetadata:
    """Immutable execution telemetry attached to every EngineResult."""
    execution_ms: float
    input_sanitized: bool
    circuit_state: str
    contract_verified: bool
    fallback_triggered: bool
    fallback_reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class EngineResult:
    """Immutable product of one full engine pipeline run."""
    metrics: CampaignMetrics
    signals: SignalVector
    decision: Decision
    why: str
    telemetry: TelemetryMetadata


# ===========================================================================
# 2. EXCEPTIONS — ordered from base to specific
# ===========================================================================

class EngineError(Exception):
    """Base for all engine-level failures."""


class InputSanitizationError(EngineError):
    """Metric payload violates domain boundaries (e.g. negative CPP)."""


class SemanticContractViolation(EngineError):
    """LLM output contradicts the deterministic decision or injects fabricated metrics."""


# ===========================================================================
# 3. INPUT SANITIZATION DECORATOR
# ===========================================================================

def sanitize_inputs(func: Callable[..., Any]) -> Callable[..., Any]:
    """Pre-flight guard that normalises raw CampaignMetrics before pipeline entry.

    Handles IEEE-754 edge cases (NaN, ±Inf), clamps values to domain
    boundaries, and reconstructs an immutable sanitized copy so downstream
    code never touches the original object.

    The decorator extracts the metrics argument by *name* ('m') to avoid
    brittle positional-index assumptions that break when callers use keyword
    arguments.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Prefer keyword arg; fall back to positional slot 1 (self=0, m=1).
        raw: CampaignMetrics = kwargs.get("m") or (args[1] if len(args) > 1 else None)
        if raw is None:
            raise TypeError("sanitize_inputs: could not locate 'CampaignMetrics' argument.")

        def _clamp(
            val: Any,
            default: float = 0.0,
            min_val: float = 0.0,
            max_val: float = float("inf"),
        ) -> float:
            try:
                fv = float(val)
            except (ValueError, TypeError):
                return default
            if not math.isfinite(fv):
                return default
            return max(min_val, min(max_val, fv))

        sanitized = CampaignMetrics(
            cpp=_clamp(raw.cpp),
            cpp_target=_clamp(raw.cpp_target, default=0.01, min_val=0.01),
            roas=_clamp(raw.roas),
            roas_target=_clamp(raw.roas_target, default=0.01, min_val=0.01),
            cvr=_clamp(raw.cvr, max_val=1.0),
            cvr_baseline=_clamp(raw.cvr_baseline, default=0.01, min_val=0.01, max_val=1.0),
            daily_spend=_clamp(raw.daily_spend),
            budget_cap=_clamp(raw.budget_cap),
            purchases=max(0, int(raw.purchases or 0)),
            ctr=_clamp(raw.ctr, max_val=1.0),
            ctr_baseline=_clamp(raw.ctr_baseline, default=0.01, min_val=0.01, max_val=1.0),
            frequency=_clamp(raw.frequency, default=1.0, min_val=1.0, max_val=50.0),
            label=str(raw.label).strip() if raw.label else "UNLABELED_CAMPAIGN",
        )

        # Propagate the sanitized object via whatever path the caller used.
        if "m" in kwargs:
            kwargs["m"] = sanitized
        else:
            args = list(args)
            args[1] = sanitized

        return func(*args, **kwargs)

    return wrapper


# ===========================================================================
# 4. CIRCUIT BREAKER
# ===========================================================================

class CircuitBreaker:
    """Thread-safe circuit breaker for the external LLM API.

    States
    ------
    CLOSED   — normal operation; failures are counted.
    OPEN     — too many failures; calls are rejected immediately.
    HALF_OPEN — one trial call is allowed to test recovery.

    Only *infrastructure* exceptions (network errors, timeouts, empty
    responses) should be passed through here.  Domain-level failures like
    SemanticContractViolation must be filtered out by the caller so they
    do not accidentally trip the breaker.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_sec: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec

        self._failure_count: int = 0
        self._last_failure_at: float = 0.0
        self._state: str = "CLOSED"
        self._lock = threading.Lock()

    # -- public read-only property ------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    # -- decorator interface ---------------------------------------------------

    def __call__(self, func: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            self._maybe_transition_to_half_open()
            self._guard_open_state()

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                self._record_failure(exc)
                raise

            self._record_success()
            return result

        return wrapper

    # -- private helpers ------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        with self._lock:
            if (
                self._state == "OPEN"
                and time.monotonic() - self._last_failure_at > self.recovery_timeout_sec
            ):
                self._state = "HALF_OPEN"
                logger.info("CircuitBreaker → HALF_OPEN (probe allowed)")

    def _guard_open_state(self) -> None:
        with self._lock:
            if self._state == "OPEN":
                ttl = self.recovery_timeout_sec - (time.monotonic() - self._last_failure_at)
                raise RuntimeError(
                    f"CircuitBreaker OPEN — LLM bypassed. Retry in {ttl:.1f}s."
                )

    def _record_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_at = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logger.critical(
                    "CircuitBreaker → OPEN after %d failures. Last error: %s",
                    self._failure_count,
                    exc,
                )

    def _record_success(self) -> None:
        with self._lock:
            if self._state == "HALF_OPEN":
                logger.info("CircuitBreaker → CLOSED (probe succeeded)")
            self._state = "CLOSED"
            self._failure_count = 0


# ===========================================================================
# 5. SEMANTIC CONTRACT GUARD
# ===========================================================================

def enforce_semantic_contract(func: Callable[..., str]) -> Callable[..., str]:
    """Validate LLM output for logical coherence before returning it.

    Checks performed
    ----------------
    1. Negation scan — the narrative must not instruct the reader to
       reverse the engine's decision.
    2. Direction contradiction — e.g. "keep running" when action is PAUSE.
    3. Fabricated metric guard — numbers co-located with metric keywords
       that don't appear in the actual metrics are rejected.

    The numeric guard uses a 5 % relative tolerance to survive float-to-
    string rounding differences (e.g. 1.2345 serialised as "1.23").

    NOTE: This decorator must run *inside* the CircuitBreaker scope so that
    SemanticContractViolation never increments the infrastructure failure
    counter.  Arrange decorators accordingly:

        @circuit_breaker     # outer — catches SemanticContractViolation too?
        @enforce_semantic_contract  # inner — runs on raw LLM output

    Because Python applies decorators bottom-up, the order above means
    enforce_semantic_contract is inner and circuit_breaker is outer —
    which is wrong for our goal.  The caller in ResilientNarrationMixin
    applies the contract check *after* the LLM call returns inside a
    try/except that explicitly excludes SemanticContractViolation from
    the circuit breaker's error accounting.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        # Extract typed arguments by name so the decorator is position-agnostic.
        decision: Decision = kwargs.get("decision") or (args[2] if len(args) > 2 else None)
        metrics: CampaignMetrics = kwargs.get("m") or (args[3] if len(args) > 3 else None)

        narrative = func(*args, **kwargs)
        _validate_narrative(narrative, decision, metrics)
        return narrative

    return wrapper


def _validate_narrative(
    narrative: str, decision: Decision, metrics: CampaignMetrics
) -> None:
    """Pure validation logic, separated from the decorator for testability."""
    action = decision.action.value.lower()
    body = narrative.lower()

    # 1. Negation scan
    negation_patterns = [
        f"don't {action}", f"do not {action}", f"not {action}",
        f"never {action}", f"instead of {action}",
        "override decision", "ignore the engine",
    ]
    for pattern in negation_patterns:
        if pattern in body:
            raise SemanticContractViolation(
                f"Narrative inverts the engine decision '{action}': pattern '{pattern}' found."
            )

    # 2. Direction contradiction for PAUSE decisions specifically
    if action == "pause" and any(
        phrase in body for phrase in ("keep running", "scale up", "maintain status")
    ):
        raise SemanticContractViolation(
            "Narrative contradicts PAUSE decision (contains affirmative continuation phrase)."
        )

    # 3. Fabricated metric guard
    #    Only trigger when the narrative names a metric keyword AND contains a
    #    number that doesn't map (within tolerance) to any actual metric value.
    metric_keywords = ("roas", "cpp", "spend", "cvr", "ctr", "frequency")
    actual_values = [
        metrics.cpp, metrics.roas, metrics.daily_spend,
        metrics.cvr, metrics.ctr, metrics.frequency,
    ]

    if any(kw in body for kw in metric_keywords):
        found_numbers = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", body)]
        for num in found_numbers:
            if num <= 1.0:
                # Ratios and small coefficients are fine — skip
                continue
            is_known = any(
                math.isclose(num, actual, rel_tol=0.05)
                for actual in actual_values
                if actual > 0
            )
            if not is_known:
                raise SemanticContractViolation(
                    f"Narrative contains metric keyword with unrecognised value {num} "
                    f"(actual metrics: {actual_values})."
                )


# ===========================================================================
# 6. PROMPT SERIALISATION
# ===========================================================================

def _build_prompt(sv: SignalVector, decision: Decision, m: CampaignMetrics) -> str:
    """Serialise domain state into a compact, token-efficient LLM prompt.

    Using a module-level function instead of a static-method-only class
    avoids the antipattern of creating a class purely as a namespace.
    """
    signal_lines = "\n".join(
        f"  {s.name}: status={s.status.value} value={s.value_str} target={s.target_str}"
        for s in sv.signals
    )
    rule_summary = "; ".join(r.message for r in decision.reasons)
    return (
        f"Campaign: {m.label}\n"
        f"Signals:\n{signal_lines}\n"
        f"Decision: {decision.headline} (action={decision.action.value})\n"
        f"Rules: {rule_summary}"
    )


# ===========================================================================
# 7. RESILIENT NARRATION MIXIN
# ===========================================================================

class ResilientNarrationMixin:
    """Adds LLM narration with multi-tier fallback to any engine class.

    Instance-level circuit breaker
    --------------------------------
    The original code placed the circuit breaker at class level, meaning
    ALL instances shared a single breaker.  A busy staging environment
    tripping the breaker would silently degrade production instances.
    Moving it to __init__ gives each engine its own isolated breaker.

    Semantic contract vs infrastructure failures
    --------------------------------------------
    SemanticContractViolation is explicitly excluded from the circuit
    breaker's failure accounting because it reflects LLM output quality,
    not infrastructure health.  Only RuntimeError and other unexpected
    exceptions increment the failure counter.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Instance-level breaker — not shared across engine instances.
        self._llm_breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=15.0)

    # -------------------------------------------------------------------------

    def _call_llm(
        self,
        sv: SignalVector,
        decision: Decision,
        m: CampaignMetrics,
        model: str,
    ) -> str:
        """Raw LLM call, undecorated, so error routing stays explicit."""
        from drip.llm import chat  # local import keeps module loadable without drip installed

        prompt = _build_prompt(sv, decision, m)
        response = chat(
            model=model,
            system=_NARRATE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        text = getattr(response, "text", "").strip()
        if not text:
            raise RuntimeError("Empty response received from LLM.")
        return text

    # -------------------------------------------------------------------------

    def generate_narration(
        self,
        sv: SignalVector,
        decision: Decision,
        m: CampaignMetrics,
        model: Optional[str] = None,
    ) -> Tuple[str, NarrationFlags]:
        """Run narration with circuit-breaker protection and deterministic fallback.

        Returns
        -------
        (narrative_text, NarrationFlags)
        """
        # Fast path: no model configured → skip LLM entirely.
        if not model:
            return _fallback_narrative(sv, decision), NarrationFlags(
                circuit_state="CLOSED",
                contract_verified=False,
                fallback_triggered=True,
                fallback_reason="no_model_configured",
            )

        # Tier 1: attempt LLM narration with circuit breaker protection.
        try:
            # Circuit breaker wraps the raw network call only.
            @self._llm_breaker
            def _protected_call() -> str:
                return self._call_llm(sv, decision, m, model)

            raw_narrative = _protected_call()

            # Semantic validation runs AFTER the LLM call, OUTSIDE the
            # circuit breaker, so contract violations don't count as infra
            # failures.
            _validate_narrative(raw_narrative, decision, m)

            return raw_narrative, NarrationFlags(
                circuit_state=self._llm_breaker.state,
                contract_verified=True,
                fallback_triggered=False,
            )

        except SemanticContractViolation as exc:
            # Contract violation — LLM infra is healthy, output was bad.
            logger.warning("Semantic contract violated; falling back. %s", exc)
            return _fallback_narrative(sv, decision), NarrationFlags(
                circuit_state=self._llm_breaker.state,
                contract_verified=False,
                fallback_triggered=True,
                fallback_reason="semantic_contract_violation",
            )

        except Exception as exc:
            # Infrastructure failure — circuit breaker already incremented.
            logger.warning("LLM call failed; falling back. %s", exc)
            return _fallback_narrative(sv, decision), NarrationFlags(
                circuit_state=self._llm_breaker.state,
                contract_verified=False,
                fallback_triggered=True,
                fallback_reason=type(exc).__name__,
            )


# ===========================================================================
# 8. DECISION ENGINE
# ===========================================================================

class DecisionEngine(ResilientNarrationMixin):
    """Top-level pipeline: raw metrics → EngineResult.

    Usage
    -----
    >>> engine = DecisionEngine(narrate_model="claude-3-5-haiku-20241022")
    >>> result = engine.run(metrics)
    >>> print(result.why)
    """

    def __init__(
        self,
        thresholds: Optional[Thresholds] = None,
        narrate_model: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.thresholds = thresholds or Thresholds()
        self.narrate_model = narrate_model

    @sanitize_inputs
    def run(self, m: CampaignMetrics) -> EngineResult:
        """Execute the full pipeline for a single campaign metrics snapshot."""
        t0 = time.perf_counter()

        # --- deterministic layers --------------------------------------------
        signals = evaluate(m, self.thresholds)
        decision = decide(signals, m, self.thresholds)

        # --- stochastic layer (optional, fault-tolerant) ---------------------
        narrative, flags = self.generate_narration(
            signals, decision, m, model=self.narrate_model
        )

        elapsed_ms = (time.perf_counter() - t0) * 1_000

        return EngineResult(
            metrics=m,
            signals=signals,
            decision=decision,
            why=narrative,
            telemetry=TelemetryMetadata(
                execution_ms=elapsed_ms,
                input_sanitized=True,  # guaranteed by @sanitize_inputs
                circuit_state=flags.circuit_state,
                contract_verified=flags.contract_verified,
                fallback_triggered=flags.fallback_triggered,
                fallback_reason=flags.fallback_reason,
            ),
        )


# ===========================================================================
# HELPERS
# ===========================================================================

def _fallback_narrative(sv: SignalVector, decision: Decision) -> str:
    """Pure-function deterministic fallback — no external I/O, always safe."""
    primary_reason = decision.reasons[0].message if decision.reasons else decision.action.value
    return f"{primary_reason}. Signal summary: {sv.summary}."
