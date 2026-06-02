"""Intraday (spend-side) control — the hourly layer above the daily engine.

The daily engine (:mod:`drip.engine.rules`) decides ROI / scale / pause on a
24–48h cadence. This intraday layer runs every ~15–60 min on **spend-side
signals only** — pacing, cost spikes, budget exhaustion — because that's as fast
as platform data refreshes and as fast as native rules run (see
``docs/intraday-research.md``). It deliberately does **not** touch ROI decisions
(ROAS isn't stable intraday) and keeps actions conservative — throttle / pause /
small raises — so it doesn't reset the platform learning phase.

Same shape as the daily engine: signals → deterministic rules → an auditable
decision with a rule chain. Pure logic, no I/O — tests offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from drip.engine.rules import Confidence, Reason

# A budget is "pacing early" if it will exhaust before this fraction of the day.
EXHAUST_EARLY = 0.85
# Cost ratios (recent CPA / target) that trip throttle / pause.
COST_THROTTLE = 1.5
COST_PAUSE = 2.0
# Recent CPA / today's baseline that counts as a spike.
SPIKE = 1.5
# Below this many conversions in the window, the read is noise — cap confidence,
# never pause or raise on it.
THIN_CONV = 5


class IntradayAction(str, Enum):
    HOLD = "HOLD"
    THROTTLE = "THROTTLE"   # cut the daily budget to slow the bleed / re-pace
    PAUSE = "PAUSE"         # stop spend now (cost breach)
    RAISE = "RAISE"         # small budget bump (underpacing + healthy)


@dataclass
class IntradayMetrics:
    """One campaign's within-day state at a point in time."""

    campaign_id: str
    daily_budget: float          # today's set daily budget
    spend_so_far: float          # cumulative spend today
    day_fraction: float          # 0..1 of the (dayparted) day elapsed
    cpa_recent: float            # cost-per-action in the recent window (e.g. last hour)
    cpa_baseline: float          # today's rolling baseline CPA
    cpa_target: float            # acceptable CPA ceiling
    conversions_recent: int = 0  # conversions in the recent window (sample size)
    label: str = ""
    platform: str = "meta"


@dataclass
class IntradaySignals:
    pace_ratio: float        # spend_so_far / expected-by-now (>1 = overpacing)
    cost_ratio: float        # cpa_recent / cpa_target (>1 = over the ceiling)
    spike_ratio: float       # cpa_recent / cpa_baseline (>1.x = spiking vs itself)
    projected_eod: float     # projected end-of-day spend at the current rate
    exhaust_at: float        # day_fraction at which the budget runs out (1 = not early)

    @property
    def summary(self) -> str:
        return (f"pace {self.pace_ratio:.2f}× · cost {self.cost_ratio:.2f}× target · "
                f"spike {self.spike_ratio:.2f}× · exhausts at {self.exhaust_at:.0%} of day")


@dataclass
class IntradayDecision:
    action: IntradayAction
    delta_pct: float                       # e.g. -0.30 throttle, +0.10 raise; 0 hold/pause
    confidence: Confidence
    reasons: list[Reason] = field(default_factory=list)
    next_check_min: int = 30
    current_budget: float = 0.0
    projected_budget: float = 0.0

    @property
    def headline(self) -> str:
        if self.action in (IntradayAction.THROTTLE, IntradayAction.RAISE):
            sign = "+" if self.delta_pct >= 0 else ""
            return (f"{self.action.value} · ${self.current_budget:,.0f} → "
                    f"${self.projected_budget:,.0f}/day ({sign}{self.delta_pct:.0%})")
        return self.action.value


def evaluate_intraday(m: IntradayMetrics) -> IntradaySignals:
    frac = max(m.day_fraction, 1e-6)
    expected = m.daily_budget * frac
    pace_ratio = m.spend_so_far / expected if expected else 0.0
    cost_ratio = m.cpa_recent / m.cpa_target if m.cpa_target else 0.0
    spike_ratio = m.cpa_recent / m.cpa_baseline if m.cpa_baseline else 0.0
    rate = m.spend_so_far / frac                       # implied full-day spend at this pace
    exhaust_at = min(m.daily_budget / rate, 1.0) if rate else 1.0
    return IntradaySignals(
        pace_ratio=pace_ratio, cost_ratio=cost_ratio, spike_ratio=spike_ratio,
        projected_eod=rate, exhaust_at=exhaust_at,
    )


def decide_intraday(s: IntradaySignals, m: IntradayMetrics) -> IntradayDecision:
    """Deterministic spend-side rules. Conservative by design: only the recent
    window is used, ROI is never optimised here, and thin samples can't pause."""
    thin = m.conversions_recent < THIN_CONV
    reasons: list[Reason] = []
    action = IntradayAction.HOLD
    delta = 0.0

    # 1. Cost breach — stop the bleed (only on a real sample).
    if s.cost_ratio >= COST_PAUSE and not thin:
        action, delta = IntradayAction.PAUSE, 0.0
        reasons.append(Reason("intraday.cost_breach",
                              f"recent CPA {s.cost_ratio:.1f}× target — stop the bleed now"))
    # 2. Cost over tolerance, or a spike vs its own baseline — throttle.
    elif s.cost_ratio >= COST_THROTTLE or (s.spike_ratio >= SPIKE and s.cost_ratio >= 1.0):
        action, delta = IntradayAction.THROTTLE, -0.30
        reasons.append(Reason("intraday.cost_high",
                              f"recent CPA {s.cost_ratio:.1f}× target (spike {s.spike_ratio:.1f}×) "
                              f"— cut budget to re-pace"))
    # 3. Burning the budget too early while cost is fine — gentle throttle to smooth.
    elif s.exhaust_at < EXHAUST_EARLY and s.cost_ratio > 1.0:
        action, delta = IntradayAction.THROTTLE, -0.15
        reasons.append(Reason("intraday.overpace",
                              f"budget exhausts at {s.exhaust_at:.0%} of day and cost is soft "
                              f"— trim to keep evening coverage"))
    # 4. Underpacing a healthy campaign — small raise (never on thin data).
    elif s.pace_ratio < 0.7 and s.cost_ratio <= 0.9 and not thin:
        action, delta = IntradayAction.RAISE, 0.10
        reasons.append(Reason("intraday.underpace_healthy",
                              f"only {s.pace_ratio:.0%} of expected spend and CPA "
                              f"{s.cost_ratio:.1f}× target — nudge budget up"))
    else:
        reasons.append(Reason("intraday.steady", "pacing and cost within band — hold"))

    if thin and action in (IntradayAction.PAUSE, IntradayAction.RAISE):
        # safety net (shouldn't trigger given the guards above): never act hard on noise
        action, delta = IntradayAction.HOLD, 0.0
        reasons.append(Reason("intraday.thin_sample",
                              f"only {m.conversions_recent} conversions in window — hold, too noisy"))

    if thin:
        conf = Confidence.LOW
    elif action is IntradayAction.HOLD:
        conf = Confidence.MEDIUM
    else:
        conf = Confidence.HIGH if s.cost_ratio >= COST_PAUSE or s.cost_ratio <= 0.9 else Confidence.MEDIUM

    projected = m.daily_budget * (1 + delta) if action in (
        IntradayAction.THROTTLE, IntradayAction.RAISE) else (
        0.0 if action is IntradayAction.PAUSE else m.daily_budget)
    return IntradayDecision(
        action=action, delta_pct=delta, confidence=conf, reasons=reasons,
        next_check_min=30, current_budget=m.daily_budget, projected_budget=projected,
    )
