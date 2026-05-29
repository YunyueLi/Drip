"""Prediction adapter — the "is this worth it" slot (LTV / value signal).

Drip does NOT train an LTV or MMM model. That needs the kind of proprietary
spend history Kohort ($6B) and Voyantis (user-level first-party data) have —
a data moat an open-source project can't and shouldn't fake.

Instead this slot accepts a *value signal* from wherever you trust it:

- ``null``       — no external model; the engine runs on observed metrics only (default)
- ``heuristic``  — a cheap proxy from ROAS × CVR × sample, as a stand-in
- bring your own — implement :class:`ValueModel` to wrap Kohort / Voyantis /
  Pecan / your in-house model

The estimate becomes one more input to the decision engine (and, optionally,
the ``target_value`` for value-based bidding in bidding.py). It never decides
on its own — it informs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ValueEstimate:
    metric: str               # e.g. "ltv_d30", "value_score", "none"
    value: float
    confidence: float = 0.5   # 0..1 — how much to trust this estimate
    source: str = ""

    def to_dict(self) -> dict[str, object]:
        return self.__dict__


class ValueModel(Protocol):
    """Implement this to plug in any LTV / value predictor."""

    name: str

    def estimate(self, features: dict[str, float]) -> ValueEstimate: ...


# --------------------------------------------------------------------------
# Built-in models
# --------------------------------------------------------------------------


class NullValueModel:
    """No external prediction. The engine runs on observed metrics alone —
    honest about having no forecast rather than faking one."""

    name = "null"

    def estimate(self, features: dict[str, float]) -> ValueEstimate:
        return ValueEstimate(metric="none", value=0.0, confidence=0.0, source="null")


class HeuristicValueModel:
    """A cheap stand-in, NOT a forecast. Combines observed ROAS, conversion
    rate, and sample size into a rough comparable score so the engine has
    *something* until you plug a real model. Low confidence by design."""

    name = "heuristic"

    def estimate(self, features: dict[str, float]) -> ValueEstimate:
        roas = float(features.get("roas", 0.0))
        cvr = float(features.get("cvr", 0.0))
        purchases = float(features.get("purchases", 0.0))
        # sqrt(sample) dampens thin-sample noise — same instinct as the engine.
        score = roas * cvr * (purchases ** 0.5)
        return ValueEstimate(
            metric="value_score",
            value=round(score, 4),
            confidence=0.3,
            source="heuristic",
        )


_MODELS: dict[str, type[ValueModel]] = {
    "null": NullValueModel,
    "heuristic": HeuristicValueModel,
}


def build_value_model(name: str = "null") -> ValueModel:
    """Build a value model by name. Unknown name → null (no fake forecast)."""
    cls = _MODELS.get(name, NullValueModel)
    return cls()
