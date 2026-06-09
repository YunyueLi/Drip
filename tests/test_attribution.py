"""Attribution behaviour lock — reconcile platform-reported vs MMP truth.

Covers the documented-haircut path, the MMP-truth path (inflation flag), the
over-investment frequency flag, and the unknown-platform default haircut.
"""

from __future__ import annotations

from drip.attribution import FREQ_OVERINVEST, PLATFORM_INFLATION, Attribution
from drip.data.metrics import AdMetrics


def _m(
    *,
    platform: str = "meta",
    campaign_id: str = "c1",
    spend: float = 100.0,
    conversion_value: float = 300.0,
    impressions: int = 1000,
    reach: int = 1000,
    label: str = "Camp",
) -> AdMetrics:
    return AdMetrics(
        platform=platform, campaign_id=campaign_id,
        date_start="2026-05-01", date_end="2026-05-07",
        spend=spend, impressions=impressions, clicks=100,
        conversions=10.0, conversion_value=conversion_value,
        reach=reach, label=label,
    )


def test_no_mmp_applies_documented_haircut() -> None:
    # roas = 300/100 = 3.0; meta haircut 0.18 → 2.46.
    [d] = Attribution().reconcile([_m(platform="meta")])
    assert d.platform_roas == 3.0
    assert d.mmp_roas is None
    assert d.adjusted_roas == round(3.0 * (1 - PLATFORM_INFLATION["meta"]), 2)
    assert d.flag == ""
    assert "haircut" in d.note


def test_unknown_platform_uses_default_haircut() -> None:
    # Unknown platform → 15% default haircut.
    [d] = Attribution().reconcile([_m(platform="snapchat")])
    assert d.adjusted_roas == round(3.0 * (1 - 0.15), 2)


def test_mmp_truth_flags_inflation() -> None:
    # Platform 3.0x but MMP truth 2.0x (3.0 > 2.0*1.1) → inflated; adjusted = truth.
    [d] = Attribution().reconcile([_m()], mmp_roas_by_campaign={"c1": 2.0})
    assert d.mmp_roas == 2.0
    assert d.adjusted_roas == 2.0
    assert d.flag == "inflated"


def test_mmp_truth_close_enough_not_flagged() -> None:
    # Platform 3.0x, MMP 2.9x — within 10% → not inflated.
    [d] = Attribution().reconcile([_m()], mmp_roas_by_campaign={"c1": 2.9})
    assert d.flag == ""


def test_high_frequency_flags_over_investment() -> None:
    # frequency = impressions/reach = 3000/1000 = 3.0 > 2.5 cap.
    [d] = Attribution().reconcile([_m(impressions=3000, reach=1000)])
    assert d.flag == "over_investment"
    assert str(FREQ_OVERINVEST) in d.note


def test_reconcile_preserves_order_and_count() -> None:
    metrics = [_m(campaign_id="a", label="A"), _m(campaign_id="b", label="B")]
    out = Attribution().reconcile(metrics)
    assert [d.campaign for d in out] == ["A", "B"]
