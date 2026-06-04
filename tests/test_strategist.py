"""Strategist behaviour lock — winner/loser ranking + creative brief generation.

Tests cover:
  - winner/loser classification by ROAS threshold
  - hypothesis generation for top winner and worst loser
  - _brief template fallback (no LLM)
  - edge cases: empty list, all winners, all losers
"""

from __future__ import annotations

from drip.data.metrics import AdMetrics
from drip.strategist import Strategist, StrategyOutput

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


def _healthy() -> AdMetrics:
    return _m(spend=200.0, value=760.0, conversions=12.0, clicks=1400, label="Healthy_US")


def _struggling() -> AdMetrics:
    return _m(spend=240.0, value=336.0, conversions=6.0, clicks=800, label="Struggling_US")


# ---------------------------------------------------------------------------
# StrategyOutput
# ---------------------------------------------------------------------------


def test_strategy_output_empty() -> None:
    s = StrategyOutput()
    assert s.winners == []
    assert s.losers == []
    assert s.hypotheses == []


# ---------------------------------------------------------------------------
# propose — winner/loser classification
# ---------------------------------------------------------------------------


def test_propose_classifies_winners_and_losers() -> None:
    s = Strategist().propose([_healthy(), _struggling()], roas_target=3.0)
    assert len(s.winners) == 1
    assert s.winners[0].label == "Healthy_US"
    assert len(s.losers) == 1
    assert s.losers[0].label == "Struggling_US"


def test_propose_all_winners_when_all_above_target() -> None:
    m1 = _m(value=760.0, spend=200.0, label="W1")   # ROAS 3.8
    m2 = _m(value=700.0, spend=200.0, label="W2")   # ROAS 3.5
    s = Strategist().propose([m1, m2], roas_target=3.0)
    assert len(s.winners) == 2
    assert len(s.losers) == 0
    # Still get a scale_winner hypothesis for the top one
    assert any(h.direction == "scale_winner" for h in s.hypotheses)
    assert not any(h.direction == "cut_loser" for h in s.hypotheses)


def test_propose_all_losers_when_all_below_target() -> None:
    m1 = _m(value=200.0, spend=200.0, label="L1")   # ROAS 1.0
    m2 = _m(value=300.0, spend=200.0, label="L2")   # ROAS 1.5
    s = Strategist().propose([m1, m2], roas_target=3.0)
    assert len(s.winners) == 0
    assert len(s.losers) == 2
    # Still get a cut_loser hypothesis for the worst one
    assert any(h.direction == "cut_loser" for h in s.hypotheses)


def test_propose_empty_metrics() -> None:
    s = Strategist().propose([], roas_target=3.0)
    assert s.winners == []
    assert s.losers == []
    assert s.hypotheses == []


def test_propose_single_winner() -> None:
    s = Strategist().propose([_healthy()], roas_target=3.0)
    assert len(s.winners) == 1
    assert len(s.losers) == 0
    assert len(s.hypotheses) == 1
    assert s.hypotheses[0].direction == "scale_winner"


def test_propose_single_loser() -> None:
    s = Strategist().propose([_struggling()], roas_target=3.0)
    assert len(s.winners) == 0
    assert len(s.losers) == 1
    assert len(s.hypotheses) == 1
    assert s.hypotheses[0].direction == "cut_loser"


# ---------------------------------------------------------------------------
# Hypothesis structure
# ---------------------------------------------------------------------------


def test_hypothesis_fields() -> None:
    s = Strategist().propose([_healthy()], roas_target=3.0)
    h = s.hypotheses[0]
    assert h.direction == "scale_winner"
    assert h.target == "Healthy_US"
    assert "ROAS" in h.rationale
    assert len(h.brief) > 0


def test_hypothesis_roas_target_respected() -> None:
    """ROAS exactly at target counts as winner."""
    m = _m(value=600.0, spend=200.0, label="Edge")  # ROAS exactly 3.0
    s = Strategist().propose([m], roas_target=3.0)
    assert len(s.winners) == 1


# ---------------------------------------------------------------------------
# _brief — template fallback
# ---------------------------------------------------------------------------


def test_brief_scale_winner_template() -> None:
    """Without LLM, scale_winner brief uses the template."""
    s = Strategist(narrate_model=None)
    m = _healthy()
    brief = s._brief("scale_winner", m, 3.0)
    assert "Double down" in brief
    assert m.label in brief
    assert "3 variants" in brief


def test_brief_cut_loser_template() -> None:
    s = Strategist(narrate_model=None)
    m = _struggling()
    brief = s._brief("cut_loser", m, 3.0)
    assert "Cut" in brief
    assert m.label in brief
    assert "different hook" in brief.lower() or "different" in brief.lower()


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_propose_winners_sorted_by_roas_desc() -> None:
    m1 = _m(value=700.0, spend=200.0, label="Mid")   # ROAS 3.5
    m2 = _m(value=840.0, spend=200.0, label="Top")   # ROAS 4.2
    s = Strategist().propose([m1, m2], roas_target=3.0)
    assert s.winners[0].label == "Top"     # highest ROAS first
    assert s.winners[1].label == "Mid"


def test_propose_top_winner_is_hypothesis_target() -> None:
    m1 = _m(value=700.0, spend=200.0, label="Mid")
    m2 = _m(value=840.0, spend=200.0, label="Top")
    s = Strategist().propose([m1, m2], roas_target=3.0)
    scale_h = [h for h in s.hypotheses if h.direction == "scale_winner"]
    assert len(scale_h) == 1
    assert scale_h[0].target == "Top"
