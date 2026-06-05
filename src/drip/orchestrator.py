"""Drip orchestrator — deterministic pipeline over the worker pool (Agent-SDK supervisor is the v0.2 direction).

Design:
- The orchestrator owns the run lifecycle and budget. Each worker is a domain
  expert that reports structured results back. The orchestrator decides what
  comes next based on those results and the budget remaining.
- Real ad-platform calls only happen when mode != SHADOW. In SHADOW mode the
  Bidding worker plans actions but does not execute them, which is the safe
  default for week-1 demos.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from drip.workers.audience import AudienceWorker
from drip.workers.base import WorkerResult
from drip.workers.bidding import BiddingWorker
from drip.workers.creative import CreativeWorker
from drip.workers.reporter import ReporterWorker

console = Console()


class RunMode(str, Enum):
    SHADOW = "shadow"        # plan-only, no platform writes
    COPILOT = "copilot"      # writes require human approval
    AUTONOMOUS = "autonomous"  # writes freely up to budget caps


class GameSpec(BaseModel):
    """User-supplied description of the campaign subject.

    The defaults below are intentionally generic so the spec applies
    across mobile games, DTC products, or B2B apps. Verticals (anime /
    gacha, DTC, tools-app) ship as Knowledge Packs that override these
    defaults via prompt + signal injection — see ``packs/`` (v0.1).
    """

    title: str
    genre: str = "mobile-game"
    art_style: str = "default"
    target_audience: str = "general adult mobile audience"
    key_characters: list[str] = Field(default_factory=list)
    store_links: dict[str, str] = Field(default_factory=dict)  # {ios:..., android:...}
    creative_brief: str = ""


@dataclass
class RunContext:
    game: GameSpec
    budget_usd: float
    regions: list[str]
    mode: RunMode
    dry_run: bool
    spent_usd: float = 0.0
    artifacts: dict[str, Any] = field(default_factory=dict)


class DripOrchestrator:
    """Top-level orchestrator over the worker pool. Deterministic pipeline today; the Agent-SDK supervisor pattern is the v0.2 plan.

    Today this is a deterministic pipeline (creative → audience → bidding →
    reporter). In v0.2 we replace the fixed order with an Agent-SDK-driven
    supervisor that can re-route based on intermediate signals.
    """

    def __init__(self, mode: RunMode = RunMode.SHADOW, dry_run: bool = False) -> None:
        self.mode = mode
        self.dry_run = dry_run
        self.creative = CreativeWorker()
        self.audience = AudienceWorker()
        self.bidding = BiddingWorker()
        self.reporter = ReporterWorker()

    async def run(self, game: GameSpec, budget: float, regions: list[str]) -> RunContext:
        ctx = RunContext(
            game=game, budget_usd=budget, regions=regions,
            mode=self.mode, dry_run=self.dry_run,
        )

        await self._step("creative", self.creative.run(ctx))
        await self._step("audience", self.audience.run(ctx))
        await self._step("bidding", self.bidding.run(ctx))
        await self._step("reporter", self.reporter.run(ctx))

        self._final_summary(ctx)
        return ctx

    async def _step(self, name: str, coro: Any) -> WorkerResult:
        console.print(f"\n[bold cyan]▸ {name}[/bold cyan]")
        result: WorkerResult = await coro
        for line in result.lines:
            console.print(f"  {line}")
        return result

    def _final_summary(self, ctx: RunContext) -> None:
        table = Table(title="drip · run summary", show_header=False, border_style="bright_black")
        table.add_row("game", ctx.game.title)
        table.add_row("regions", ", ".join(ctx.regions))
        table.add_row("budget", f"${ctx.budget_usd:,.2f}")
        table.add_row("spent (planned)", f"${ctx.spent_usd:,.2f}")
        table.add_row("mode", ctx.mode.value)
        for k, v in ctx.artifacts.items():
            table.add_row(k, str(v))
        console.print(table)


async def _demo() -> None:  # pragma: no cover — for `python -m drip.orchestrator`
    game = GameSpec(title="Sample Mobile Game", creative_brief="generic launch demo")
    await DripOrchestrator(mode=RunMode.SHADOW, dry_run=True).run(
        game=game, budget=500, regions=["jp", "sg", "tw"]
    )


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_demo())
