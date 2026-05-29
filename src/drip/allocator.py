"""Allocator — cross-platform budget allocation.

Platform algorithms (Advantage+/AXON/Smart+) optimise WITHIN their own walled
garden. Nobody optimises ACROSS platforms — deciding whether the next dollar
should go to Meta or TikTok is exactly the gap this agent fills, and exactly
where an open, neutral tool has the right to play.

The flow:
  1. run each campaign through the decision engine (SCALE/PAUSE/…)
  2. turn decisions into a desired budget (pause -> 0, scale -> +delta, …)
  3. weight by value (ROAS by default; a plugged ValueModel if you want)
  4. normalise to the fixed total budget — freed budget from pauses flows to
     the scalers in proportion to value
  5. (optional) hand each new budget to the bidding slot for execution

``plan()`` is pure (engine + data only) so it runs and tests offline.
``execute()`` lazily uses the bidding slot, so the dependency only loads when
you actually dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from drip.data.metrics import AdMetrics
from drip.engine import DecisionEngine, EngineResult
from drip.engine.rules import Action


@dataclass
class Allocation:
    metrics: AdMetrics
    result: EngineResult
    old_budget: float
    new_budget: float

    @property
    def delta(self) -> float:
        return self.new_budget - self.old_budget

    @property
    def reason(self) -> str:
        return self.result.decision.action.value


@dataclass
class AllocationPlan:
    allocations: list[Allocation] = field(default_factory=list)
    total_budget: float = 0.0

    @property
    def allocated(self) -> float:
        return sum(a.new_budget for a in self.allocations)


class Allocator:
    def __init__(
        self,
        engine: DecisionEngine | None = None,
        value_model_name: str = "null",
    ) -> None:
        self.engine = engine or DecisionEngine()
        self.value_model_name = value_model_name

    def plan(
        self,
        metrics: list[AdMetrics],
        *,
        total_budget: float,
        cpp_target: float,
        roas_target: float,
    ) -> AllocationPlan:
        # 1. decide per campaign
        verdicts: list[tuple[AdMetrics, EngineResult]] = []
        for m in metrics:
            em = m.to_engine_metrics(
                cpp_target=cpp_target, roas_target=roas_target,
                budget_cap=total_budget,
            )
            verdicts.append((m, self.engine.run(em)))

        # 2. desired budget from each decision
        desired: list[float] = []
        for m, r in verdicts:
            action = r.decision.action
            if action is Action.PAUSE:
                desired.append(0.0)
            elif action in (Action.SCALE, Action.REDUCE):
                desired.append(m.spend * (1 + r.decision.delta_pct))
            else:  # HOLD / REFRESH_CREATIVE keep current
                desired.append(m.spend)

        # 3. value weight (ROAS by default; a ValueModel if requested)
        values = self._value_weights(metrics)

        # 4. normalise desired*value to the fixed total
        weights = [d * v for d, v in zip(desired, values)]
        wsum = sum(weights)
        plan = AllocationPlan(total_budget=total_budget)
        for (m, r), w in zip(verdicts, weights):
            new_budget = total_budget * (w / wsum) if wsum > 0 else 0.0
            plan.allocations.append(Allocation(
                metrics=m, result=r,
                old_budget=m.spend, new_budget=round(new_budget, 2),
            ))
        return plan

    def execute(self, plan: AllocationPlan, *, executor_name: str = "shadow") -> list[dict]:
        """Hand each non-zero budget to the bidding slot. Lazy-imports the
        slot so the dependency only loads when you actually dispatch."""
        from drip.adapters.bidding import (
            BidInstruction,
            BidStrategy,
            build_bid_executor,
        )

        executor = build_bid_executor(executor_name)
        results: list[dict] = []
        for a in plan.allocations:
            if a.new_budget <= 0:
                continue
            instr = BidInstruction(
                platform=a.metrics.platform,
                budget=a.new_budget,
                strategy=BidStrategy.PLATFORM_AUTO,
            )
            results.append(executor.execute(instr).to_dict())
        return results

    def _value_weights(self, metrics: list[AdMetrics]) -> list[float]:
        if self.value_model_name == "null":
            # ROAS is the cheap default weight; floor avoids zero-out.
            return [max(m.roas, 0.1) for m in metrics]
        from drip.adapters.prediction import build_value_model

        model = build_value_model(self.value_model_name)
        out: list[float] = []
        for m in metrics:
            est = model.estimate({
                "roas": m.roas, "cvr": m.cvr, "purchases": m.conversions,
            })
            out.append(max(est.value, 0.1))
        return out
