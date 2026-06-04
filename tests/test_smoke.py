"""Smoke tests — ensure the CLI is wired and the demo pipeline doesn't crash."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from drip.orchestrator import DripOrchestrator, GameSpec, RunMode


def test_import_package() -> None:
    import drip

    assert drip.__version__


def test_game_spec_parses() -> None:
    demo_path = Path(__file__).resolve().parents[1] / "examples" / "demo_game.yaml"
    data = yaml.safe_load(demo_path.read_text(encoding="utf-8"))
    spec = GameSpec.model_validate(data)
    assert spec.title
    assert spec.key_characters


def test_demo_pipeline_runs_dry() -> None:
    """The dry-run pipeline must not touch any external service."""
    demo_path = Path(__file__).resolve().parents[1] / "examples" / "demo_game.yaml"
    spec = GameSpec.model_validate(yaml.safe_load(demo_path.read_text(encoding="utf-8")))
    orch = DripOrchestrator(mode=RunMode.SHADOW, dry_run=True)
    ctx = asyncio.run(orch.run(game=spec, budget=500.0, regions=["jp", "sg"]))
    assert ctx.artifacts.get("creatives")
    assert ctx.artifacts.get("bidding_plan")
    assert ctx.spent_usd == 0.0  # shadow + dry_run never spends


@pytest.mark.parametrize("mode", list(RunMode))
def test_modes_round_trip(mode: RunMode) -> None:
    assert RunMode(mode.value) is mode
