"""Pipeline — the one-stop loop, end to end.

Wires every agent into the full cycle:

    Collector → Analyst (diagnose) → Strategist (next creative)
       → Creative (variants) → Allocator (cross-platform budget)
       → Feedback (learnings, fed back next cycle)

Runs offline on sample data (dry/template/null paths); plug credentials,
an LLM, and a creative generator to go live — no code change. This is the
framework-agnostic reference flow; the production daemon upgrades it to a
LangGraph supervisor (checkpointing + interrupt() approval + retries), and
the agent boundaries here map 1:1 onto graph nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from drip.allocator import AllocationPlan, Allocator
from drip.analyst import Analyst, AnalystReport
from drip.collectors import Collector
from drip.creative import Creative, CreativeVariant
from drip.feedback import FeedbackLoop, FeedbackResult
from drip.strategist import Strategist, StrategyOutput


@dataclass
class PipelineResult:
    report: AnalystReport
    strategy: StrategyOutput
    variants: list[CreativeVariant]
    plan: AllocationPlan
    feedback: FeedbackResult


@dataclass
class Pipeline:
    cpp_target: float = 25.0
    roas_target: float = 3.0
    total_budget: float = 1000.0
    narrate_model: str | None = None     # plug an LLM for human reports/briefs
    creative_generator: str = "dry"      # plug gpt-image/seedance/comfyui to go live
    collector: Collector = field(default_factory=Collector)

    def run(self, *, since: str, until: str) -> PipelineResult:
        # 1. collect
        metrics = self.collector.collect(since=since, until=until)

        # 2. diagnose (engine + anomalies + report)
        report = Analyst(narrate_model=self.narrate_model).analyze(
            metrics,
            cpp_target=self.cpp_target,
            roas_target=self.roas_target,
            budget_cap=self.total_budget,
        )

        # 3. strategy (what to test next)
        strategy = Strategist(narrate_model=self.narrate_model).propose(
            metrics, roas_target=self.roas_target,
        )

        # 4. creative (variants for the winning direction)
        creative = Creative(generator=self.creative_generator)
        variants: list[CreativeVariant] = []
        for h in strategy.hypotheses:
            if h.direction == "scale_winner":
                variants.extend(creative.produce(h.brief, n=3))

        # 5. cross-platform budget allocation
        plan = Allocator().plan(
            metrics,
            total_budget=self.total_budget,
            cpp_target=self.cpp_target,
            roas_target=self.roas_target,
        )

        # 6. feedback loop (feeds the next cycle)
        feedback = FeedbackLoop(roas_target=self.roas_target).review(metrics)

        return PipelineResult(
            report=report, strategy=strategy, variants=variants,
            plan=plan, feedback=feedback,
        )
