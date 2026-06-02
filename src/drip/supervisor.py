"""Supervisor — signal-driven autonomous orchestration.

Replaces the fixed ``creative → audience → bidding → reporter`` order with a
supervisor that inspects the diagnosis and **routes**: a bleeding account gets a
stop-loss pass first, winners get scaled, fatigued creative is queued for
refresh, thin/mixed reads are held. It drives the whole loop end-to-end and — in
``autonomous`` mode — applies within the money-safety caps, behind a **circuit
breaker** that halts the run before any write if the situation looks anomalous
(e.g. most of the account wants to pause — likely a bad data pull), or mid-run
if writes start failing.

Deterministic and auditable by design — rules route, not an LLM — so the routing
decision carries its own reason chain, the same property as every Drip decision.
This module is pure logic (no I/O); the ``drip autopilot`` command wires it to
the collector, allocator, and platform writers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from drip.engine.rules import Action


class Situation(str, Enum):
    BLEEDING = "bleeding"     # something has broken unit economics → stop the loss first
    SCALING = "scaling"       # there are winners to fund
    FATIGUED = "fatigued"     # creative is saturating → refresh, don't scale into the wall
    STEADY = "steady"         # nothing to move → hold and gather


@dataclass
class RouteStep:
    step: str
    why: str


@dataclass
class RouteResult:
    situation: Situation
    steps: list[RouteStep] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return f"{self.situation.value}: " + " → ".join(s.step for s in self.steps)


def classify(actions: list[Action]) -> Situation:
    """Pick the dominant situation from the per-campaign decisions.

    Priority is safety-first: bleeding (pause) outranks scaling outranks
    fatigue, because stopping a loss matters more than funding a winner.
    """
    if Action.PAUSE in actions:
        return Situation.BLEEDING
    if Action.SCALE in actions:
        return Situation.SCALING
    if Action.REFRESH_CREATIVE in actions:
        return Situation.FATIGUED
    return Situation.STEADY


def route(actions: list[Action]) -> RouteResult:
    """Turn the diagnosis into an ordered, reasoned plan of attack."""
    sit = classify(actions)
    if sit is Situation.BLEEDING:
        steps = [
            RouteStep("stop-loss", "pause units with broken unit economics before anything else"),
            RouteStep("reallocate", "move the freed budget to the survivors, within the daily cap"),
            RouteStep("hold-rest", "leave mixed/thin reads untouched until they clear"),
        ]
    elif sit is Situation.SCALING:
        steps = [
            RouteStep("scale-winners", "raise the winners by the engine's sized step"),
            RouteStep("refresh-fatigued", "queue fresh creative for any saturating line"),
            RouteStep("allocate", "fund the plan across platforms"),
        ]
    elif sit is Situation.FATIGUED:
        steps = [
            RouteStep("refresh", "produce new creative for the fatigued winners"),
            RouteStep("hold-budget", "don't add budget into a saturating audience"),
        ]
    else:
        steps = [
            RouteStep("hold", "no budget moves — signals are mixed or thin"),
            RouteStep("gather", "wait for clearer reads before the next cycle"),
        ]
    return RouteResult(situation=sit, steps=steps)


@dataclass
class CircuitBreaker:
    """The autonomous-mode safety net: halt rather than do something drastic."""

    max_pause_ratio: float = 0.6     # > this share wanting PAUSE = likely a data anomaly
    max_fail_ratio: float = 0.34     # > this share of writes failing = stop the run

    def pre_apply(self, n_total: int, n_pause: int) -> tuple[bool, str]:
        """Check the diagnosis before any write goes out."""
        if n_total and n_pause / n_total > self.max_pause_ratio:
            return True, (f"{n_pause}/{n_total} campaigns want PAUSE "
                          f"(> {self.max_pause_ratio:.0%}) — likely a data anomaly, "
                          f"halting before any write")
        return False, ""

    def post_write(self, n_attempted: int, n_failed: int) -> tuple[bool, str]:
        """Check write health mid-run."""
        if n_attempted and n_failed / n_attempted > self.max_fail_ratio:
            return True, (f"{n_failed}/{n_attempted} writes failed "
                          f"(> {self.max_fail_ratio:.0%}) — halting the run")
        return False, ""
