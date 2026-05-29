"""Simulation adapter — OASIS multi-agent social simulation.

We seed a small social graph of synthetic users, expose each candidate
creative as a stimulus (post), and aggregate downstream signals (likes,
comments, reshares) into predicted CTR / install-intent scores.

v0 uses OASIS' bundled reddit profile sample so the loop is reproducible
without external data. Knowledge Packs override the persona pool for
verticals (anime / gacha, DTC, tools-app). v0.2 swaps the sample for
region-specific personas sampled from public community profiles.
"""

from __future__ import annotations

import hashlib
from typing import Any

# OASIS imports — these are only required at runtime; we import lazily so
# unit tests / dry-runs don't need camel-oasis installed.
try:
    import oasis  # type: ignore
    from camel.models import ModelFactory  # type: ignore
    from camel.types import ModelPlatformType, ModelType  # type: ignore
    from oasis import (  # type: ignore
        ActionType,
        LLMAction,
        generate_reddit_agent_graph,
    )

    OASIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    OASIS_AVAILABLE = False


DEFAULT_STEPS = 3


class SimulationAdapter:
    """Wraps OASIS into a single `predict_reaction()` call.

    Returns a normalized dict: {ctr, install, engagement_score, sample_n}.
    """

    def __init__(
        self,
        *,
        platform: str = "reddit",
        steps: int = DEFAULT_STEPS,
        model_platform: str = "openai",
        model_name: str = "gpt-4o-mini",
    ) -> None:
        self.platform = platform
        self.steps = steps
        self.model_platform = model_platform
        self.model_name = model_name

    @classmethod
    def default(cls) -> "SimulationAdapter":
        return cls()

    async def predict_reaction(
        self,
        *,
        creative: dict[str, Any],
        regions: list[str],
        audience_size: int,
        dry_run: bool = False,
    ) -> dict[str, float]:
        if dry_run or not OASIS_AVAILABLE:
            return self._deterministic_stub(creative, regions, audience_size)
        return await self._run_oasis(creative, audience_size)

    def _deterministic_stub(
        self, creative: dict[str, Any], regions: list[str], n: int
    ) -> dict[str, float]:
        """Hash the concept into a stable pseudo-CTR for v0 dry-runs."""
        seed = creative.get("concept", "") + ",".join(regions)
        h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
        ctr = 0.012 + (h % 5000) / 1_000_000  # ~1.2% – 1.7%
        install = ctr * (0.05 + (h % 500) / 10000)
        return {
            "ctr": ctr,
            "install": install,
            "engagement_score": ctr * 100,
            "sample_n": float(n),
        }

    async def _run_oasis(
        self, creative: dict[str, Any], audience_size: int
    ) -> dict[str, float]:  # pragma: no cover — integration path
        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=ModelType.GPT_4O_MINI,
        )
        agent_graph = await generate_reddit_agent_graph(
            profile_path="./data/oasis/default_users.json",
            model=model,
            available_actions=[
                ActionType.CREATE_POST,
                ActionType.CREATE_COMMENT,
                ActionType.LIKE_POST,
            ],
        )
        env = oasis.make(
            agent_graph=agent_graph,
            platform=oasis.DefaultPlatformType.REDDIT,
        )
        await env.reset()

        # Inject the creative as a seed post.
        await env.platform.create_post(
            agent_id=0,
            content=creative.get("concept", ""),
        )

        # Let agents react for N steps.
        for _ in range(self.steps):
            actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}
            await env.step(actions)

        signals = await self._aggregate_signals(env)
        await env.close()

        likes = signals.get("likes", 0)
        comments = signals.get("comments", 0)
        n = max(audience_size, 1)
        ctr = (likes + 0.5 * comments) / n
        return {
            "ctr": ctr,
            "install": ctr * 0.07,  # generic heuristic; Knowledge Packs override
            "engagement_score": float(likes + comments * 2),
            "sample_n": float(n),
        }

    async def _aggregate_signals(self, env: Any) -> dict[str, int]:  # pragma: no cover
        # OASIS exposes `platform.db` for post-run inspection in 0.2.x.
        # Real aggregation lives there; stubbed here.
        try:
            posts = await env.platform.list_posts()
            likes = sum(getattr(p, "likes", 0) for p in posts)
            comments = sum(getattr(p, "comments", 0) for p in posts)
            return {"likes": likes, "comments": comments}
        except Exception:
            return {"likes": 0, "comments": 0}
