"""Bidding adapter — the "who runs the auction" slot.

Drip does NOT build a bidding algorithm. Inside each walled garden the
platform engines already win: Meta Advantage+/GEM, AppLovin AXON, TikTok
Smart+, Unity Vector. Beating them on raw auction optimisation is a losing
game, and post-ATT the data to even try lives only on the platform side.

So Drip keeps the *cross-platform* job (how much budget each platform gets
— that's the Allocator) and delegates the *in-platform auction* to whoever
you trust via this slot:

- ``shadow``        — record the bid plan, never touch a real auction (default)
- ``platform_auto`` — hand budget + objective to the platform's own bidder
- ``third_party``   — delegate to Madgicx / Smartly / etc.

Real API dispatch happens through :mod:`drip.adapters.ads` (v0.2, MCP). This
module only decides *strategy + who executes*, so the decision stays
auditable and the executor stays swappable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class BidStrategy(str, Enum):
    PLATFORM_AUTO = "platform_auto"   # delegate to Advantage+ / AXON / Smart+
    COST_CAP = "cost_cap"
    BID_CAP = "bid_cap"
    LOWEST_COST = "lowest_cost"
    THIRD_PARTY = "third_party"       # Madgicx / Smartly / ...


@dataclass
class BidInstruction:
    """What the Allocator hands down: a platform's budget + how to bid it."""

    platform: str
    budget: float
    objective: str = "conversions"
    strategy: BidStrategy = BidStrategy.PLATFORM_AUTO
    # Optional cap, or a predicted value from a ValueModel (see prediction.py)
    # for value-based bidding.
    target_value: float | None = None
    notes: str = ""


@dataclass
class BidResult:
    platform: str
    strategy: str
    budget: float
    executor: str
    status: str = "planned"   # planned | shadow | delegated | live

    def to_dict(self) -> dict[str, object]:
        return self.__dict__


class BidExecutor(Protocol):
    """Implement this to plug in any auction runner."""

    name: str

    def execute(self, instr: BidInstruction) -> BidResult: ...


# --------------------------------------------------------------------------
# Built-in executors
# --------------------------------------------------------------------------


class ShadowBidExecutor:
    """Default. Plans the bid but never touches a real auction — the safe
    floor, mirrors Drip's shadow run mode."""

    name = "shadow"

    def execute(self, instr: BidInstruction) -> BidResult:
        return BidResult(
            platform=instr.platform,
            strategy=instr.strategy.value,
            budget=instr.budget,
            executor=self.name,
            status="shadow",
        )


class PlatformAutoBidExecutor:
    """Hand the budget + objective to the platform's own bidder
    (Advantage+ / AXON / Smart+). Drip stops at 'here's the money and the
    goal'; the platform runs the auction. Real dispatch via AdsAdapter (v0.2).
    """

    name = "platform_auto"

    def execute(self, instr: BidInstruction) -> BidResult:
        return BidResult(
            platform=instr.platform,
            strategy=BidStrategy.PLATFORM_AUTO.value,
            budget=instr.budget,
            executor=self.name,
            status="delegated",
        )


class ThirdPartyBidExecutor:
    """Delegate auction management to a third party (Madgicx / Smartly).
    Subclass and wire the vendor's API; the default records the delegation."""

    name = "third_party"

    def __init__(self, vendor: str = "unspecified") -> None:
        self.vendor = vendor

    def execute(self, instr: BidInstruction) -> BidResult:
        return BidResult(
            platform=instr.platform,
            strategy=BidStrategy.THIRD_PARTY.value,
            budget=instr.budget,
            executor=f"{self.name}:{self.vendor}",
            status="delegated",
        )


_EXECUTORS: dict[str, type[BidExecutor]] = {
    "shadow": ShadowBidExecutor,
    "platform_auto": PlatformAutoBidExecutor,
    "third_party": ThirdPartyBidExecutor,
}


def build_bid_executor(name: str = "shadow") -> BidExecutor:
    """Build a bid executor by name. Unknown name → shadow (safe default)."""
    cls = _EXECUTORS.get(name, ShadowBidExecutor)
    return cls()
