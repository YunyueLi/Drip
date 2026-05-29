"""Attribution — reconcile platform-reported vs MMP truth, flag over-investment.

Platforms mark their own homework: reporting suggests Meta inflates ROAS
~17-19% (counting view-through, likes/shares as engagement). This agent
reconciles platform-reported metrics against an MMP source (AppsFlyer /
Adjust — an interface you plug in, not something open source can be the
source of truth for) and, absent an MMP, applies a documented haircut so the
numbers you act on aren't the platform's rosiest.

It also flags likely over-investment (saturated frequency), the "is this
budget still working or just buying the same users again" question.

SKAN conversion-value handling follows the singular-labs/skan open schema —
also an interface, since the mapping is MMP-hosted.
"""

from __future__ import annotations

from dataclasses import dataclass

from drip.data.metrics import AdMetrics

# Documented self-report inflation by platform (research-derived priors).
# Used only when no MMP truth is supplied.
PLATFORM_INFLATION = {"meta": 0.18, "tiktok": 0.12, "google": 0.10}
FREQ_OVERINVEST = 2.5


@dataclass
class Discrepancy:
    campaign: str
    platform: str
    platform_roas: float
    adjusted_roas: float
    mmp_roas: float | None
    flag: str          # "" | "inflated" | "over_investment"
    note: str


class Attribution:
    def reconcile(
        self,
        platform_metrics: list[AdMetrics],
        mmp_roas_by_campaign: dict[str, float] | None = None,
    ) -> list[Discrepancy]:
        mmp = mmp_roas_by_campaign or {}
        out: list[Discrepancy] = []
        for m in platform_metrics:
            truth = mmp.get(m.campaign_id)
            if truth is not None:
                adjusted = truth
                flag = "inflated" if m.roas > truth * 1.1 else ""
                note = f"MMP truth {truth:.2f}x vs platform {m.roas:.2f}x"
            else:
                haircut = PLATFORM_INFLATION.get(m.platform, 0.15)
                adjusted = round(m.roas * (1 - haircut), 2)
                flag = ""
                note = (f"no MMP — applied {haircut:.0%} haircut → est {adjusted:.2f}x "
                        f"(connect AppsFlyer/Adjust for ground truth)")

            if m.frequency > FREQ_OVERINVEST:
                flag = "over_investment"
                note += (f"; frequency {m.frequency:.1f} > {FREQ_OVERINVEST} — "
                         f"likely buying the same users again")

            out.append(Discrepancy(
                campaign=m.label, platform=m.platform,
                platform_roas=round(m.roas, 2), adjusted_roas=adjusted,
                mmp_roas=truth, flag=flag, note=note,
            ))
        return out
