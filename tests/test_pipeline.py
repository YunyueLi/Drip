"""End-to-end pipeline smoke tests — the one-stop loop runs on samples.

Pure offline (samples + templates + dry generator), so these run in CI with
no credentials. They lock the loop behaviour: budget conservation, winner
variants, feedback signals.
"""

from __future__ import annotations

from drip.pipeline import Pipeline


def test_pipeline_runs_end_to_end() -> None:
    r = Pipeline(total_budget=1000.0).run(since="2026-05-01", until="2026-05-28")
    assert r.report.n_campaigns == 4
    assert r.report.total_spend == 880
    assert len(r.variants) == 3            # winner gets variants
    assert r.feedback.platform_roas        # feedback produced learnings/signals


def test_allocation_conserves_budget() -> None:
    r = Pipeline(total_budget=500.0).run(since="2026-05-01", until="2026-05-28")
    assert abs(r.plan.allocated - 500.0) < 0.01


def test_losers_get_zero_budget() -> None:
    r = Pipeline().run(since="2026-05-01", until="2026-05-28")
    pauses = [a for a in r.plan.allocations if a.reason == "PAUSE"]
    assert pauses
    assert all(a.new_budget == 0 for a in pauses)


def test_winners_get_funded() -> None:
    r = Pipeline().run(since="2026-05-01", until="2026-05-28")
    scales = [a for a in r.plan.allocations if a.reason == "SCALE"]
    assert scales
    assert all(a.new_budget > 0 for a in scales)
