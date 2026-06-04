"""Feedback behaviour lock — loop closing, learnings, platform weighting.

Tests cover:
  - platform_roas aggregation
  - platform_weights normalisation
  - learning generation (best/worst platform, winner CTR bar)
  - edge cases: single platform, all losers, zero ROAS
"""

from __future__ import annotations

from drip.data.metrics import AdMetrics
from drip.feedback import FeedbackLoop, FeedbackResult, Learning

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _m(platform: str = "meta", spend: float = 200.0,
       conversions: float = 12.0, value: float = 760.0,
       clicks: int = 1400, imps: int = 100_000, label: str = "") -> AdMetrics:
    return AdMetrics(
        platform=platform, campaign_id=f"{platform}-001",
        date_start="2026-05-01", date_end="2026-05-28",
        spend=spend, impressions=imps, clicks=clicks,
        conversions=conversions, conversion_value=value,
        reach=50_000, label=label or f"{platform}_test",
    )


# ---------------------------------------------------------------------------
# FeedbackResult
# ---------------------------------------------------------------------------


def test_feedback_result_empty() -> None:
    r = FeedbackResult()
    assert r.platform_roas == {}
    assert r.learnings == []
    assert r.platform_weights == {}


def test_platform_weights_normalise() -> None:
    r = FeedbackResult(platform_roas={"meta": 3.8, "tiktok": 1.2})
    w = r.platform_weights
    total = 3.8 + 1.2
    assert w["meta"] == round(3.8 / total, 3)
    assert w["tiktok"] == round(1.2 / total, 3)


def test_platform_weights_zero_sum() -> None:
    """When all platform ROAS are 0, weights default to 1.0 each."""
    r = FeedbackResult(platform_roas={"meta": 0.0, "tiktok": 0.0})
    w = r.platform_weights
    assert w["meta"] == 1.0
    assert w["tiktok"] == 1.0


def test_platform_weights_single_platform() -> None:
    r = FeedbackResult(platform_roas={"meta": 3.8})
    w = r.platform_weights
    assert w["meta"] == 1.0


# ---------------------------------------------------------------------------
# FeedbackLoop.review
# ---------------------------------------------------------------------------


def test_review_aggregates_platform_roas() -> None:
    m1 = _m("meta", value=760.0, spend=200.0)       # ROAS 3.8
    m2 = _m("meta", value=660.0, spend=200.0)       # ROAS 3.3
    m3 = _m("tiktok", value=400.0, spend=200.0)     # ROAS 2.0
    result = FeedbackLoop().review([m1, m2, m3])
    assert "meta" in result.platform_roas
    assert "tiktok" in result.platform_roas
    # meta avg = (3.8+3.3)/2 = 3.55
    assert result.platform_roas["meta"] == round((3.8 + 3.3) / 2, 2)
    assert result.platform_roas["tiktok"] == 2.0


def test_review_single_platform_no_platform_learning() -> None:
    """With only one platform, there's no cross-platform comparison."""
    result = FeedbackLoop().review([_m("meta")])
    assert len(result.platform_roas) == 1
    # No cross-platform learning
    assert not any("outperforms" in lrn.insight for lrn in result.learnings)


def test_review_best_vs_worst_platform_learning() -> None:
    """Two platforms with different ROAS → cross-platform learning."""
    m1 = _m("meta", value=760.0, spend=200.0, label="best")    # ROAS 3.8
    m2 = _m("tiktok", value=240.0, spend=200.0, label="worst")  # ROAS 1.2
    result = FeedbackLoop().review([m1, m2])
    cross = [lrn for lrn in result.learnings if "outperforms" in lrn.insight]
    assert len(cross) == 1
    assert "meta" in cross[0].insight
    assert "tiktok" in cross[0].insight
    assert cross[0].signal["shift_to"] == "meta"


def test_review_equal_platform_roas_no_cross_learning() -> None:
    """If best == worst ROAS, no cross-platform learning is generated."""
    m1 = _m("meta", value=600.0, spend=200.0)      # ROAS 3.0
    m2 = _m("tiktok", value=600.0, spend=200.0)    # ROAS 3.0
    result = FeedbackLoop().review([m1, m2])
    assert not any("outperforms" in lrn.insight for lrn in result.learnings)


def test_review_winners_set_ctr_bar() -> None:
    """Campaigns above ROAS target set the CTR bar for next creatives."""
    m1 = _m("meta", value=760.0, spend=200.0, clicks=1400, imps=100_000)  # CTR 1.4%
    m2 = _m("meta", value=660.0, spend=200.0, clicks=1600, imps=100_000)  # CTR 1.6%
    result = FeedbackLoop(roas_target=3.0).review([m1, m2])
    ctr_learnings = [lrn for lrn in result.learnings if "CTR" in lrn.insight]
    assert len(ctr_learnings) == 1
    # Avg CTR = (0.014+0.016)/2 = 0.015
    assert "winner_ctr_bar" in ctr_learnings[0].signal


def test_review_no_winners_no_ctr_learning() -> None:
    """When no campaign meets ROAS target, no CTR bar learning."""
    m = _m(value=200.0, spend=200.0)  # ROAS 1.0 — below target
    result = FeedbackLoop(roas_target=3.0).review([m])
    assert not any("CTR" in lrn.insight for lrn in result.learnings)


def test_review_empty_metrics() -> None:
    result = FeedbackLoop().review([])
    assert result.platform_roas == {}
    assert result.learnings == []


def test_review_custom_roas_target() -> None:
    """ROAS target affects winner classification."""
    m = _m(value=500.0, spend=200.0)  # ROAS 2.5
    # With target 3.0, this is a loser
    r1 = FeedbackLoop(roas_target=3.0).review([m])
    assert not any("CTR" in lrn.insight for lrn in r1.learnings)
    # With target 2.0, this is a winner
    r2 = FeedbackLoop(roas_target=2.0).review([m])
    assert any("CTR" in lrn.insight for lrn in r2.learnings)


def test_learning_structure() -> None:
    learning = Learning(insight="test insight", signal={"key": "value"})
    assert learning.insight == "test insight"
    assert learning.signal == {"key": "value"}
