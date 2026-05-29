"""Score one agent response against one case.

Three components:

- ``action_part`` — exact match on chosen_action gets ``action_match_max``;
  otherwise look up ``scoring.partial_credit`` for the chosen action.
- ``direction_part`` — only meaningful when both case and response carry a
  ``numeric_delta``. Same sign → proportional credit scaled by magnitude
  proximity. Different sign or missing → 0.
- ``reasoning_part`` — average over ReasoningChecks (full/partial/none)
  produced by the judge, multiplied by ``reasoning_max``.
"""

from __future__ import annotations

from drip.eval.schema import (
    AgentResponse,
    Case,
    CaseScore,
    ReasoningCheck,
)


def _action_part(case: Case, resp: AgentResponse) -> float:
    if resp.chosen_action == case.ground_truth.action:
        return float(case.scoring.action_match_max)
    return float(case.scoring.partial_credit.get(resp.chosen_action, 0))


def _direction_part(case: Case, resp: AgentResponse) -> float:
    gt_delta = case.ground_truth.numeric_delta
    if gt_delta is None or resp.numeric_delta is None:
        return 0.0
    if (gt_delta > 0) != (resp.numeric_delta > 0):
        return 0.0
    if gt_delta == 0 and resp.numeric_delta == 0:
        return float(case.scoring.direction_match_max)
    # Magnitude proximity: 1.0 when equal, 0 when 10x off.
    ratio = min(abs(gt_delta), abs(resp.numeric_delta)) / max(
        abs(gt_delta), abs(resp.numeric_delta)
    )
    return float(case.scoring.direction_match_max) * ratio


def _reasoning_part(case: Case, checks: list[ReasoningCheck]) -> float:
    if not checks:
        return 0.0
    avg = sum(c.numeric for c in checks) / len(checks)
    return float(case.scoring.reasoning_max) * avg


def score(
    case: Case,
    response: AgentResponse,
    reasoning_checks: list[ReasoningCheck],
) -> CaseScore:
    return CaseScore(
        case_id=case.id,
        chosen_action=response.chosen_action,
        ground_truth_action=case.ground_truth.action,
        action_part=_action_part(case, response),
        direction_part=_direction_part(case, response),
        reasoning_part=_reasoning_part(case, reasoning_checks),
        reasoning_checks=reasoning_checks,
    )
