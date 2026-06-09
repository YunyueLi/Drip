"""Drip-Bench behaviour lock — scoring math, schema validation, and an
offline end-to-end smoke (dummy agent + heuristic judge, no API key)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from drip.eval.bench import run_bench
from drip.eval.schema import (
    AgentResponse,
    Case,
    GroundTruth,
    ReasoningCheck,
    Scoring,
)
from drip.eval.scorer import score


def _case(
    *,
    gt_action: str = "A",
    gt_delta: float | None = None,
    choices: dict[str, str] | None = None,
    partial: dict[str, int] | None = None,
) -> Case:
    return Case(
        id=1, category="scale_decision", title="t", difficulty="easy",
        context="ctx", question="q",
        choices=choices or {"A": "SCALE +20%", "B": "HOLD"},
        ground_truth=GroundTruth(action=gt_action, numeric_delta=gt_delta, reasoning="r"),
        scoring=Scoring(partial_credit=partial or {}),
        source="unit-test",
    )


def _resp(action: str, delta: float | None = None) -> AgentResponse:
    return AgentResponse(chosen_action=action, numeric_delta=delta, reasoning="because")


# --- action component --------------------------------------------------------

def test_action_exact_match_full_credit() -> None:
    s = score(_case(gt_action="A"), _resp("A"), [])
    assert s.action_part == 40.0


def test_action_partial_credit() -> None:
    s = score(_case(gt_action="A", partial={"B": 10}), _resp("B"), [])
    assert s.action_part == 10.0


def test_action_wrong_no_partial_zero() -> None:
    s = score(_case(gt_action="A"), _resp("B"), [])
    assert s.action_part == 0.0


# --- direction component -----------------------------------------------------

def test_direction_equal_delta_full() -> None:
    s = score(_case(gt_action="A", gt_delta=0.2), _resp("A", 0.2), [])
    assert s.direction_part == 20.0


def test_direction_same_sign_proportional() -> None:
    # ratio = min/max = 0.1/0.2 = 0.5 → 20 * 0.5 = 10.
    s = score(_case(gt_action="A", gt_delta=0.2), _resp("A", 0.1), [])
    assert s.direction_part == 10.0


def test_direction_opposite_sign_zero() -> None:
    s = score(_case(gt_action="A", gt_delta=0.2), _resp("A", -0.1), [])
    assert s.direction_part == 0.0


def test_direction_missing_delta_zero() -> None:
    s = score(_case(gt_action="A", gt_delta=0.2), _resp("A", None), [])
    assert s.direction_part == 0.0


# --- reasoning component -----------------------------------------------------

def test_reasoning_averages_checks() -> None:
    checks = [
        ReasoningCheck(mention="x", coverage="full"),     # 1.0
        ReasoningCheck(mention="y", coverage="partial"),  # 0.5
        ReasoningCheck(mention="z", coverage="none"),     # 0.0
    ]
    s = score(_case(), _resp("A"), checks)
    assert s.reasoning_part == pytest.approx(40.0 * 0.5)


def test_reasoning_no_checks_zero() -> None:
    assert score(_case(), _resp("A"), []).reasoning_part == 0.0


# --- schema validation -------------------------------------------------------

def test_scoring_components_must_sum_to_100() -> None:
    with pytest.raises(ValidationError, match="sum to 100"):
        Scoring(action_match_max=40, direction_match_max=20, reasoning_max=30)


def test_ground_truth_action_must_be_a_choice() -> None:
    with pytest.raises(ValidationError, match="not in choices"):
        _case(gt_action="Z")  # Z is not in {A, B}


def test_partial_credit_key_must_be_a_choice() -> None:
    with pytest.raises(ValidationError, match="partial_credit"):
        _case(partial={"Z": 5})


# --- offline end-to-end smoke ------------------------------------------------

def test_run_bench_dummy_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the heuristic judge (no LLM key) so the run is fully offline.
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    result = run_bench(agent_name="dummy", write_bundle=False)
    assert len(result.case_scores) >= 1
    assert 0.0 <= result.total_score <= result.max_score
    # Every case score carries the three components that sum to its total.
    for s in result.case_scores:
        assert s.total == s.action_part + s.direction_part + s.reasoning_part
