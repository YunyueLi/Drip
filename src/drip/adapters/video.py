"""Video adapter — Seedance 2.0 via Volc Engine ARK (ByteDance).

The ARK content-generation API is async: submit a task, poll for completion,
then download the resulting MP4 within 24 hours.
"""

from __future__ import annotations

import asyncio
import base64
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from volcenginesdkarkruntime import Ark

ARTIFACT_DIR = Path("artifacts/videos")
POLL_INITIAL_SECONDS = 8
POLL_MAX_SECONDS = 60
POLL_TIMEOUT_SECONDS = 600


@dataclass
class GeneratedVideo:
    local_path: str
    prompt: str
    model: str
    duration_s: int


class VideoAdapter:
    """Thin wrapper around `volcenginesdkarkruntime.Ark`.

    The SDK itself is synchronous; we run its blocking calls in a thread
    so the orchestrator stays async.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        resolution: str = "1080p",
        ratio: str = "9:16",  # vertical = TikTok / Reels default
    ) -> None:
        self.model = model or os.getenv("SEEDANCE_MODEL", "doubao-seedance-2-0-260128")
        self.resolution = resolution
        self.ratio = ratio
        self._client: Any = None

    @classmethod
    def default(cls) -> "VideoAdapter":
        return cls()

    def _ensure_client(self) -> "Ark":
        if self._client is None:
            try:
                from volcenginesdkarkruntime import Ark
            except ImportError as e:
                raise RuntimeError(
                    "Seedance video needs the Volc Engine ARK SDK. "
                    "Install provider extras:  uv pip install -e '.[providers]'"
                ) from e

            api_key = os.getenv("ARK_API_KEY")
            if not api_key:
                raise RuntimeError("ARK_API_KEY is not set")
            self._client = Ark(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        *,
        seed_image: str | None = None,
        duration_seconds: int = 5,
    ) -> GeneratedVideo:
        task_id = await asyncio.to_thread(self._submit, prompt, seed_image, duration_seconds)
        video_url = await self._poll(task_id)
        local_path = await self._download(video_url)
        return GeneratedVideo(
            local_path=local_path, prompt=prompt, model=self.model, duration_s=duration_seconds,
        )

    def _submit(self, prompt: str, seed_image: str | None, duration: int) -> str:
        client = self._ensure_client()
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        if seed_image:
            # ARK accepts either a public URL or an `image_base64` field.
            with open(seed_image, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({"type": "image", "image_base64": b64, "role": "first_frame"})

        resp = client.content_generation.tasks.create(
            model=self.model,
            content=content,
            resolution=self.resolution,
            ratio=self.ratio,
            duration=duration,
            watermark=False,
        )
        return resp.id

    async def _poll(self, task_id: str) -> str:
        wait = POLL_INITIAL_SECONDS
        elapsed = 0
        client = self._ensure_client()

        while elapsed < POLL_TIMEOUT_SECONDS:
            r = await asyncio.to_thread(client.content_generation.tasks.get, task_id=task_id)
            status = r.status
            if status == "succeeded":
                return r.content.video_url
            if status in ("failed", "expired", "cancelled"):
                raise RuntimeError(f"seedance task {task_id} -> {status}")
            await asyncio.sleep(wait)
            elapsed += wait
            wait = min(wait * 2, POLL_MAX_SECONDS)

        raise TimeoutError(f"seedance task {task_id} did not complete in {POLL_TIMEOUT_SECONDS}s")

    async def _download(self, url: str) -> str:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        out = ARTIFACT_DIR / f"{uuid.uuid4().hex}.mp4"
        # video_url is valid for 24h — download immediately
        async with httpx.AsyncClient(timeout=60.0) as http:
            async with http.stream("GET", url) as resp:
                resp.raise_for_status()
                with out.open("wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        return str(out)
