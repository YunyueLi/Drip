"""Cross-platform ad metrics — the data contract every agent shares.

Meta calls spend "Amount Spent", TikTok "Total Cost", Google "Cost". Conversions
live in different shapes (Meta ``actions[]``, TikTok ``conversion``). The Collector
normalises all of them into one :class:`AdMetrics` record, so the rest of the
system speaks a single language. Derived metrics (CTR/CPP/ROAS/…) are computed
here once, not re-derived per agent.

Pure stdlib — no pydantic, no provider deps — so it runs anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drip.engine.signals import CampaignMetrics


@dataclass
class AdMetrics:
    """One campaign's observed metrics over a window, normalised across platforms.

    These are *observations*. Targets and baselines (needed by the decision
    engine) are injected by the caller via :meth:`to_engine_metrics`, because
    they come from the business profile / history, not from the platform.
    """

    platform: str             # "meta" | "tiktok" | "google"
    campaign_id: str
    date_start: str           # ISO date, e.g. "2026-05-01"
    date_end: str
    spend: float
    impressions: int
    clicks: int
    conversions: float        # purchases / installs / leads
    conversion_value: float   # revenue, for ROAS
    reach: int = 0            # unique users reached, for frequency
    currency: str = "USD"
    adset_id: str = ""
    label: str = ""

    # --- derived metrics (computed once, here) ---

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def cpc(self) -> float:
        return self.spend / self.clicks if self.clicks else 0.0

    @property
    def cpp(self) -> float:
        """Cost per purchase / acquisition."""
        return self.spend / self.conversions if self.conversions else 0.0

    @property
    def cvr(self) -> float:
        return self.conversions / self.clicks if self.clicks else 0.0

    @property
    def roas(self) -> float:
        return self.conversion_value / self.spend if self.spend else 0.0

    @property
    def frequency(self) -> float:
        return self.impressions / self.reach if self.reach else 0.0

    def to_dict(self) -> dict[str, object]:
        d = dict(self.__dict__)
        d.update(ctr=self.ctr, cpc=self.cpc, cpp=self.cpp,
                 cvr=self.cvr, roas=self.roas, frequency=self.frequency)
        return d

    def to_engine_metrics(
        self,
        *,
        cpp_target: float,
        roas_target: float,
        budget_cap: float,
        cvr_baseline: float | None = None,
        ctr_baseline: float | None = None,
    ) -> CampaignMetrics:
        """Build a ``drip.engine.CampaignMetrics`` from this observation plus
        the targets/baselines the caller supplies. Returns the engine's
        CampaignMetrics (imported lazily to avoid a hard dependency)."""
        from drip.engine.signals import CampaignMetrics

        return CampaignMetrics(
            cpp=self.cpp,
            cpp_target=cpp_target,
            roas=self.roas,
            roas_target=roas_target,
            cvr=self.cvr,
            cvr_baseline=cvr_baseline if cvr_baseline is not None else self.cvr,
            daily_spend=self.spend,
            budget_cap=budget_cap,
            purchases=int(self.conversions),
            ctr=self.ctr,
            ctr_baseline=ctr_baseline if ctr_baseline is not None else self.ctr,
            frequency=self.frequency,
            label=self.label or f"{self.platform}:{self.campaign_id}",
        )
