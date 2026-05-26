"""Ads adapter — Meta + TikTok via MCP.

v0 ships a planning/shadow implementation only. v0.2 will speak MCP directly
to `pipeboard-co/meta-ads-mcp` and `amekala/ads-mcp` for real campaign writes.

The contract is intentionally narrow: `launch_many(plan) -> list[result]`.
Everything else (creative upload, audience setup) is dispatched per item.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class LaunchResult:
    platform: str
    region: str
    ad_group_id: str
    budget: float
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


class AdsAdapter:
    """v0 implementation deliberately stays in shadow mode.

    A real run is gated by `DRIP_MODE` upstream; here we additionally guard
    against missing platform tokens so an accidental autonomous-mode run can't
    blow money before keys are configured.
    """

    def __init__(self) -> None:
        self.meta_token = os.getenv("META_ACCESS_TOKEN")
        self.tiktok_token = os.getenv("TIKTOK_ACCESS_TOKEN")

    @classmethod
    def default(cls) -> "AdsAdapter":
        return cls()

    async def launch_many(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = await asyncio.gather(*(self._launch_one(item) for item in plan))
        return [r.to_dict() for r in results]

    async def _launch_one(self, item: dict[str, Any]) -> LaunchResult:
        platform = item["platform"]

        # Defensive: refuse to call real APIs unless tokens exist.
        if platform == "meta" and not self.meta_token:
            return LaunchResult(platform, item["region"], "dry-no-token", item["budget"], "skipped")
        if platform == "tiktok" and not self.tiktok_token:
            return LaunchResult(platform, item["region"], "dry-no-token", item["budget"], "skipped")

        # TODO(v0.2): replace with real MCP call. See:
        #   https://github.com/pipeboard-co/meta-ads-mcp
        #   https://github.com/amekala/ads-mcp
        # For now we return a fake id so the rest of the pipeline can flow.
        ad_group_id = f"{platform}-{item['region']}-{abs(hash(item['concept'])) % 10_000:04d}"
        return LaunchResult(
            platform=platform,
            region=item["region"],
            ad_group_id=ad_group_id,
            budget=item["budget"],
        )
