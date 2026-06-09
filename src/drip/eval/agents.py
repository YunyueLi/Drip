"""Agent adapters for Drip-Bench.

An agent reads a :class:`Case` and emits an :class:`AgentResponse`. All
model-backed agents run on the unified :mod:`drip.llm` layer, so any
provider works out of the box:

    drip bench run --agent openai/gpt-4o
    drip bench run --agent anthropic/claude-sonnet-4-6
    drip bench run --agent openrouter/google/gemini-2.0-flash
    drip bench run --agent deepseek/deepseek-chat

Two flavours of model agent:

- ``LLMAgent``  — the raw model, given only the case.
- ``DripAgent`` — the same model **plus Drip's 8-signal methodology** in
  the system prompt. Comparing ``--agent claude-...`` against
  ``--agent drip:claude-...`` measures what Drip's framework adds.
"""

from __future__ import annotations

from typing import Protocol

from drip.eval.schema import AgentResponse, Case
from drip.llm import LLMError, chat


class Agent(Protocol):
    name: str

    def answer(self, case: Case) -> AgentResponse: ...


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

AGENT_SYSTEM = """You are a senior user-acquisition operator. You are given \
a campaign situation and a multiple-choice decision. You must:

1. Pick exactly one choice key (e.g. "A", "B", "C", "D").
2. Give a brief reasoning (3-6 sentences) explaining WHY, citing the \
specific signals/numbers in the case.
3. If your choice implies a numeric delta (e.g. "SCALE +20%"), report it.

Return ONLY a JSON object:
{"chosen_action": "A", "numeric_delta": 0.20, "reasoning": "..."}"""

# Drip's methodology — injected so any base model reasons the Drip way.
DRIP_METHODOLOGY = """Before answering, evaluate the situation against \
Drip's 8 signals:
  1. CPP/CPA/CPI vs target   (green if <= target)
  2. ROAS vs target          (green if >= target)
  3. Purchase CVR stability  (3-day; a >15% drop is red)
  4. Daily spend vs cap
  5. Purchases vs min sample (min 10) — THIN SAMPLE caps your confidence
  6. CTR stability           (3-day; a >15% drop is red)
  7. Frequency vs cap (2.5)  — past cap = creative saturation
  8. Budget headroom         — is there room to scale?

Apply this decision priority, in order:
  1. CPP and ROAS both red       -> PAUSE (unit economics broken)
  2. ROAS red                    -> REDUCE spend
  3. Frequency past cap          -> REFRESH creative, do NOT scale into it
  4. 7-8 green + thick sample + headroom -> SCALE (+20% only if 8/8 with a
     thick sample; otherwise the conservative +10%)
  5. Otherwise                   -> HOLD for a clearer read

Always: a thin sample forces the conservative step and caps confidence.
Always prefer the smallest meaningful move, and state the guardrail that
would make you revert. Then choose the option that best matches."""

DRIP_SYSTEM = AGENT_SYSTEM + "\n\n" + DRIP_METHODOLOGY


def _user_message(case: Case) -> str:
    choices = "\n".join(f"  {k}: {v}" for k, v in case.choices.items())
    return (
        f"CASE {case.id:03d} — {case.title}\n\n"
        f"SITUATION:\n{case.context.strip()}\n\n"
        f"QUESTION: {case.question}\n\n"
        f"CHOICES:\n{choices}\n"
    )


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------


class DummyAgent:
    """Always the first choice — a leaderboard floor. No API needed."""

    name = "dummy"

    def __init__(self, fixed_choice: str | None = None) -> None:
        self._fixed = fixed_choice

    def answer(self, case: Case) -> AgentResponse:
        choice = self._fixed or next(iter(case.choices))
        return AgentResponse(
            chosen_action=choice,
            numeric_delta=None,
            reasoning="Dummy baseline — always the first choice.",
            raw={"strategy": "fixed-first"},
        )


class LLMAgent:
    """Any provider/model via drip.llm. Optionally armed with a methodology."""

    def __init__(
        self,
        model: str,
        *,
        system: str = AGENT_SYSTEM,
        name: str | None = None,
        max_tokens: int = 8192,
    ) -> None:
        self.model = model
        self.system = system
        self.name = name or model
        # Reasoning models (e.g. deepseek-v4-pro, o-series) spend most of the
        # token budget on hidden chain-of-thought before the answer, so the cap
        # must be generous or the JSON answer gets truncated mid-string.
        self.max_tokens = max_tokens

    def answer(self, case: Case) -> AgentResponse:
        try:
            result = chat(
                model=self.model,
                system=self.system,
                messages=[{"role": "user", "content": _user_message(case)}],
                json_mode=True,
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
        except LLMError as exc:
            raise RuntimeError(f"agent '{self.name}' failed: {exc}") from exc

        try:
            data = result.json()
        except Exception as exc:
            raise RuntimeError(
                f"agent '{self.name}' returned non-JSON: {result.text[:200]}"
            ) from exc

        return AgentResponse(
            chosen_action=str(data.get("chosen_action", "")).strip(),
            numeric_delta=data.get("numeric_delta"),
            reasoning=str(data.get("reasoning", "")),
            raw={
                "model": result.model,
                "provider": result.provider,
                "usage": result.usage,
            },
        )


def DripAgent(model: str = "anthropic/claude-sonnet-4-6") -> LLMAgent:
    """Drip = base model + Drip's 8-signal methodology in the prompt."""
    return LLMAgent(model, system=DRIP_SYSTEM, name=f"drip:{model}")


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


def build_agent(name: str) -> Agent:
    """Build an agent from a short name.

    - ``dummy``                  → :class:`DummyAgent`
    - ``drip``                   → Drip methodology on the default model
    - ``drip:<provider/model>``  → Drip methodology on a chosen model
    - anything else              → raw :class:`LLMAgent` on that model spec
      (e.g. ``openai/gpt-4o``, ``claude-sonnet-4-6``, ``openrouter/...``)
    """
    if name == "dummy":
        return DummyAgent()
    if name == "drip":
        return DripAgent()
    if name.startswith("drip:"):
        return DripAgent(name[len("drip:"):])
    return LLMAgent(name)
