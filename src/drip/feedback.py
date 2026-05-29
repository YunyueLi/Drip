"""Feedback — close the loop: what won, fed back to strategy and allocation.

The link that turns a one-shot run into a learning system. It aggregates
performance into reusable signals: which platform is pulling weight, what CTR
bar the winners set. Those signals feed the Strategist (next creative bar)
and the Allocator (platform weighting), so each cycle is a little smarter.

Element-level creative attribution (which hook won) needs creative tagging —
that's a v0.x extension; here we work at platform/campaign granularity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from drip.data.metrics import AdMetrics


@dataclass
class Learning:
    insight: str
    signal: dict[str, object]


@dataclass
class FeedbackResult:
    platform_roas: dict[str, float] = field(default_factory=dict)
    learnings: list[Learning] = field(default_factory=list)

    @property
    def platform_weights(self) -> dict[str, float]:
        """Normalised weights to feed the Allocator next round."""
        total = sum(self.platform_roas.values())
        if total <= 0:
            return {p: 1.0 for p in self.platform_roas}
        return {p: round(r / total, 3) for p, r in self.platform_roas.items()}


class FeedbackLoop:
    def __init__(self, roas_target: float = 3.0) -> None:
        self.roas_target = roas_target

    def review(self, metrics: list[AdMetrics]) -> FeedbackResult:
        by_platform: dict[str, list[AdMetrics]] = {}
        for m in metrics:
            by_platform.setdefault(m.platform, []).append(m)

        platform_roas = {
            p: round(sum(x.roas for x in ms) / len(ms), 2)
            for p, ms in by_platform.items()
        }
        result = FeedbackResult(platform_roas=platform_roas)

        if len(platform_roas) >= 2:
            best = max(platform_roas, key=lambda p: platform_roas[p])
            worst = min(platform_roas, key=lambda p: platform_roas[p])
            if platform_roas[best] > platform_roas[worst]:
                result.learnings.append(Learning(
                    insight=(f"{best} outperforms {worst} on ROAS "
                             f"({platform_roas[best]:.2f}x vs {platform_roas[worst]:.2f}x) — "
                             f"shift weight toward {best}"),
                    signal={"shift_to": best, "away_from": worst},
                ))

        winners = [m for m in metrics if m.roas >= self.roas_target]
        if winners:
            ctr_bar = sum(w.ctr for w in winners) / len(winners)
            result.learnings.append(Learning(
                insight=(f"{len(winners)} campaigns beat {self.roas_target:.0f}x ROAS; "
                         f"their avg CTR {ctr_bar:.2%} is the bar for the next creatives"),
                signal={"winner_ctr_bar": round(ctr_bar, 4)},
            ))
        return result
