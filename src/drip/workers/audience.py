"""Audience worker — pre-flight reaction simulation via OASIS.

Spawns N synthetic anime gachas with personality + memory, exposes each ad
candidate to them, and reports a predicted CTR distribution before any real
budget is spent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from drip.adapters.simulation import SimulationAdapter
from drip.workers.base import Worker, WorkerResult

if TYPE_CHECKING:
    from drip.orchestrator import RunContext


DEFAULT_SIM_SIZE = 5_000


class AudienceWorker(Worker):
    name = "audience"
    model = "claude-sonnet-4-6"

    def __init__(self) -> None:
        self.sim = SimulationAdapter.default()

    async def run(self, ctx: "RunContext") -> WorkerResult:
        lines: list[str] = []

        creatives = ctx.artifacts.get("creatives", [])
        if not creatives:
            lines.append("no creatives to evaluate — skipping")
            return WorkerResult(lines=lines)

        predictions = []
        for creative in creatives:
            pred = await self.sim.predict_reaction(
                creative=creative,
                regions=ctx.regions,
                audience_size=DEFAULT_SIM_SIZE,
                dry_run=ctx.dry_run,
            )
            predictions.append({"concept": creative["concept"], **pred})

        # rank by predicted CTR
        predictions.sort(key=lambda p: p.get("ctr", 0.0), reverse=True)
        top = predictions[:3]

        lines.append(f"simulated {DEFAULT_SIM_SIZE:,} synthetic gachas via OASIS")
        for p in top:
            lines.append(
                f"  ctr≈{p.get('ctr', 0):.2%}  install≈{p.get('install', 0):.2%}  "
                f"{p['concept'][:50]}"
            )

        ctx.artifacts["audience_predictions"] = predictions
        ctx.artifacts["top_creatives"] = top
        return WorkerResult(lines=lines, data={"predictions": predictions, "top": top})
