"""The 8 signals — Drip's decision-engine inputs.

Modelled on GrowthGPT's autopilot demo: each signal is evaluated against a
hard threshold and resolves to GREEN / YELLOW / RED. Confidence and the
final action are derived from the signal vector, NOT from a free-form LLM
guess. The LLM only narrates the decision afterwards (see engine.py).

Pure stdlib — no pydantic, no third-party deps — so this module runs and
tests under plain CPython without installing the project.

Thresholds live as module constants and can be overridden per-vertical by
a Knowledge Pack (v0.1) by passing a ``Thresholds`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

    @property
    def mark(self) -> str:
        return {"green": "✓", "yellow": "~", "red": "✗"}[self.value]


# --------------------------------------------------------------------------
# Tunable thresholds (GrowthGPT-style defaults)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    # CPP / CPA / CPI: ratio of actual to target.
    cpp_yellow_ratio: float = 1.0      # <= target → green
    cpp_red_ratio: float = 1.2         # > 1.2x target → red

    # ROAS: ratio of actual to target.
    roas_yellow_ratio: float = 1.0     # >= target → green
    roas_red_ratio: float = 0.8        # < 0.8x target → red

    # Stability signals (CVR, CTR): day-over-day change vs baseline.
    stability_yellow_drop: float = 0.05   # 5% drop → yellow
    stability_red_drop: float = 0.15      # 15% drop → red

    # Daily spend vs cap.
    spend_yellow_ratio: float = 0.90   # < 90% cap → green
    spend_red_ratio: float = 1.0       # >= cap → red

    # Conversion sample size.
    min_sample: int = 10
    sample_green_mult: float = 1.5     # >= 1.5x min → green

    # Frequency.
    freq_cap: float = 2.5
    freq_yellow: float = 2.0           # < 2.0 → green

    # Budget headroom (room to scale).
    headroom_green: float = 0.15       # > 15% headroom → green
    headroom_red: float = 0.05         # < 5% → red


DEFAULT = Thresholds()


# --------------------------------------------------------------------------
# Inputs + Signal record
# --------------------------------------------------------------------------


@dataclass
class CampaignMetrics:
    """One campaign's last-window metrics. Baselines drive stability checks."""

    cpp: float                  # cost per purchase (or CPA / CPI)
    cpp_target: float
    roas: float
    roas_target: float
    cvr: float                  # current purchase conversion rate
    cvr_baseline: float         # trailing baseline for stability
    daily_spend: float
    budget_cap: float
    purchases: int              # daily conversions (sample size)
    ctr: float
    ctr_baseline: float
    frequency: float
    label: str = "campaign"     # human label for the card


@dataclass
class Signal:
    name: str
    status: Status
    value_str: str              # rendered actual, e.g. "$18.00"
    target_str: str             # rendered target/threshold, e.g. "$25.00"
    note: str = ""

    @property
    def is_green(self) -> bool:
        return self.status is Status.GREEN

    @property
    def is_red(self) -> bool:
        return self.status is Status.RED


# --------------------------------------------------------------------------
# Individual evaluators
# --------------------------------------------------------------------------


def _stability_status(current: float, baseline: float, t: Thresholds) -> Status:
    if baseline <= 0:
        return Status.YELLOW
    drop = (baseline - current) / baseline
    if drop >= t.stability_red_drop:
        return Status.RED
    if drop >= t.stability_yellow_drop:
        return Status.YELLOW
    return Status.GREEN


def eval_cpp(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    ratio = m.cpp / m.cpp_target if m.cpp_target else 99.0
    if ratio <= t.cpp_yellow_ratio:
        status = Status.GREEN
    elif ratio <= t.cpp_red_ratio:
        status = Status.YELLOW
    else:
        status = Status.RED
    pct = (1 - ratio) * 100
    note = f"{abs(pct):.0f}% {'below' if pct >= 0 else 'above'} target"
    return Signal("CPP", status, f"${m.cpp:,.2f}", f"${m.cpp_target:,.2f}", note)


def eval_roas(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    ratio = m.roas / m.roas_target if m.roas_target else 0.0
    if ratio >= t.roas_yellow_ratio:
        status = Status.GREEN
    elif ratio >= t.roas_red_ratio:
        status = Status.YELLOW
    else:
        status = Status.RED
    return Signal("ROAS", status, f"{m.roas:.1f}x", f"{m.roas_target:.1f}x",
                  "exceeding" if status is Status.GREEN else "below target")


def eval_cvr(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    status = _stability_status(m.cvr, m.cvr_baseline, t)
    return Signal("Purchase CVR", status, f"{m.cvr:.2%}", f"{m.cvr_baseline:.2%} base",
                  {"green": "3-day stable", "yellow": "softening", "red": "dropping"}[status.value])


def eval_spend(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    ratio = m.daily_spend / m.budget_cap if m.budget_cap else 99.0
    if ratio < t.spend_yellow_ratio:
        status = Status.GREEN
    elif ratio < t.spend_red_ratio:
        status = Status.YELLOW
    else:
        status = Status.RED
    return Signal("Daily Spend", status, f"${m.daily_spend:,.0f}", f"${m.budget_cap:,.0f} cap",
                  f"{ratio:.0%} of cap")


def eval_purchases(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    if m.purchases >= t.min_sample * t.sample_green_mult:
        status = Status.GREEN
    elif m.purchases >= t.min_sample:
        status = Status.YELLOW
    else:
        status = Status.RED
    return Signal("Purchases", status, f"{m.purchases}", f"min {t.min_sample}",
                  "sufficient sample" if status is Status.GREEN else "thin sample")


def eval_ctr(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    status = _stability_status(m.ctr, m.ctr_baseline, t)
    return Signal("CTR", status, f"{m.ctr:.2%}", f"{m.ctr_baseline:.2%} base",
                  {"green": "3-day stable", "yellow": "softening", "red": "dropping"}[status.value])


def eval_frequency(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    if m.frequency < t.freq_yellow:
        status = Status.GREEN
    elif m.frequency <= t.freq_cap:
        status = Status.YELLOW
    else:
        status = Status.RED
    return Signal("Frequency", status, f"{m.frequency:.1f}", f"cap {t.freq_cap:.1f}",
                  "room to run" if status is Status.GREEN else "near saturation")


def eval_budget_headroom(m: CampaignMetrics, t: Thresholds = DEFAULT) -> Signal:
    headroom = (m.budget_cap - m.daily_spend) / m.budget_cap if m.budget_cap else 0.0
    if headroom > t.headroom_green:
        status = Status.GREEN
    elif headroom >= t.headroom_red:
        status = Status.YELLOW
    else:
        status = Status.RED
    return Signal("Budget", status, f"{headroom:.0%} headroom", ">15% to scale",
                  "room to scale" if status is Status.GREEN else "tight")


# The canonical 8-signal vector, in display order.
EVALUATORS = [
    eval_cpp,
    eval_roas,
    eval_cvr,
    eval_spend,
    eval_purchases,
    eval_ctr,
    eval_frequency,
    eval_budget_headroom,
]


@dataclass
class SignalVector:
    signals: list[Signal] = field(default_factory=list)

    @property
    def green(self) -> int:
        return sum(1 for s in self.signals if s.status is Status.GREEN)

    @property
    def red(self) -> int:
        return sum(1 for s in self.signals if s.status is Status.RED)

    @property
    def total(self) -> int:
        return len(self.signals)

    def by_name(self, name: str) -> Signal | None:
        for s in self.signals:
            if s.name == name:
                return s
        return None

    @property
    def summary(self) -> str:
        return f"{self.green}/{self.total} green"


def evaluate(m: CampaignMetrics, t: Thresholds = DEFAULT) -> SignalVector:
    """Run all 8 evaluators against the metrics."""
    return SignalVector([fn(m, t) for fn in EVALUATORS])
