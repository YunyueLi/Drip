"""Bidding worker — plans + (optionally) executes campaign launches across platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING

from drip.adapters.ads import AdsAdapter
from drip.workers.base import Worker, WorkerResult

if TYPE_CHECKING:
    from drip.orchestrator import RunContext


class BiddingWorker(Worker):
    name = "bidding"
    model = "claude-sonnet-4-6"

    def __init__(self) -> None:
        self.ads = AdsAdapter.default()

    async def run(self, ctx: RunContext) -> WorkerResult:
        lines: list[str] = []
        top = ctx.artifacts.get("top_creatives") or ctx.artifacts.get("creatives", [])

        if not top:
            lines.append("nothing to launch — no creatives selected")
            return WorkerResult(lines=lines)

        # naive allocation v0: equal split across (creatives × regions × {meta, tiktok})
        plan = self._plan_allocation(ctx, top)
        ctx.artifacts["bidding_plan"] = plan
        lines.append(f"planned {len(plan)} ad groups across {len(ctx.regions)} regions × 2 platforms")

        if ctx.mode.value == "shadow" or ctx.dry_run:
            lines.append("[shadow mode] not pushing to platforms")
        else:
            launched = await self.ads.launch_many(plan)
            ctx.artifacts["launched"] = launched
            ctx.spent_usd += sum(a["budget"] for a in launched)
            lines.append(f"launched {len(launched)} ad groups (live)")

        return WorkerResult(lines=lines, data={"plan": plan})

    def _plan_allocation(
        self, ctx: RunContext, creatives: list[dict]
    ) -> list[dict]:
        per_group = ctx.budget_usd / max(len(creatives) * len(ctx.regions) * 2, 1)
        plan = []
        for creative in creatives:
            for region in ctx.regions:
                for platform in ("meta", "tiktok"):
                    plan.append({
                        "platform": platform,
                        "region": region,
                        "concept": creative["concept"],
                        "creative_asset": creative.get("video") or creative.get("keyframe"),
                        "budget": round(per_group, 2),
                    })
        return plan
