"""Drip-Bench data model.

Cases are loaded from YAML files in ``benchmarks/cases/`` and validated
against :class:`Case`. Agents emit :class:`AgentResponse`. Scorers emit
:class:`CaseScore`. A bench run aggregates everything into
:class:`RunResult`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Category = Literal[
    "scale_decision",
    "pause_decision",
    "budget_reallocation",
    "creative_fatigue",
    "anomaly_diagnosis",
    "cohort_quality",
    "audience_expansion",
    "bid_strategy_switch",
    "market_entry",
    "crisis_response",
]

Difficulty = Literal["easy", "medium", "hard"]


class GroundTruth(BaseModel):
    action: str
    numeric_delta: float | None = None
    reasoning: str
    reasoning_must_mention: list[str] = Field(default_factory=list)


class Scoring(BaseModel):
    action_match_max: int = 40
    direction_match_max: int = 20
    reasoning_max: int = 40
    partial_credit: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_sums(self) -> Scoring:
        total = self.action_match_max + self.direction_match_max + self.reasoning_max
        if total != 100:
            raise ValueError(f"scoring components must sum to 100, got {total}")
        return self


class Case(BaseModel):
    id: int
    category: Category
    title: str
    difficulty: Difficulty
    context: str
    question: str
    choices: dict[str, str]
    ground_truth: GroundTruth
    scoring: Scoring = Field(default_factory=Scoring)
    source: str
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_truth_in_choices(self) -> Case:
        if self.ground_truth.action not in self.choices:
            raise ValueError(
                f"case {self.id}: ground_truth.action "
                f"{self.ground_truth.action!r} not in choices "
                f"{list(self.choices)}"
            )
        for k in self.scoring.partial_credit:
            if k not in self.choices:
                raise ValueError(
                    f"case {self.id}: partial_credit key {k!r} not in choices"
                )
        return self


class AgentResponse(BaseModel):
    """What an agent emits for one case."""

    chosen_action: str
    numeric_delta: float | None = None
    reasoning: str
    raw: dict[str, object] = Field(default_factory=dict)
    """Optional implementation-specific payload (prompt, tool calls, etc.)."""


class ReasoningCheck(BaseModel):
    mention: str
    coverage: Literal["full", "partial", "none"]
    notes: str = ""

    @property
    def numeric(self) -> float:
        return {"full": 1.0, "partial": 0.5, "none": 0.0}[self.coverage]


class CaseScore(BaseModel):
    case_id: int
    chosen_action: str
    ground_truth_action: str
    action_part: float
    direction_part: float
    reasoning_part: float
    reasoning_checks: list[ReasoningCheck] = Field(default_factory=list)

    @property
    def total(self) -> float:
        return self.action_part + self.direction_part + self.reasoning_part


class RunResult(BaseModel):
    agent_name: str
    started_at: datetime
    finished_at: datetime
    case_scores: list[CaseScore]
    notes: str = ""

    @property
    def total_score(self) -> float:
        return sum(s.total for s in self.case_scores)

    @property
    def max_score(self) -> float:
        return 100.0 * len(self.case_scores)

    def by_category(self) -> dict[str, float]:
        # Caller passes Case list for category if needed; here we keep it
        # simple and return per-case_id totals.
        return {str(s.case_id): s.total for s in self.case_scores}
