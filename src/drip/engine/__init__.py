"""Drip decision engine — the autopilot core.

    signals → rule engine → decision → LLM narration → card

Deterministic where it matters (the action is decided by rules over the
8-signal vector), explainable everywhere (every decision carries its rule
chain), and model-agnostic for the narration (any provider via drip.llm).
"""

from drip.engine.engine import DecisionEngine, EngineResult
from drip.engine.rules import Action, Confidence, Decision, decide
from drip.engine.signals import CampaignMetrics, SignalVector, Thresholds, evaluate

__all__ = [
    "DecisionEngine",
    "EngineResult",
    "CampaignMetrics",
    "SignalVector",
    "Thresholds",
    "evaluate",
    "decide",
    "Decision",
    "Action",
    "Confidence",
]
