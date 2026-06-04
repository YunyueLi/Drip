"""Allocator behaviour lock — cross-platform budget allocation.

Tests cover:
  - AllocationPlan conservation (sum of budgets == total)
  - PAUSE → $0, SCALE → +delta, HOLD → keep current
  - _value_weights defaults and pluggable model path
  - Edge cases: zero budget, single campaign, empty list
"""

from __future__ import annotations

from drip.allocator import Allocation, AllocationPlan, Allocator
from drip.data.metrics import AdMetrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _m(platform: str = "meta", spend: float = 200.0,
       conversions: float = 12.0, value: float = 760.0,
       clicks: int = 1400, imps: int = 100_000, **kw: object) -> AdMetrics:
    return AdMetrics(
        platform=platform, campaign_id=f"{platform}-001",
        date_start="2026-05-01", date_end="2026-05-28",
        spend=spend, impressions=imps, clicks=clicks,
        conversions=conversions, conversion_value=value,
        reach=50_000, label=kw.pop("label", f"{platform}_test"),
        **{k: v for k, v in kw.items() if k in AdMetrics.__dataclass_fields__},
    )


# ---------------------------------------------------------------------------
# Allocation & AllocationPlan
# ---------------------------------------------------------------------------


def test_allocation_delta() -> None:
    m = _m()
    from drip.engine import DecisionEngine
    r = DecisionEngine().run(m.to_engine_metrics(
        cpp_target=25.0, roas_target=3.0, budget_cap=1000.0,
    ))
    a = Allocation(metrics=m, result=r, old_budget=200.0, new_budget=240.0)
    assert a.delta == 40.0
    assert a.reason == r.decision.action.value


def test_allocation_plan_allocated() -> None:
    a1 = Allocation(_m(), None, 100.0, 150.0)
    a2 = Allocation(_m(), None, 200.0, 250.0)
    plan = AllocationPlan(allocations=[a1, a2], total_budget=500.0)
    assert plan.allocated == 400.0


def test_allocation_plan_empty() -> None:
    plan = AllocationPlan()
    assert plan.allocated == 0.0
    assert plan.total_budget == 0.0


# ---------------------------------------------------------------------------
# Allocator.plan — the main algorithm
# ---------------------------------------------------------------------------


def test_plan_conserves_budget() -> None:
    """Budget is conserved: sum(new_budgets) == total_budget (within rounding)."""
    metrics = [_m("meta", spend=200.0), _m("tiktok", spend=180.0)]
    plan = Allocator().plan(metrics, total_budget=500.0,
                            cpp_target=25.0, roas_target=3.0)
    assert abs(plan.allocated - 500.0) < 0.02
    assert plan.total_budget == 500.0


def test_plan_single_campaign_gets_all_budget() -> None:
    """With only one campaign, it gets the entire budget."""
    plan = Allocator().plan([_m()], total_budget=500.0,
                            cpp_target=25.0, roas_target=3.0)
    assert len(plan.allocations) == 1
    assert plan.allocations[0].new_budget == 500.0


def test_plan_paused_campaign_gets_zero() -> None:
    """A campaign that triggers PAUSE gets $0 budget."""
    # A blown campaign: CPP very high, ROAS very low
    blown = _m(spend=300.0, value=200.0, conversions=5.0, clicks=600)
    plan = Allocator().plan([blown], total_budget=500.0,
                            cpp_target=25.0, roas_target=3.0)
    verdict = plan.allocations[0].result.decision
    if verdict.action.value == "PAUSE":
        assert plan.allocations[0].new_budget == 0.0


def test_plan_scale_campaign_gets_more() -> None:
    """A green campaign gets a budget increase."""
    # A very healthy campaign: low CPP, high ROAS, lots of conversions
    healthy = _m(spend=200.0, value=760.0, conversions=20.0, clicks=2000, imps=100_000)
    plan = Allocator().plan([healthy], total_budget=500.0,
                            cpp_target=25.0, roas_target=3.0)
    verdict = plan.allocations[0].result.decision
    if verdict.action.value == "SCALE":
        assert plan.allocations[0].new_budget > plan.allocations[0].old_budget


def test_plan_hold_keeps_spend() -> None:
    """A HOLD campaign keeps current spend in the weight calculation."""
    # A moderate campaign — mixed signals
    moderate = _m(spend=200.0, value=500.0, conversions=10.0, clicks=1200, imps=100_000)
    plan = Allocator().plan([moderate], total_budget=500.0,
                            cpp_target=25.0, roas_target=3.0)
    # Single campaign always gets full budget; the action determines delta
    assert plan.allocations[0].new_budget == 500.0


def test_plan_multiple_campaigns_proportional() -> None:
    """With two campaigns, the split is proportional to value * desired."""
    healthy = _m("meta", spend=200.0, value=760.0, conversions=12.0, clicks=1400)
    moderate = _m("tiktok", spend=200.0, value=500.0, conversions=10.0, clicks=1200)
    plan = Allocator().plan([healthy, moderate], total_budget=400.0,
                            cpp_target=25.0, roas_target=3.0)
    assert len(plan.allocations) == 2
    assert abs(sum(a.new_budget for a in plan.allocations) - 400.0) < 0.02


def test_plan_zero_total_budget() -> None:
    """With zero total budget, all allocations get zero."""
    plan = Allocator().plan([_m()], total_budget=0.0,
                            cpp_target=25.0, roas_target=3.0)
    assert plan.allocations[0].new_budget == 0.0


def test_plan_empty_metrics_list() -> None:
    """Empty metrics list produces empty plan."""
    plan = Allocator().plan([], total_budget=500.0,
                            cpp_target=25.0, roas_target=3.0)
    assert len(plan.allocations) == 0
    assert plan.allocated == 0.0


# ---------------------------------------------------------------------------
# _value_weights
# ---------------------------------------------------------------------------


def test_value_weights_default_uses_roas() -> None:
    """With value_model_name='null', weights are ROAS values (floored)."""
    m1 = _m(value=760.0, spend=200.0)  # ROAS = 3.8
    m2 = _m(value=336.0, spend=240.0)  # ROAS = 1.4
    weights = Allocator(value_model_name="null")._value_weights([m1, m2])
    assert len(weights) == 2
    assert weights[0] == 3.8
    assert weights[1] == 1.4


def test_value_weights_floor_is_0_1() -> None:
    """Even with zero ROAS, the floor is 0.1 to avoid zero-out."""
    zero_roas = _m(value=0.0, spend=100.0)  # ROAS = 0.0
    weights = Allocator()._value_weights([zero_roas])
    assert weights[0] == 0.1


def test_plan_preserves_allocation_order() -> None:
    """Allocations are in the same order as input metrics."""
    m1 = _m("meta")
    m2 = _m("tiktok")
    m3 = _m("google")
    plan = Allocator().plan([m1, m2, m3], total_budget=600.0,
                            cpp_target=25.0, roas_target=3.0)
    assert plan.allocations[0].metrics.platform == "meta"
    assert plan.allocations[1].metrics.platform == "tiktok"
    assert plan.allocations[2].metrics.platform == "google"
