"""Centralised configuration — one place for every env var and shared default.

Every ``os.getenv`` call and magic number that's scattered across the codebase
should migrate here. This module documents every knob in one file so a new
developer doesn't have to grep for ``os.getenv`` to understand what's tunable.

Import convention::

    from drip import config

    limit = config.get_budget_cap()
    target = config.DEFAULT_ROAS_TARGET
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared numeric defaults — used by pipeline, graph, feedback, allocator
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
# Run mode
# ---------------------------------------------------------------------------


def get_mode(default: str = "shadow") -> str:
    """Resolve ``DRIP_MODE``. Default is ``"shadow"`` — plan only, no writes."""
    return os.getenv("DRIP_MODE", default)


# ---------------------------------------------------------------------------
# Money-safety caps
# ---------------------------------------------------------------------------


def get_budget_cap() -> float:
    """Return ``DRIP_BUDGET_CAP`` (0 means unset / no cap)."""
    raw = os.getenv("DRIP_BUDGET_CAP", "")
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def get_max_change_pct() -> float:
    """Return ``DRIP_MAX_CHANGE_PCT``, defaulting to :data:`DEFAULT_MAX_CHANGE_PCT`."""
    return float(os.getenv("DRIP_MAX_CHANGE_PCT", str(DEFAULT_MAX_CHANGE_PCT))
                 or DEFAULT_MAX_CHANGE_PCT)


def get_audit_path() -> Path:
    """Return the audit trail path (``DRIP_AUDIT_PATH``)."""
    return Path(os.getenv("DRIP_AUDIT_PATH", "artifacts/audit/writes.jsonl"))


# ---------------------------------------------------------------------------
# Platform credentials — documented here so they're discoverable
# ---------------------------------------------------------------------------

# Each function mirrors the pattern already used by collectors.py / providers.py.
# They stay tiny so the config module is importable with zero side effects.


def get_meta_token() -> str | None:
    return os.getenv("META_ACCESS_TOKEN")


def get_meta_account_id() -> str | None:
    return os.getenv("META_AD_ACCOUNT_ID")


def get_tiktok_token() -> str | None:
    return os.getenv("TIKTOK_ACCESS_TOKEN")


def get_tiktok_advertiser_id() -> str | None:
    return os.getenv("TIKTOK_ADVERTISER_ID")


def get_tencent_token() -> str | None:
    return os.getenv("TENCENT_ACCESS_TOKEN")


def get_tencent_account_id() -> str | None:
    return os.getenv("TENCENT_ACCOUNT_ID")


def get_oceanengine_token() -> str | None:
    return os.getenv("OCEANENGINE_ACCESS_TOKEN")


def get_oceanengine_advertiser_id() -> str | None:
    return os.getenv("OCEANENGINE_ADVERTISER_ID")


def get_kuaishou_token() -> str | None:
    return os.getenv("KUAISHOU_ACCESS_TOKEN")


def get_kuaishou_advertiser_id() -> str | None:
    return os.getenv("KUAISHOU_ADVERTISER_ID")


def get_openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_anthropic_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")
