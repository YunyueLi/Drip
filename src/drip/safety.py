"""Money-safety guards + an append-only audit trail for platform writes.

Every real mutate (a budget or status change pushed to an ad platform) passes
through :func:`guard_change` *before* the API call and is recorded by
:func:`audit` *after*. The guards are the hard floor under ``DRIP_MODE``: even an
``autonomous`` run cannot push a single campaign's daily budget above
``DRIP_BUDGET_CAP`` or move it by more than ``DRIP_MAX_CHANGE_PCT`` in one step
(a large jump would also reset the platform's learning phase — see
``docs/intraday-research.md``).

Pure stdlib — no provider deps — so it imports anywhere.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MAX_CHANGE_PCT = 0.5
_BUDGET_ACTIONS = {"SCALE", "REDUCE"}


class GuardError(RuntimeError):
    """A write was refused by a money-safety guard."""


@dataclass
class Caps:
    """Hard limits on a single budget write. ``budget_cap == 0`` means unset."""

    budget_cap: float = 0.0
    max_change_pct: float = DEFAULT_MAX_CHANGE_PCT

    @classmethod
    def from_env(cls) -> Caps:
        return cls(
            budget_cap=float(os.getenv("DRIP_BUDGET_CAP", "0") or 0),
            max_change_pct=float(
                os.getenv("DRIP_MAX_CHANGE_PCT", str(DEFAULT_MAX_CHANGE_PCT)) or DEFAULT_MAX_CHANGE_PCT
            ),
        )


def guard_change(*, action: str, old_budget: float, new_budget: float, caps: Caps) -> None:
    """Raise :class:`GuardError` if this change violates a money-safety cap.

    Only budget-moving actions (SCALE/REDUCE) are size-checked; PAUSE (→ $0) and
    non-spending actions are always allowed through.
    """
    if action.upper() not in _BUDGET_ACTIONS:
        return
    if caps.budget_cap and new_budget > caps.budget_cap:
        raise GuardError(
            f"new daily budget ${new_budget:,.2f} exceeds DRIP_BUDGET_CAP ${caps.budget_cap:,.2f}"
        )
    if old_budget > 0 and caps.max_change_pct:
        change = abs(new_budget - old_budget) / old_budget
        if change > caps.max_change_pct + 1e-9:
            raise GuardError(
                f"single-step change {change:.0%} exceeds DRIP_MAX_CHANGE_PCT "
                f"{caps.max_change_pct:.0%} — a jump this large resets the platform "
                f"learning phase; split it into smaller steps"
            )


def audit_path() -> Path:
    return Path(os.getenv("DRIP_AUDIT_PATH", "artifacts/audit/writes.jsonl"))


def audit(record: dict[str, Any]) -> Path:
    """Append one write record to the audit trail (JSONL). Returns the path.

    The trail is the accountability wall: who/when/old→new/result for every
    real or shadow write, so any change can be reviewed or rolled back.
    """
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
