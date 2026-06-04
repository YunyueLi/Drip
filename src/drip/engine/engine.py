"""Engine orchestration: signals → rules → narration → card.

The action comes from the rule engine (deterministic, auditable). The LLM
only writes the human-facing "why". Narration is model-agnostic via
drip.llm — pass any provider/model string, or leave it off for a template.
"""

from __future__ import annotations

from dataclasses import dataclass

from drip.engine.rules import Decision, decide
from drip.engine.signals import CampaignMetrics, SignalVector, Thresholds, evaluate


@dataclass
class EngineResult:
    metrics: CampaignMetrics
    signals: SignalVector
    decision: Decision
    why: str


_NARRATE_SYSTEM = (
    "You are a senior user-acquisition operator. You are given a campaign's "
    "8-signal snapshot and the decision a deterministic rule engine has "
    "already made. Write 2-3 sentences explaining WHY this is the right "
    "call, referencing the specific signals and numbers. Do not second-guess "
    "or change the action — explain it. No preamble, no bullet points."
)


def _template_why(result_signals: SignalVector, decision: Decision) -> str:
    head = decision.reasons[0].message if decision.reasons else decision.action.value
    return f"{head}. Signals: {result_signals.summary}."


def narrate(
    sv: SignalVector,
    decision: Decision,
    m: CampaignMetrics,
    *,
    model: str | None = None,
) -> str:
    """Generate the human 'why'. Falls back to a template with no model/key."""
    if not model:
        return _template_why(sv, decision)

    signal_lines = "\n".join(
        f"  {s.status.value.upper():6} {s.name}: {s.value_str} (target {s.target_str}) — {s.note}"
        for s in sv.signals
    )
    rule_lines = "\n".join(f"  - {r.message}" for r in decision.reasons)
    user = (
        f"CAMPAIGN: {m.label}\n\n"
        f"SIGNALS ({sv.summary}):\n{signal_lines}\n\n"
        f"RULE-ENGINE DECISION: {decision.headline}\n"
        f"confidence: {decision.confidence.value}\n"
        f"rule chain:\n{rule_lines}\n\n"
        "Explain why this decision is correct."
    )
    try:
        from drip.llm import chat
        result = chat(
            model=model,
            system=_NARRATE_SYSTEM,
            messages=[{"role": "user", "content": user}],
            max_tokens=300,
            temperature=0.0,
        )
        return result.text or _template_why(sv, decision)
    except Exception:
        from drip.log import logger
        logger.warning("LLM narration failed, falling back to template", exc_info=True)
        return _template_why(sv, decision)


class DecisionEngine:
    """Run the full pipeline for one campaign snapshot."""

    def __init__(
        self,
        thresholds: Thresholds | None = None,
        narrate_model: str | None = None,
    ) -> None:
        self.thresholds = thresholds or Thresholds()
        self.narrate_model = narrate_model

    def run(self, m: CampaignMetrics) -> EngineResult:
        sv = evaluate(m, self.thresholds)
        decision = decide(sv, m, self.thresholds)
        why = narrate(sv, decision, m, model=self.narrate_model)
        return EngineResult(metrics=m, signals=sv, decision=decision, why=why)


# --------------------------------------------------------------------------
# Demo — `python -m drip.engine.engine`
# --------------------------------------------------------------------------

_DEMO_CASES = [
    ("healthy but sample on the edge", CampaignMetrics(
        cpp=18.0, cpp_target=25.0, roas=3.8, roas_target=3.0,
        cvr=0.025, cvr_baseline=0.025, daily_spend=200.0, budget_cap=240.0,
        purchases=11, ctr=0.014, ctr_baseline=0.014, frequency=1.8,
        label="DTC_US_Meta_Prospecting_v3",
    )),
    ("all green, thick sample", CampaignMetrics(
        cpp=16.0, cpp_target=25.0, roas=4.2, roas_target=3.0,
        cvr=0.031, cvr_baseline=0.030, daily_spend=180.0, budget_cap=260.0,
        purchases=22, ctr=0.016, ctr_baseline=0.015, frequency=1.6,
        label="DTC_US_Meta_Lookalike_v2",
    )),
    ("unit economics broken", CampaignMetrics(
        cpp=41.0, cpp_target=25.0, roas=1.4, roas_target=3.0,
        cvr=0.012, cvr_baseline=0.020, daily_spend=240.0, budget_cap=240.0,
        purchases=6, ctr=0.008, ctr_baseline=0.014, frequency=2.4,
        label="DTC_US_Meta_Broad_v1",
    )),
]


def _demo() -> None:  # pragma: no cover
    from drip.engine.cards import print_card
    engine = DecisionEngine()  # no narrate_model → template why (no API needed)
    for title, metrics in _DEMO_CASES:
        print(f"\n=== {title} ===")
        result = engine.run(metrics)
        print_card(result.decision, result.signals,
                   label=metrics.label, why=result.why)


if __name__ == "__main__":  # pragma: no cover
    _demo()
