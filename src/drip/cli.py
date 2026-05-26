"""drip CLI — `drip launch`, `drip demo`, `drip eval`."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from drip import __version__
from drip.orchestrator import DripOrchestrator, GameSpec, RunMode

console = Console()


def _load_env() -> None:
    load_dotenv()


def _read_game(path: Path) -> GameSpec:
    if not path.exists():
        raise click.ClickException(f"game spec not found: {path}")
    data = yaml.safe_load(path.read_text())
    return GameSpec.model_validate(data)


@click.group()
@click.version_option(__version__, "-V", "--version")
def main() -> None:
    """drip — autonomous UA agent for anime / gacha mobile games."""
    _load_env()


@main.command()
@click.option("--game", "game_path", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to game spec YAML (see examples/demo_game.yaml).")
@click.option("--budget", type=float, required=True, help="Total USD budget for this run.")
@click.option("--regions", required=True, help="Comma-separated region codes, e.g. jp,sg,tw.")
@click.option("--mode", type=click.Choice([m.value for m in RunMode]),
              default=None, help="Override DRIP_MODE env var.")
@click.option("--dry-run", is_flag=True, help="Plan only, do not call any external API.")
def launch(game_path: Path, budget: float, regions: str, mode: str | None, dry_run: bool) -> None:
    """Launch an end-to-end UA run."""
    game = _read_game(game_path)
    region_list = [r.strip() for r in regions.split(",") if r.strip()]
    mode_enum = RunMode(mode) if mode else RunMode(os.getenv("DRIP_MODE", "shadow"))

    cap = float(os.getenv("DRIP_BUDGET_CAP", "0") or 0)
    if cap and budget > cap:
        raise click.ClickException(
            f"requested budget ${budget:.2f} exceeds DRIP_BUDGET_CAP ${cap:.2f}"
        )

    console.print(Panel.fit(
        f"[bold]{game.title}[/bold]  ·  ${budget:,.0f}  ·  {', '.join(region_list)}\n"
        f"mode = [yellow]{mode_enum.value}[/yellow]   dry-run = {dry_run}",
        title="drip launch", border_style="bright_black",
    ))

    orchestrator = DripOrchestrator(mode=mode_enum, dry_run=dry_run)
    try:
        asyncio.run(orchestrator.run(game=game, budget=budget, regions=region_list))
    except KeyboardInterrupt:
        console.print("[red]interrupted[/red]")
        sys.exit(130)


@main.command()
def demo() -> None:
    """Run a dry-run against the bundled demo game (no API calls)."""
    demo_path = Path(__file__).resolve().parents[2] / "examples" / "demo_game.yaml"
    game = _read_game(demo_path)
    console.print(Panel.fit(f"running demo: {game.title}", border_style="bright_black"))
    orchestrator = DripOrchestrator(mode=RunMode.SHADOW, dry_run=True)
    asyncio.run(orchestrator.run(game=game, budget=500.0, regions=["jp", "sg", "tw"]))


@main.command()
@click.option("--suite", default="v0", help="Bench suite to run.")
def eval(suite: str) -> None:
    """Run Drip-Bench evaluation."""
    from drip.eval.bench import run_bench
    run_bench(suite=suite)


if __name__ == "__main__":
    main()
