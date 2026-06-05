"""Decision-engine behaviour lock.

These tests double as the engine's spec: each one states a rule the
8-signal engine must obey. Pure stdlib + the engine package — no API keys,
no provider deps — so they run anywhere.
"""

from __future__ import annotations

from typing import Any

from drip.engine import CampaignMetrics, DecisionEngine, decide, evaluate
from drip.engine.rules import Action, Confidence
from drip.engine.signals import Status


def _m(**overrides: object) -> CampaignMetrics:
    """An all-green, thick-sample campaign; override one factor per test."""
    base: dict[str, Any] = dict(
        cpp=18.0, cpp_target=25.0,
        roas=3.8, roas_target=3.0,
        cvr=0.025, cvr_baseline=0.025,
        daily_spend=200.0, budget_cap=240.0,
        purchases=20,
        ctr=0.014, ctr_baseline=0.014,
        frequency=1.8,
        label="test",
    )
    base.update(overrides)
    return CampaignMetrics(**base)


# --- the three headline behaviours -----------------------------------------


def test_all_green_thick_sample_scales_20_high() -> None:
    r = DecisionEngine().run(_m(cpp=16.0, roas=4.2, purchases=22,
                                daily_spend=180.0, budget_cap=260.0))
    assert r.decision.action is Action.SCALE
    assert r.decision.delta_pct == 0.20
    assert r.decision.confidence is Confidence.HIGH


def test_thin_sample_forces_cautious_scale_medium() -> None:
    # 11 purchases is above the min (10) but below the green bar (15) →
    # the lesson from bench case 001: scale, but smaller, with less confidence.
    r = DecisionEngine().run(_m(purchases=11))
    assert r.decision.action is Action.SCALE
    assert r.decision.delta_pct == 0.10
    assert r.decision.confidence is Confidence.MEDIUM


def test_both_econ_signals_red_pauses_low() -> None:
    r = DecisionEngine().run(_m(cpp=41.0, roas=1.4, purchases=6,
                                daily_spend=240.0, budget_cap=240.0,
                                cvr=0.012, cvr_baseline=0.020, ctr=0.008))
    assert r.decision.action is Action.PAUSE
    assert r.decision.confidence is Confidence.LOW


# --- individual rules -------------------------------------------------------


def test_roas_red_reduces() -> None:
    r = DecisionEngine().run(_m(roas=1.5))
    assert r.decision.action is Action.REDUCE
    assert r.decision.delta_pct < 0


def test_frequency_past_cap_refreshes_not_scales() -> None:
    r = DecisionEngine().run(_m(frequency=3.0))
    assert r.decision.action is Action.REFRESH_CREATIVE


def test_scale_emits_guardrails() -> None:
    r = DecisionEngine().run(_m(cpp=16.0, roas=4.2, purchases=22,
                                daily_spend=180.0, budget_cap=260.0))
    conditions = " ".join(g.condition for g in r.decision.guardrails)
    assert "CPP" in conditions
    assert "CTR" in conditions


# --- signal evaluators ------------------------------------------------------


def test_thin_sample_is_yellow() -> None:
    sv = evaluate(_m(purchases=11))
    assert sv.by_name("Purchases").status is Status.YELLOW


def test_below_min_sample_is_red() -> None:
    sv = evaluate(_m(purchases=6))
    assert sv.by_name("Purchases").status is Status.RED


def test_frequency_past_cap_is_red() -> None:
    sv = evaluate(_m(frequency=3.0))
    assert sv.by_name("Frequency").status is Status.RED


def test_ctr_sharp_drop_is_red() -> None:
    sv = evaluate(_m(ctr=0.010, ctr_baseline=0.014))  # ~29% drop
    assert sv.by_name("CTR").status is Status.RED


# --- bench bridge -----------------------------------------------------------


def test_to_bench_letter_matches_action_verb() -> None:
    m = _m(cpp=16.0, roas=4.2, purchases=22, daily_spend=180.0, budget_cap=260.0)
    decision = decide(evaluate(m), m)
    choices = {"A": "SCALE budget +20%", "B": "HOLD", "C": "PAUSE"}
    assert decision.to_bench_letter(choices) == "A"
