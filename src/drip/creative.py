"""Creative — produce ad variants from a brief by orchestrating external tools.

Drip does NOT train image/video models. AdCreative / Creatify / Arcads and
the platforms' own generators (Meta Advantage+, TikTok Symphony) already win
that race. This agent's job is orchestration: take a brief (from the
Strategist), fan out to a chosen generator, produce N variants, and track
them so Feedback can later attribute performance back to a variant.

Generators are pluggable:
  - ``dry``      — deterministic placeholders (default; runs offline)
  - ``gpt-image``— OpenAI keyframes via adapters.image (lazy)
  - ``seedance`` — short video via adapters.video (lazy)
  - ``comfyui``  — local ComfyUI batch (lazy; see research)

Like every Drip slot: it runs empty; plug a generator to make it real.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


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
        if self.generator == "dry":
            return self._dry(brief, n, kind)
        if self.generator in ("gpt-image", "seedance", "comfyui"):
            return self._live(brief, n, kind)
        # Unknown generator → safe dry fallback.
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

    def _live(self, brief: str, n: int, kind: str) -> list[CreativeVariant]:  # pragma: no cover
        # Lazy import so offline/dry never needs provider SDKs.
        h = hashlib.sha256(brief.encode()).hexdigest()[:6]
        variants: list[CreativeVariant] = []
        if self.generator == "gpt-image":
            from drip.adapters.image import ImageAdapter
            adapter = ImageAdapter.default()
            # ImageAdapter.generate is async; the daemon awaits it. Here we
            # record intent so a sync caller still gets variant records.
            for i in range(n):
                variants.append(CreativeVariant(
                    variant_id=f"{h}-{i+1}", brief=brief, asset_kind="image",
                    asset_ref=f"pending:gpt-image:{adapter.model}", generator="gpt-image",
                ))
        elif self.generator == "comfyui":
            for i in range(n):
                variants.append(CreativeVariant(
                    variant_id=f"{h}-{i+1}", brief=brief, asset_kind=kind,
                    asset_ref="pending:comfyui", generator="comfyui",
                ))
        else:  # seedance video
            for i in range(n):
                variants.append(CreativeVariant(
                    variant_id=f"{h}-{i+1}", brief=brief, asset_kind="video",
                    asset_ref="pending:seedance", generator="seedance",
                ))
        return variants
