"""Creative — produce ad variants from a brief by orchestrating external tools.

Drip does NOT train image/video models. The platforms' own generators (Meta
Advantage+, TikTok Symphony) and tools like AdCreative already win that race.
This agent's job is orchestration: take a brief (from the Strategist), fan out
to a chosen generator, produce N variants, and track them so Feedback can later
attribute performance back to a variant.

Generators are pluggable:
  - ``dry``      — deterministic placeholders (default; runs offline)
  - ``gpt-image``— OpenAI gpt-image-2 keyframes via adapters.image (needs ``OPENAI_API_KEY``)
  - ``seedance`` — short video via adapters.video / Volc ARK (needs ``ARK_API_KEY``)

A live generator with no key — or any generator we don't ship yet — falls back
to ``dry`` placeholders, so the loop always runs offline. Plug a key to make a
generator produce real assets; no code change.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

_T = TypeVar("_T")


@dataclass
class CreativeVariant:
    variant_id: str
    brief: str
    asset_kind: str        # "image" | "video"
    asset_ref: str         # local path / url, or "(dry-run)"
    generator: str


class Creative:
    def __init__(self, generator: str = "dry") -> None:
        self.generator = generator

    def produce(self, brief: str, *, n: int = 3, kind: str = "image") -> list[CreativeVariant]:
        if self.generator == "gpt-image" and os.getenv("OPENAI_API_KEY"):
            return self._gpt_image(brief, n)
        if self.generator == "seedance" and os.getenv("ARK_API_KEY"):
            return self._seedance(brief, n)
        # dry, an unshipped generator (e.g. comfyui), or a live generator with
        # no key → deterministic placeholders so the pipeline still runs.
        return self._dry(brief, n, kind)

    def _dry(self, brief: str, n: int, kind: str) -> list[CreativeVariant]:
        h = hashlib.sha256(brief.encode()).hexdigest()[:6]
        return [
            CreativeVariant(
                variant_id=f"{h}-{i+1}",
                brief=brief,
                asset_kind=kind,
                asset_ref="(dry-run)",
                generator="dry",
            )
            for i in range(n)
        ]

    def _gpt_image(self, brief: str, n: int) -> list[CreativeVariant]:  # pragma: no cover — needs OPENAI_API_KEY + network
        from drip.adapters.image import ImageAdapter

        adapter = ImageAdapter.default()
        images = _run_n(lambda: adapter.generate(brief), n)
        h = hashlib.sha256(brief.encode()).hexdigest()[:6]
        return [
            CreativeVariant(variant_id=f"{h}-{i+1}", brief=brief, asset_kind="image",
                            asset_ref=img.local_path, generator="gpt-image")
            for i, img in enumerate(images)
        ]

    def _seedance(self, brief: str, n: int) -> list[CreativeVariant]:  # pragma: no cover — needs ARK_API_KEY + network
        from drip.adapters.video import VideoAdapter

        adapter = VideoAdapter.default()
        videos = _run_n(lambda: adapter.generate(brief), n)
        h = hashlib.sha256(brief.encode()).hexdigest()[:6]
        return [
            CreativeVariant(variant_id=f"{h}-{i+1}", brief=brief, asset_kind="video",
                            asset_ref=v.local_path, generator="seedance")
            for i, v in enumerate(videos)
        ]


def _run_n(make_coro: Callable[[], Awaitable[_T]], n: int) -> list[_T]:  # pragma: no cover — only hit on the live (keyed) path
    """Drive an async generator call N times from this sync agent.

    The pipeline is synchronous, so we own the event loop here.
    """
    async def _gather() -> list[_T]:
        return [await make_coro() for _ in range(n)]

    return asyncio.run(_gather())
