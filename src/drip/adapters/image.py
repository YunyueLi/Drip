"""Image adapter — OpenAI gpt-image-2.

The real OpenAI Images endpoint as of 2026-05 is `gpt-image-2`. We default
to `quality='high'` for hero keyframes and let callers downshift to
`gpt-image-1-mini` for cheap variant batches.
"""

from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI

ARTIFACT_DIR = Path("artifacts/images")


@dataclass
class GeneratedImage:
    local_path: str
    prompt: str
    model: str


class ImageAdapter:
    """Thin wrapper around `openai.images.generate(model='gpt-image-2', ...)`.

    We use `AsyncOpenAI` so the orchestrator can pipeline image + video calls.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-image-2",
        quality: str = "high",
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.quality = quality
        self.client = client or AsyncOpenAI()

    @classmethod
    def default(cls) -> "ImageAdapter":
        return cls()

    async def generate(self, prompt: str, *, size: str = "1024x1536") -> GeneratedImage:
        """Generate one image; persist to artifacts/ and return its local path."""
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set")

        resp = await self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=size,
            quality=self.quality,
            n=1,
            response_format="b64_json",
        )
        b64 = resp.data[0].b64_json
        if not b64:
            raise RuntimeError("OpenAI returned no image data")

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        out = ARTIFACT_DIR / f"{uuid.uuid4().hex}.png"
        out.write_bytes(base64.b64decode(b64))
        return GeneratedImage(local_path=str(out), prompt=prompt, model=self.model)
