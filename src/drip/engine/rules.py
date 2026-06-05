"""Rule engine — turns a SignalVector into an auditable Decision.

This is the deterministic core. The LLM does NOT decide the action here;
it only narrates afterwards (engine.py). Every action carries the rule
chain that produced it, so the decision is auditable end-to-end — the
property GrowthGPT advertises and closed-source agents can't show you.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from drip.engine.signals import CampaignMetrics, SignalVector, Status, Thresholds


class Action(str, Enum):
    SCALE = "SCALE"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    PAUSE = "PAUSE"
    REFRESH_CREATIVE = "REFRESH_CREATIVE"


# Sets derived from Action for quick membership checks in adapters and safety.
BUDGET_ACTIONS: frozenset[str] = frozenset({Action.SCALE, Action.REDUCE})
PAUSE_ACTIONS: frozenset[str] = frozenset({Action.PAUSE})


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Reason:
    rule_id: str
    message: str


@dataclass
class Guardrail:
    condition: str        # e.g. "CPP > $22.00"
    action: str = "revert"


@dataclass
class Decision:
    action: Action
    delta_pct: float                 # +0.20 = +20%; 0 for HOLD/PAUSE/REFRESH
    confidence: Confidence
    reasons: list[Reason] = field(default_factory=list)
    guardrails: list[Guardrail] = field(default_factory=list)
    next_check_hours: int = 24
    current_budget: float = 0.0
    projected_budget: float = 0.0

    @property
    def headline(self) -> str:
        if self.action is Action.SCALE or self.action is Action.REDUCE:
            sign = "+" if self.delta_pct >= 0 else ""
            return (f"{self.action.value} · "
                    f"${self.current_budget:,.0f} → ${self.projected_budget:,.0f}/day "
                    f"({sign}{self.delta_pct:.0%})")
        return f"{self.action.value}"

    # Map to the bench's A/B/C/D world when needed (see eval/agents.py).
    def to_bench_letter(self, choices: dict[str, str]) -> str:
        """Best-effort match of this decision to a multiple-choice key by
        looking for the action verb in the choice text."""
        verb = self.action.value.split("_")[0].lower()  # scale/reduce/hold/pause/refresh
        for key, text in choices.items():
            if verb in text.lower():
                return key
        # PAUSE-ish fallbacks
        if self.action in (Action.REDUCE, Action.REFRESH_CREATIVE):
            for key, text in choices.items():
                if "hold" in text.lower() or "reduce" in text.lower():
                    return key
        return next(iter(choices))


def decide(sv: SignalVector, m: CampaignMetrics, t: Thresholds | None = None) -> Decision:
    t = t or Thresholds()
    cpp = sv.by_name("CPP")
    roas = sv.by_name("ROAS")
    freq = sv.by_name("Frequency")
    purch = sv.by_name("Purchases")
    headroom = sv.by_name("Budget")

    reasons: list[Reason] = []
    action = Action.HOLD
    delta = 0.0

    # 1. Unit economics broken → stop the bleed.
    if cpp and roas and cpp.is_red and roas.is_red:
        action, delta = Action.PAUSE, 0.0
        reasons.append(Reason("econ.both_red",
                              "CPP and ROAS both red — unit economics broken"))
    elif roas and roas.is_red:
        action, delta = Action.REDUCE, -0.30
        reasons.append(Reason("econ.roas_red",
                              "ROAS below floor — cut spend to protect efficiency"))
    elif cpp and cpp.is_red:
        action, delta = Action.REDUCE, -0.20
        reasons.append(Reason("econ.cpp_red",
                              "CPP over tolerance — trim spend"))

    # 2. Creative saturation → refresh, don't scale into the wall.
    elif freq and freq.is_red:
        action, delta = Action.REFRESH_CREATIVE, 0.0
        reasons.append(Reason("creative.freq_saturated",
                              "Frequency past cap — creative is saturating, "
                              "refresh before adding budget"))

    # 3. Strong green → scale, sized by signal strength + sample.
    elif sv.green >= 7 and not (headroom and headroom.is_red) \
            and not (purch and purch.is_red):
        if sv.green == 8 and purch and purch.is_green:
            delta = 0.20
            reasons.append(Reason("scale.full_green",
                                  "8/8 signals green with a thick sample — "
                                  "scale at the standard step"))
        else:
            delta = 0.10
            reasons.append(Reason("scale.cautious",
                                  f"{sv.green}/8 green but sample/headroom not "
                                  "fully clear — take the conservative step"))
        action = Action.SCALE

    # 4. Mixed → hold for clarity.
    else:
        action, delta = Action.HOLD, 0.0
        reasons.append(Reason("hold.mixed",
                              f"{sv.green}/8 green, signals mixed — hold for "
                              "clearer reads before moving budget"))

    # Confidence from the signal vector (not vibes).
    if sv.green == 8 and purch and purch.is_green:
        conf = Confidence.HIGH
    elif sv.green >= 6:
        conf = Confidence.MEDIUM
    else:
        conf = Confidence.LOW
    # Thin-sample caps confidence — the lesson from bench case 001.
    if purch and purch.is_red:
        conf = Confidence.LOW
        reasons.append(Reason("conf.thin_sample",
                              "Sample below minimum — confidence capped low"))
    elif purch and purch.status is Status.YELLOW and conf is Confidence.HIGH:
        conf = Confidence.MEDIUM
        reasons.append(Reason("conf.sample_edge",
                              "Sample near minimum — confidence downgraded"))

    # Auto-generated guardrails for any budget-moving action.
    guardrails: list[Guardrail] = []
    if action in (Action.SCALE, Action.REDUCE):
        revert_cpp = m.cpp_target * 0.88
        guardrails.append(Guardrail(f"CPP > ${revert_cpp:,.2f}"))
        guardrails.append(Guardrail("CTR drop > 15% within 24h"))

    next_check = {
        Action.SCALE: 48,
        Action.REDUCE: 24,
        Action.PAUSE: 24,
        Action.HOLD: 24,
        Action.REFRESH_CREATIVE: 24,
    }[action]

    projected = m.daily_spend * (1 + delta)
    return Decision(
        action=action,
        delta_pct=delta,
        confidence=conf,
        reasons=reasons,
        guardrails=guardrails,
        next_check_hours=next_check,
        current_budget=m.daily_spend,
        projected_budget=projected,
    )
