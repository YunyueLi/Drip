"""Collector behaviour lock — platform fetch + normalisation.

Tests cover:
  - _parse_action edge cases (Meta actions[] parsing)
  - Collector with default sources (sample data)
  - Collector with custom sources
  - _sample determinism
"""

from __future__ import annotations

from drip.collectors import (
    Collector,
    KuaishouInsights,
    MetaInsights,
    OceanEngineInsights,
    TencentInsights,
    TikTokInsights,
    _parse_action,
    _sample,
)
from drip.data.metrics import AdMetrics

# ---------------------------------------------------------------------------
# _parse_action
# ---------------------------------------------------------------------------


def test_parse_action_pulls_purchase_values() -> None:
    actions = [
        {"action_type": "purchase", "value": "150.00"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "50.00"},
        {"action_type": "click", "value": "999"},
    ]
    total = _parse_action(actions, "purchase")
    assert total == 200.0


def test_parse_action_matches_suffix() -> None:
    actions = [{"action_type": "some.nested.purchase", "value": "75.5"}]
    assert _parse_action(actions, "purchase") == 75.5


def test_parse_action_not_a_list() -> None:
    assert _parse_action(None, "purchase") == 0.0
    assert _parse_action("not a list", "purchase") == 0.0


def test_parse_action_empty_list() -> None:
    assert _parse_action([], "purchase") == 0.0


def test_parse_action_no_value_field() -> None:
    actions = [{"action_type": "purchase"}]
    assert _parse_action(actions, "purchase") == 0.0


def test_parse_action_unrelated_types() -> None:
    actions = [
        {"action_type": "click", "value": "100"},
        {"action_type": "impression", "value": "200"},
    ]
    assert _parse_action(actions, "purchase") == 0.0


def test_parse_action_mixed_types() -> None:
    actions = [
        {"action_type": "purchase", "value": 100},
        {"action_type": "offsite_conversion", "value": 200},
    ]
    # Only the first matches purchase (exact match); offsite_conversion
    # doesn't end with ".purchase" so it's skipped
    result = _parse_action(actions, "purchase")
    assert result >= 100.0  # at minimum the exact match


# ---------------------------------------------------------------------------
# _sample
# ---------------------------------------------------------------------------


def test_sample_returns_two_rows_per_platform() -> None:
    rows = _sample("meta", "2026-05-01", "2026-05-28")
    assert len(rows) == 2  # deterministic: healthy + struggling
    assert all(isinstance(r, AdMetrics) for r in rows)


def test_sample_is_deterministic() -> None:
    a = _sample("meta", "2026-05-01", "2026-05-28")
    b = _sample("meta", "2026-05-01", "2026-05-28")
    for ra, rb in zip(a, b, strict=True):
        assert ra.campaign_id == rb.campaign_id
        assert ra.spend == rb.spend


def test_sample_different_platforms_differ() -> None:
    meta = _sample("meta", "2026-05-01", "2026-05-28")
    tiktok = _sample("tiktok", "2026-05-01", "2026-05-28")
    assert meta[0].campaign_id != tiktok[0].campaign_id


def test_sample_healthy_has_higher_roas() -> None:
    rows = _sample("meta", "2026-05-01", "2026-05-28")
    # The first row is the "healthy" variant
    assert rows[0].roas > rows[1].roas


# ---------------------------------------------------------------------------
# Source constructors — offline fallback
# ---------------------------------------------------------------------------


def test_meta_insights_offline() -> None:
    src = MetaInsights(account_id=None, token=None)
    assert src.platform == "meta"
    rows = src.fetch(since="2026-05-01", until="2026-05-28")
    assert len(rows) == 2  # sample fallback


def test_tiktok_insights_offline() -> None:
    src = TikTokInsights(advertiser_id=None, token=None)
    assert src.platform == "tiktok"
    rows = src.fetch(since="2026-05-01", until="2026-05-28")
    assert len(rows) == 2  # sample fallback


def test_tencent_insights_offline() -> None:
    src = TencentInsights()
    assert src.platform == "tencent"
    rows = src.fetch(since="2026-05-01", until="2026-05-28")
    assert len(rows) == 1  # China platforms return 1 sample


def test_oceanengine_insights_offline() -> None:
    src = OceanEngineInsights()
    assert src.platform == "oceanengine"
    rows = src.fetch(since="2026-05-01", until="2026-05-28")
    assert len(rows) == 1


def test_kuaishou_insights_offline() -> None:
    src = KuaishouInsights()
    assert src.platform == "kuaishou"
    rows = src.fetch(since="2026-05-01", until="2026-05-28")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


def test_collector_default_sources() -> None:
    c = Collector()
    assert len(c.sources) == 5  # meta + tiktok + 3 china


def test_collector_fans_out_to_all_sources() -> None:
    c = Collector()
    rows = c.collect(since="2026-05-01", until="2026-05-28")
    # 2+2+1+1+1 = 7 total
    assert len(rows) == 7
    platforms = {r.platform for r in rows}
    assert platforms >= {"meta", "tiktok", "tencent", "oceanengine", "kuaishou"}


def test_collector_with_custom_sources() -> None:
    c = Collector(sources=[MetaInsights()])
    rows = c.collect(since="2026-05-01", until="2026-05-28")
    assert len(rows) == 2
    assert all(r.platform == "meta" for r in rows)


def test_collector_empty_sources_falls_back_to_defaults() -> None:
    """Passing an empty list triggers the default-source fallback (falsy check)."""
    c = Collector(sources=[])
    rows = c.collect(since="2026-05-01", until="2026-05-28")
    # Empty list is falsy → Collector substitutes the 5 default sources
    assert len(rows) == 7
    platforms = {r.platform for r in rows}
    assert platforms >= {"meta", "tiktok", "tencent", "oceanengine", "kuaishou"}
