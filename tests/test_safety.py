"""Money-safety guard behaviour lock.

Tests cover the three guardrails that protect real spend:
  - budget_cap: no single campaign can exceed the hard cap
  - max_change_pct: no single-step jump resets platform learning
  - audit: every write is recorded to an append-only JSONL trail

Pure stdlib — no provider deps — runs everywhere.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from drip.safety import Caps, GuardError, audit, guard_change

# ---------------------------------------------------------------------------
# GuardError
# ---------------------------------------------------------------------------


def test_guard_error_is_runtime_error() -> None:
    """GuardError is a RuntimeError so callers can catch it broadly."""
    with pytest.raises(RuntimeError):
        raise GuardError("test")
    with pytest.raises(GuardError):
        raise GuardError("test")


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------


def test_caps_defaults() -> None:
    """Sanity-check Caps defaults match config."""
    c = Caps()
    assert c.budget_cap == 0.0            # 0 = unset
    assert c.max_change_pct > 0.0         # must be non-zero for safety


def test_caps_override() -> None:
    c = Caps(budget_cap=500.0, max_change_pct=0.3)
    assert c.budget_cap == 500.0
    assert c.max_change_pct == 0.3


def test_caps_from_env_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIP_BUDGET_CAP", "800")
    monkeypatch.setenv("DRIP_MAX_CHANGE_PCT", "0.25")
    c = Caps.from_env()
    assert c.budget_cap == 800.0
    assert c.max_change_pct == 0.25


def test_caps_from_env_no_vars_uses_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRIP_BUDGET_CAP", raising=False)
    monkeypatch.delenv("DRIP_MAX_CHANGE_PCT", raising=False)
    c = Caps.from_env()
    assert c.budget_cap == 0.0            # unset → 0
    assert c.max_change_pct > 0.0


def test_caps_from_env_invalid_budget_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIP_BUDGET_CAP", "not-a-number")
    c = Caps.from_env()
    assert c.budget_cap == 0.0            # gracefully defaults to 0


# ---------------------------------------------------------------------------
# guard_change — the hard floor
# ---------------------------------------------------------------------------


@pytest.fixture
def caps() -> Caps:
    return Caps(budget_cap=1000.0, max_change_pct=0.5)


def test_non_budget_action_always_passes(caps: Caps) -> None:
    """PAUSE, HOLD, REFRESH_CREATIVE are never size-checked."""
    guard_change(action="PAUSE", old_budget=200.0, new_budget=0.0, caps=caps)
    guard_change(action="HOLD", old_budget=200.0, new_budget=200.0, caps=caps)
    guard_change(action="REFRESH_CREATIVE", old_budget=200.0, new_budget=200.0, caps=caps)


def test_action_case_insensitive(caps: Caps) -> None:
    guard_change(action="scale", old_budget=100.0, new_budget=120.0, caps=caps)


def test_budget_cap_exceeded_raises(caps: Caps) -> None:
    with pytest.raises(GuardError, match="DRIP_BUDGET_CAP"):
        guard_change(action="SCALE", old_budget=500.0, new_budget=1200.0, caps=caps)


def test_budget_within_cap_passes(caps: Caps) -> None:
    # 500→700 = +40% change, within 50% cap and under 1000 budget_cap
    guard_change(action="SCALE", old_budget=500.0, new_budget=700.0, caps=caps)


def test_zero_cap_means_unset(caps: Caps) -> None:
    """budget_cap == 0 and max_change_pct == 0 means both caps are off."""
    c = Caps(budget_cap=0.0, max_change_pct=0.0)
    guard_change(action="SCALE", old_budget=100.0, new_budget=999999.0, caps=c)


def test_max_change_pct_exceeded_raises(caps: Caps) -> None:
    old, new = 100.0, 160.0  # +60% > 50% cap
    with pytest.raises(GuardError, match="DRIP_MAX_CHANGE_PCT"):
        guard_change(action="SCALE", old_budget=old, new_budget=new, caps=caps)


def test_max_change_pct_within_limit_passes(caps: Caps) -> None:
    old, new = 100.0, 150.0  # exactly 50% — at boundary
    guard_change(action="SCALE", old_budget=old, new_budget=new, caps=caps)


def test_max_change_from_zero_old_budget_passes(caps: Caps) -> None:
    """old_budget == 0 → change is undefined; must not divide by zero."""
    guard_change(action="SCALE", old_budget=0.0, new_budget=500.0, caps=caps)


def test_reduce_within_limit_passes(caps: Caps) -> None:
    guard_change(action="REDUCE", old_budget=200.0, new_budget=120.0, caps=caps)  # -40%


def test_reduce_exceeds_limit_raises(caps: Caps) -> None:
    old, new = 200.0, 50.0  # -75% > 50% cap
    with pytest.raises(GuardError, match="DRIP_MAX_CHANGE_PCT"):
        guard_change(action="REDUCE", old_budget=old, new_budget=new, caps=caps)


def test_fuzzing_epsilon_boundary(caps: Caps) -> None:
    """The epsilon (1e-9) in guard_change should allow values exactly at the limit."""
    old = 100.0
    new = old * (1 + caps.max_change_pct)  # exactly at limit
    guard_change(action="SCALE", old_budget=old, new_budget=new, caps=caps)


# ---------------------------------------------------------------------------
# audit — append-only JSONL trail
# ---------------------------------------------------------------------------


def test_audit_appends_jsonl() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "writes.jsonl"
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DRIP_AUDIT_PATH", str(p))
            path = audit({"action": "SCALE", "old": 100.0, "new": 120.0})
            assert path == p
            assert p.exists()
            lines = p.read_text("utf-8").strip().split("\n")
            assert len(lines) == 1
            record = json.loads(lines[0])
            assert record["action"] == "SCALE"
            assert record["old"] == 100.0
            assert record["new"] == 120.0

            # Second write → second line
            audit({"action": "PAUSE", "old": 120.0, "new": 0.0})
            lines = p.read_text("utf-8").strip().split("\n")
            assert len(lines) == 2


def test_audit_creates_parent_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        nested = Path(tmp) / "deeply" / "nested" / "path" / "writes.jsonl"
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DRIP_AUDIT_PATH", str(nested))
            audit({"test": True})
            assert nested.exists()


def test_audit_handles_unicode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "writes.jsonl"
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DRIP_AUDIT_PATH", str(p))
            audit({"campaign": "测试活动", "detail": "成功 ¥€$"})
            record = json.loads(p.read_text("utf-8").strip())
            assert record["campaign"] == "测试活动"
            assert record["detail"] == "成功 ¥€$"


def test_audit_path_returns_pathlib_path() -> None:
    from drip.safety import audit_path
    p = audit_path()
    assert isinstance(p, Path)
