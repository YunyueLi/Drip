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

    async def run(self, ctx: RunContext) -> WorkerResult:
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

    def _brainstorm_concepts(self, ctx: RunContext) -> list[str]:
        """Generic concept seeds for the v0 demo.

        Deterministic and vertical-neutral. Knowledge Packs (v0.1) override
        this list with vertical-specific concept seeds — e.g. anime / gacha
        adds banner-pull POV, slice-of-life vignettes, and signature-skill
        hero shots. v0.2 replaces the static list with a Claude sub-agent.
        """
        chars = ", ".join(ctx.game.key_characters) or "the protagonist"
        themes = [
            f"cinematic intro of {chars} in {ctx.game.art_style} style, dramatic lighting",
            f"gameplay loop hero shot — {chars} performing a signature action",
            f"emotional reveal of {chars}, atmospheric particles",
            f"core-loop showcase — fast-cut highlights of {chars} in action",
            f"slice-of-life vignette of {chars}, ambient scene",
            f"first-person POV of a key game moment — {chars} appears in a payoff beat",
        ]
        return themes[:CONCEPTS_PER_RUN]
