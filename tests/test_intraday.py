"""Tests for the intraday (spend-side) control engine — pure logic, no I/O."""

from __future__ import annotations

from typing import Any

from drip.engine.intraday import (
    IntradayAction,
    IntradayMetrics,
    decide_intraday,
    evaluate_intraday,
)
from drip.engine.rules import Confidence


def mk(**kw: object) -> IntradayMetrics:
    base: dict[str, Any] = dict(
        campaign_id="c", daily_budget=200.0, spend_so_far=100.0, day_fraction=0.5,
        cpa_recent=18.0, cpa_baseline=18.0, cpa_target=25.0, conversions_recent=10, label="L",
    )
    base.update(kw)
    return IntradayMetrics(**base)


def decide(**kw: object) -> tuple[object, object]:
    m = mk(**kw)
    s = evaluate_intraday(m)
    return decide_intraday(s, m), s


def test_evaluate_pacing_and_cost() -> None:
    s = evaluate_intraday(mk())
    assert abs(s.pace_ratio - 1.0) < 1e-9          # 100 spent vs 100 expected at mid-day
    assert abs(s.cost_ratio - 0.72) < 1e-9          # 18 / 25
    assert abs(s.exhaust_at - 1.0) < 1e-9           # on pace → not early


def test_cost_breach_pauses() -> None:
    d, _ = decide(cpa_recent=55.0)
    assert d.action is IntradayAction.PAUSE
    assert d.projected_budget == 0.0


def test_cost_over_tolerance_throttles() -> None:
    d, _ = decide(cpa_recent=40.0)
    assert d.action is IntradayAction.THROTTLE
    assert abs(d.delta_pct + 0.30) < 1e-9


def test_spike_vs_baseline_throttles() -> None:
    d, _ = decide(cpa_recent=28.0, cpa_baseline=16.0)  # 1.75× its own baseline, just over target
    assert d.action is IntradayAction.THROTTLE


def test_overpacing_soft_cost_trims_gently() -> None:
    d, s = decide(spend_so_far=160.0, cpa_recent=27.0, cpa_baseline=26.0)
    assert d.action is IntradayAction.THROTTLE
    assert abs(d.delta_pct + 0.15) < 1e-9
    assert s.exhaust_at < 0.85


def test_underpacing_healthy_raises() -> None:
    d, _ = decide(spend_so_far=50.0, cpa_recent=18.0)
    assert d.action is IntradayAction.RAISE
    assert abs(d.delta_pct - 0.10) < 1e-9


def test_thin_sample_cannot_pause_only_throttles() -> None:
    d, _ = decide(cpa_recent=55.0, conversions_recent=2)  # breach but noisy
    assert d.action is IntradayAction.THROTTLE
    assert d.confidence is Confidence.LOW


def test_thin_sample_cannot_raise() -> None:
    d, _ = decide(spend_so_far=50.0, conversions_recent=2)  # would raise, but too noisy
    assert d.action is IntradayAction.HOLD
    assert d.confidence is Confidence.LOW


def test_steady_holds() -> None:
    d, _ = decide()
    assert d.action is IntradayAction.HOLD
    assert d.confidence is Confidence.MEDIUM
    assert d.projected_budget == d.current_budget
