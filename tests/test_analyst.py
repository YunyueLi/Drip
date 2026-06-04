"""Analyst behaviour lock — anomaly scan, decision roll-up, report generation.

Tests cover:
  - anomaly detection thresholds (frequency, CTR, ROAS)
  - report aggregation (n_campaigns, total_spend, by_action)
  - template summary and LLM fallback path

Uses the same _m()-style helpers importing from test_engine to keep fixtures
consistent across the test suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from drip.analyst import FREQ_ALARM as _FREQ
from drip.analyst import (
    Analyst,
    AnalystReport,
    Anomaly,
    CampaignVerdict,
)
from drip.data.metrics import AdMetrics

if TYPE_CHECKING:
    from drip.engine import EngineResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _healthy(label: str = "Meta_US_Prospecting") -> AdMetrics:
    """A healthy campaign: ROAS 3.8x, CTR 1.4%, low freq."""
    return AdMetrics(
        platform="meta", campaign_id="m-healthy", date_start="2026-05-01",
        date_end="2026-05-28", spend=200.0, impressions=100_000, clicks=1400,
        conversions=12.0, conversion_value=760.0, reach=56_000, label=label,
    )


def _struggling(label: str = "Meta_US_Broad") -> AdMetrics:
    """A struggling campaign: ROAS 1.4x, thin conversions, high freq."""
    return AdMetrics(
        platform="meta", campaign_id="m-broad", date_start="2026-05-01",
        date_end="2026-05-28", spend=240.0, impressions=100_000, clicks=800,
        conversions=6.0, conversion_value=336.0, reach=40_000, label=label,
    )


def _blown(label: str = "TikTok_JP_Gacha") -> AdMetrics:
    """A campaign with both CPP and ROAS blown out."""
    return AdMetrics(
        platform="tiktok", campaign_id="tt-blown", date_start="2026-05-01",
        date_end="2026-05-28", spend=300.0, impressions=80_000, clicks=600,
        conversions=5.0, conversion_value=200.0, reach=30_000, label=label,
    )


# ---------------------------------------------------------------------------
# Anomaly & Report dataclasses
# ---------------------------------------------------------------------------


def test_anomaly_fields() -> None:
    a = Anomaly("camp1", "frequency", "3.2 — audience burnout risk")
    assert a.campaign == "camp1"
    assert a.metric == "frequency"
    assert "burnout" in a.detail


def test_report_empty() -> None:
    r = AnalystReport()
    assert r.n_campaigns == 0
    assert r.total_spend == 0.0
    assert r.by_action == {}
    assert r.summary == ""


def test_report_n_campaigns() -> None:
    r = AnalystReport(verdicts=[CampaignVerdict(_healthy(), None)])
    assert r.n_campaigns == 1


def test_report_total_spend() -> None:
    r = AnalystReport(verdicts=[
        CampaignVerdict(_healthy(), None),
        CampaignVerdict(_struggling(), None),
    ])
    assert r.total_spend == 200.0 + 240.0


def test_report_by_action() -> None:
    """by_action groups verdicts by their action label."""
    from drip.engine import DecisionEngine
    engine = DecisionEngine()
    em1 = _healthy().to_engine_metrics(cpp_target=25.0, roas_target=3.0, budget_cap=1000.0)
    em2 = _struggling().to_engine_metrics(cpp_target=25.0, roas_target=3.0, budget_cap=1000.0)
    r = AnalystReport(verdicts=[
        CampaignVerdict(_healthy(), engine.run(em1)),
        CampaignVerdict(_struggling(), engine.run(em2)),
    ])
    counts = r.by_action
    assert isinstance(counts, dict)
    assert sum(counts.values()) == 2


# ---------------------------------------------------------------------------
# _scan — anomaly detection
# ---------------------------------------------------------------------------


def test_scan_healthy_campaign_no_anomalies() -> None:
    a = Analyst()
    anoms = a._scan(_healthy())
    assert len(anoms) == 0


def test_scan_high_frequency_flags_anomaly() -> None:
    a = Analyst()
    m = _healthy()
    m.reach = 1  # frequency = 100000/1 = very high
    m.impressions = int(_FREQ * 100 + 1)
    anoms = a._scan(m)
    freqs = [x for x in anoms if x.metric == "frequency"]
    assert len(freqs) >= 1
    assert "burnout" in freqs[0].detail


def test_scan_low_ctr_flags_anomaly() -> None:
    a = Analyst()
    m = _healthy()
    m.impressions = 10_000
    m.clicks = 1  # CTR = 0.01% — well below CTR_FLOOR
    anoms = a._scan(m)
    ctrs = [x for x in anoms if x.metric == "ctr"]
    assert len(ctrs) >= 1
    assert "creative" in ctrs[0].detail.lower()


def test_scan_zero_impressions_no_ctr_flag() -> None:
    """CTR check skips when impressions == 0 (avoid false positive)."""
    a = Analyst()
    m = _healthy()
    m.impressions = 0
    m.clicks = 0
    anoms = a._scan(m)
    assert all(x.metric != "ctr" for x in anoms)


def test_scan_roas_below_floor_flags_anomaly() -> None:
    a = Analyst()
    m = _healthy()
    m.conversion_value = 50.0   # ROAS = 50/200 = 0.25x < ROAS_FLOOR
    anoms = a._scan(m)
    roas_anoms = [x for x in anoms if x.metric == "roas"]
    assert len(roas_anoms) >= 1
    assert "losing" in roas_anoms[0].detail.lower()


def test_scan_zero_roas_no_flag() -> None:
    """ROAS == 0 should not flag (condition is 0 < roas < floor)."""
    a = Analyst()
    m = _healthy()
    m.conversion_value = 0.0
    m.spend = 200.0  # ROAS = 0.0
    anoms = a._scan(m)
    assert all(x.metric != "roas" for x in anoms)


def test_scan_multiple_anomalies_on_struggling() -> None:
    a = Analyst()
    # A truly broken campaign: ROAS 0.5x, CTR 0.1%, freq 5.0
    broken = AdMetrics(
        platform="meta", campaign_id="broken", date_start="2026-05-01",
        date_end="2026-05-28", spend=200.0, impressions=100_00, clicks=10,
        conversions=2.0, conversion_value=100.0, reach=2_000, label="Broken",
    )
    anoms = a._scan(broken)
    # Should trigger: frequency (5.0 > 3.0 alarm), CTR (0.1% < 0.5% floor),
    # ROAS (0.5x < 1.0x floor)
    assert len(anoms) >= 2


# ---------------------------------------------------------------------------
# _template — deterministic summary fallback
# ---------------------------------------------------------------------------


def _run_engine(m: AdMetrics) -> EngineResult:
    from drip.engine import DecisionEngine
    em = m.to_engine_metrics(cpp_target=25.0, roas_target=3.0, budget_cap=1000.0)
    return DecisionEngine().run(em)


def test_template_no_anomalies() -> None:
    a = Analyst()
    r = AnalystReport(
        verdicts=[CampaignVerdict(_healthy(), _run_engine(_healthy()))],
        anomalies=[],
    )
    result = a._template(r)
    assert "Scanned" in result
    assert "No anomalies" in result


def test_template_with_anomalies() -> None:
    a = Analyst()
    r = AnalystReport(
        verdicts=[CampaignVerdict(_healthy(), _run_engine(_healthy()))],
        anomalies=[
            Anomaly("camp1", "frequency", "3.2 burnout"),
            Anomaly("camp1", "ctr", "0.2% below floor"),
        ],
    )
    result = a._template(r)
    assert "2 anomalies" in result
    assert "camp1 frequency" in result
    assert "camp1 ctr" in result


def test_template_more_than_three_anomalies_truncates() -> None:
    a = Analyst()
    anoms = [Anomaly(f"c{i}", "freq", "test") for i in range(5)]
    r = AnalystReport(
        verdicts=[CampaignVerdict(_healthy(), _run_engine(_healthy()))],
        anomalies=anoms,
    )
    result = a._template(r)
    assert "5 anomalies" in result
    assert "…" in result  # truncation ellipsis


def test_template_no_verdicts() -> None:
    a = Analyst()
    r = AnalystReport()
    result = a._template(r)
    assert "0 campaigns" in result or "Scanned 0" in result


# ---------------------------------------------------------------------------
# _summarize — LLM or template
# ---------------------------------------------------------------------------


def test_summarize_no_model_uses_template() -> None:
    """Without a narrate_model, _summarize must call _template."""
    a = Analyst(narrate_model=None)
    m = _healthy()
    em = m.to_engine_metrics(cpp_target=25.0, roas_target=3.0, budget_cap=1000.0)
    r = AnalystReport(
        verdicts=[CampaignVerdict(m, a.engine.run(em))],
    )
    summary = a._summarize(r)
    assert len(summary) > 0
    assert "Scanned" in summary  # template output


# ---------------------------------------------------------------------------
# analyze — full integration (no LLM)
# ---------------------------------------------------------------------------


def test_analyze_with_offline_defaults() -> None:
    """Full analyze() runs without LLM — all template paths."""
    a = Analyst()
    report = a.analyze(
        [_healthy(), _struggling()],
        cpp_target=25.0, roas_target=3.0, budget_cap=1000.0,
    )
    assert report.n_campaigns == 2
    assert report.total_spend == 440.0
    assert len(report.verdicts) == 2
    assert len(report.summary) > 0
    # Each verdict has a decision + signal vector
    for v in report.verdicts:
        assert v.result.decision is not None
        assert v.result.signals is not None


def test_analyze_single_campaign() -> None:
    a = Analyst()
    report = a.analyze(
        [_healthy()],
        cpp_target=25.0, roas_target=3.0, budget_cap=1000.0,
    )
    assert report.n_campaigns == 1
    assert report.total_spend == 200.0


def test_analyze_empty_metrics() -> None:
    a = Analyst()
    report = a.analyze([], cpp_target=25.0, roas_target=3.0, budget_cap=1000.0)
    assert report.n_campaigns == 0
    assert report.total_spend == 0.0
    assert report.summary  # template still produces output


def test_analyze_with_custom_baselines() -> None:
    """cvr_baseline and ctr_baseline are forwarded to engine metrics."""
    a = Analyst()
    report = a.analyze(
        [_healthy()],
        cpp_target=25.0, roas_target=3.0, budget_cap=1000.0,
        cvr_baseline=0.030, ctr_baseline=0.020,
    )
    assert report.n_campaigns == 1


def test_analyst_accepts_custom_engine() -> None:
    from drip.engine import DecisionEngine, Thresholds
    t = Thresholds(cpp_red_ratio=1.5)  # more permissive
    engine = DecisionEngine(thresholds=t)
    a = Analyst(engine=engine)
    report = a.analyze(
        [_healthy()],
        cpp_target=25.0, roas_target=3.0, budget_cap=1000.0,
    )
    assert report.n_campaigns == 1
