"""Reporter — narrative summary + next-step recommendation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from drip.workers.base import Worker, WorkerResult

if TYPE_CHECKING:
    from drip.orchestrator import RunContext


class ReporterWorker(Worker):
    name = "reporter"
    model = "claude-haiku-4-5"

    async def run(self, ctx: "RunContext") -> WorkerResult:
        lines: list[str] = []
        plan = ctx.artifacts.get("bidding_plan", [])
        top = ctx.artifacts.get("top_creatives") or ctx.artifacts.get("creatives", [])
        predictions = ctx.artifacts.get("audience_predictions", [])

        if not plan:
            lines.append("no plan to report on")
            return WorkerResult(lines=lines)

        # v0 deterministic narrative; v0.2 hands ctx to Haiku for prose generation.
        best = top[0] if top else None
        best_pred = predictions[0] if predictions else {}
        lines.append(
            f"plan: {len(plan)} groups · "
            f"budget ${ctx.budget_usd:,.0f} · "
            f"regions {', '.join(ctx.regions)}"
        )
        if best:
            lines.append(f"top concept: {best['concept'][:70]}")
        if best_pred:
            lines.append(
                f"predicted: ctr≈{best_pred.get('ctr', 0):.2%}  "
                f"install≈{best_pred.get('install', 0):.2%}"
            )
        lines.append("next: wait 48h, then re-run `drip launch` with `--mode copilot`")

        return WorkerResult(lines=lines)
