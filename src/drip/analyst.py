"""Analyst — turn raw metrics + engine decisions into a human report.

Three parts:
  1. anomaly scan — lightweight stdlib rules now; pluggable to Prophet/ADTK
     once a per-campaign time series is available (single-window snapshots
     can't do seasonal decomposition, so we keep the interface for the daemon path).
  2. decision roll-up — runs each campaign through the decision engine.
  3. natural-language summary — via drip.llm (any provider); falls back to a
     deterministic template when no model/key is set, so it runs offline.

Kept framework-agnostic and dependency-light: importing this module pulls in
only the engine (pure stdlib). drip.llm is imported lazily inside the summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from drip.data.metrics import AdMetrics
from drip.engine import DecisionEngine, EngineResult


@dataclass
class Anomaly:
    campaign: str
    metric: str
    detail: str


@dataclass
class CampaignVerdict:
    metrics: AdMetrics
    result: EngineResult


@dataclass
class AnalystReport:
    verdicts: list[CampaignVerdict] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    summary: str = ""

    @property
    def n_campaigns(self) -> int:
        return len(self.verdicts)

    @property
    def total_spend(self) -> float:
        return sum(v.metrics.spend for v in self.verdicts)

    @property
    def by_action(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.verdicts:
            a = v.result.decision.action.value
            counts[a] = counts.get(a, 0) + 1
        return counts


# Anomaly thresholds — deliberately conservative; the daemon can swap these
# for Prophet/ADTK forecasts once it has history.
FREQ_ALARM = 3.0
CTR_FLOOR = 0.005
ROAS_FLOOR = 1.0


class Analyst:
    def __init__(
        self,
        engine: DecisionEngine | None = None,
        narrate_model: str | None = None,
    ) -> None:
        self.engine = engine or DecisionEngine(narrate_model=narrate_model)
        self.narrate_model = narrate_model

    def analyze(
        self,
        metrics: list[AdMetrics],
        *,
        cpp_target: float,
        roas_target: float,
        budget_cap: float,
        cvr_baseline: float | None = None,
        ctr_baseline: float | None = None,
    ) -> AnalystReport:
        report = AnalystReport()
        for m in metrics:
            em = m.to_engine_metrics(
                cpp_target=cpp_target, roas_target=roas_target,
                budget_cap=budget_cap,
                cvr_baseline=cvr_baseline, ctr_baseline=ctr_baseline,
            )
            report.verdicts.append(CampaignVerdict(m, self.engine.run(em)))
            report.anomalies.extend(self._scan(m))
        report.summary = self._summarize(report)
        return report

    def _scan(self, m: AdMetrics) -> list[Anomaly]:
        out: list[Anomaly] = []
        if m.frequency > FREQ_ALARM:
            out.append(Anomaly(m.label, "frequency",
                               f"{m.frequency:.1f} (>{FREQ_ALARM}) — audience burnout risk"))
        if m.ctr < CTR_FLOOR and m.impressions > 0:
            out.append(Anomaly(m.label, "ctr",
                               f"{m.ctr:.2%} — below {CTR_FLOOR:.1%} floor, creative may be weak"))
        if 0 < m.roas < ROAS_FLOOR:
            out.append(Anomaly(m.label, "roas",
                               f"{m.roas:.2f}x — below 1.0x, losing money on spend"))
        return out

    def _summarize(self, report: AnalystReport) -> str:
        if not self.narrate_model:
            return self._template(report)
        try:
            from drip.llm import chat

            lines = [
                f"{v.metrics.platform} {v.metrics.label}: "
                f"spend ${v.metrics.spend:.0f}, CPP ${v.metrics.cpp:.2f}, "
                f"ROAS {v.metrics.roas:.2f}x -> {v.result.decision.headline} "
                f"({v.result.decision.confidence.value})"
                for v in report.verdicts
            ]
            anomalies = [f"{a.campaign}: {a.metric} {a.detail}" for a in report.anomalies]
            user = (
                "Write a 3-4 sentence morning report for a UA manager. Be concrete, "
                "lead with what needs attention.\n\n"
                f"CAMPAIGNS ({report.n_campaigns}, total spend ${report.total_spend:.0f}):\n"
                + "\n".join(lines)
                + ("\n\nANOMALIES:\n" + "\n".join(anomalies) if anomalies else "\n\nNo anomalies.")
            )
            result = chat(
                model=self.narrate_model,
                system="You are a senior UA manager writing a concise daily report.",
                messages=[{"role": "user", "content": user}],
                max_tokens=300, temperature=0.0,
            )
            return result.text or self._template(report)
        except Exception:
            return self._template(report)

    def _template(self, report: AnalystReport) -> str:
        actions = ", ".join(f"{n} {a}" for a, n in sorted(report.by_action.items()))
        parts = [
            f"Scanned {report.n_campaigns} campaigns, total spend "
            f"${report.total_spend:.0f}. Decisions: {actions or 'none'}."
        ]
        if report.anomalies:
            parts.append(f"{len(report.anomalies)} anomalies flagged: "
                         + "; ".join(f"{a.campaign} {a.metric}" for a in report.anomalies[:3])
                         + ("…" if len(report.anomalies) > 3 else "") + ".")
        else:
            parts.append("No anomalies flagged.")
        return " ".join(parts)
