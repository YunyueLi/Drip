"""Centralised configuration — shared numeric defaults, the run-mode ladder,
and the money-safety env knobs, in one place.

Tunable thresholds and the ``DRIP_*`` money-safety vars live here so they're
discoverable without grepping. Platform credentials (``META_ACCESS_TOKEN`` etc.)
are intentionally read at their point of use (``collectors``/``adapters``), next
to the SDK call that needs them.

Import convention::

    from drip import config

    limit = config.get_budget_cap()
    target = config.DEFAULT_ROAS_TARGET
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared numeric defaults — used by pipeline, feedback, allocator
# ---------------------------------------------------------------------------

DEFAULT_CPP_TARGET = 25.0
DEFAULT_ROAS_TARGET = 3.0
DEFAULT_BUDGET_CAP = 1000.0

# ---------------------------------------------------------------------------
# Analyst anomaly-detection thresholds (analyst.py)
# ---------------------------------------------------------------------------

DEFAULT_FREQ_ALARM = 3.0       # frequency multiplier that triggers a burnout warning
DEFAULT_CTR_FLOOR = 0.005      # CTR below this floors as "creative may be weak"
DEFAULT_ROAS_FLOOR = 1.0       # ROAS below 1.0x flags "losing money on spend"

# ---------------------------------------------------------------------------
# Intraday spend-side thresholds (engine/intraday.py)
# ---------------------------------------------------------------------------

DEFAULT_EXHAUST_EARLY = 0.85   # budget-exhaustion day-fraction that triggers overpacing
DEFAULT_COST_THROTTLE = 1.5    # CPA / target ratio that triggers a throttle
DEFAULT_COST_PAUSE = 2.0       # CPA / target ratio that triggers a pause
DEFAULT_SPIKE_RATIO = 1.5      # recent-CPA / baseline ratio that counts as a spike
DEFAULT_THIN_CONV = 5          # min conversions before a spend-side action is trusted

# ---------------------------------------------------------------------------
# Money-safety caps (safety.py)
# ---------------------------------------------------------------------------

DEFAULT_MAX_CHANGE_PCT = 0.5

# ---------------------------------------------------------------------------
# CLI tuning
# ---------------------------------------------------------------------------

DEFAULT_WATCH_INTERVAL_MIN = 30

# ---------------------------------------------------------------------------
# Run mode — the money-safety ladder (DRIP_MODE)
# ---------------------------------------------------------------------------


class RunMode(str, Enum):
    """Money-safety ladder. ``shadow`` plans only and never writes; ``copilot``
    needs per-write human approval; ``autonomous`` writes within the caps."""

    SHADOW = "shadow"          # plan-only, no platform writes
    COPILOT = "copilot"        # writes require human approval
    AUTONOMOUS = "autonomous"  # writes freely up to budget caps


# ---------------------------------------------------------------------------
# Money-safety caps
# ---------------------------------------------------------------------------


def get_budget_cap() -> float:
    """Return ``DRIP_BUDGET_CAP`` (0 means unset / no cap).

    A malformed value raises rather than silently returning 0 — a money-safety
    limit must never fail open (a typo'd cap should stop the run, not disable it).
    """
    raw = os.getenv("DRIP_BUDGET_CAP", "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"DRIP_BUDGET_CAP must be a number (got {raw!r}); unset it for no cap."
        ) from exc


def get_max_change_pct() -> float:
    """Return ``DRIP_MAX_CHANGE_PCT``, defaulting to :data:`DEFAULT_MAX_CHANGE_PCT`."""
    raw = os.getenv("DRIP_MAX_CHANGE_PCT", "").strip()
    if not raw:
        return DEFAULT_MAX_CHANGE_PCT
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"DRIP_MAX_CHANGE_PCT must be a number (got {raw!r})."
        ) from exc


def get_audit_path() -> Path:
    """Return the audit trail path (``DRIP_AUDIT_PATH``)."""
    return Path(os.getenv("DRIP_AUDIT_PATH", "artifacts/audit/writes.jsonl"))
