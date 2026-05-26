"""Creative worker — generates keyframes (GPT-Image) and short videos (Seedance 2.0).

MVP scope: produce N candidate creatives, each = (concept, keyframe png, video mp4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from drip.adapters.image import ImageAdapter
from drip.adapters.video import VideoAdapter
from drip.workers.base import Worker, WorkerResult

if TYPE_CHECKING:
    from drip.orchestrator import RunContext


CONCEPTS_PER_RUN = 6


class CreativeWorker(Worker):
    name = "creative"
    model = "claude-sonnet-4-6"

    def __init__(self) -> None:
        self.image = ImageAdapter.default()
        self.video = VideoAdapter.default()

    async def run(self, ctx: "RunContext") -> WorkerResult:
        lines: list[str] = []
        creatives: list[dict[str, str]] = []

        concepts = self._brainstorm_concepts(ctx)
        lines.append(f"brainstormed {len(concepts)} ad concepts")

        for i, concept in enumerate(concepts, start=1):
            if ctx.dry_run:
                creatives.append({"concept": concept, "keyframe": "(dry-run)", "video": "(dry-run)"})
                continue

            keyframe = await self.image.generate(prompt=concept, size="1024x1536")
            video = await self.video.generate(
                prompt=concept,
                seed_image=keyframe.local_path,
                duration_seconds=6,
            )
            creatives.append({
                "concept": concept,
                "keyframe": keyframe.local_path,
                "video": video.local_path,
            })
            lines.append(f"  [{i}/{len(concepts)}] {concept[:70]}")

        ctx.artifacts["creatives"] = creatives
        lines.append(f"produced {len(creatives)} candidate creatives")
        return WorkerResult(lines=lines, data={"creatives": creatives})

    def _brainstorm_concepts(self, ctx: "RunContext") -> list[str]:
        """Stub — v0.2 hands this to a Claude sub-agent with the game brief.

        We use a deterministic seeding strategy for the v0 demo so the pipeline
        is reproducible without burning API credits.
        """
        chars = ", ".join(ctx.game.key_characters) or "the protagonist"
        themes = [
            f"cinematic intro of {chars} in {ctx.game.art_style} style, dramatic lighting",
            f"gameplay loop hero shot — {chars} performing a signature skill",
            f"emotional reveal of {chars} with cherry blossom particles",
            f"sci-fi neon arena, {chars} mid-combat, hand-drawn anime",
            f"slice-of-life vignette of {chars}, summer festival",
            f"first-person POV pulling a new banner, {chars} appears in 5★ glow",
        ]
        return themes[:CONCEPTS_PER_RUN]
