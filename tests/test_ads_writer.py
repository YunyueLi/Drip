"""Tests for the Meta write path (drip.adapters.ads) and money-safety (drip.safety).

The live SDK is never imported: we monkeypatch ``MetaWriter._entity`` with a
fake campaign object, so the real action→params mapping, snapshot, verify, and
idempotency logic are all exercised without facebook-business or a token.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from drip import safety
from drip.adapters.ads import MetaWriter, WriteResult, _cents


class FakeEntity:
    """Stand-in for a facebook-business Campaign/AdSet."""

    def __init__(self, status: str = "ACTIVE", daily_budget: int = 20000) -> None:
        self.state = {"name": "Camp", "status": status, "daily_budget": daily_budget}
        self.updates: list[dict[str, object]] = []

    def api_get(self, fields: object = None) -> dict[str, object]:
        return dict(self.state)

    def api_update(self, params: dict[str, object] | None = None) -> None:
        self.updates.append(dict(params or {}))
        self.state.update(params or {})


def _wire(monkeypatch: pytest.MonkeyPatch, ent: FakeEntity, **kw: object) -> MetaWriter:
    w = MetaWriter(token="TEST", **kw)  # type: ignore[arg-type]
    monkeypatch.setattr(w, "_entity", lambda target_id: ent)
    return w


def test_cents() -> None:
    assert _cents(240.0) == 24000
    assert _cents(199.99) == 19999
    assert _cents(None) is None


def test_no_token_is_shadow_never_calls_api() -> None:
    w = MetaWriter(token="")  # explicit empty → not live, regardless of env
    assert w.live is False
    r = w.apply_decision("c1", "SCALE", new_budget=240.0)
    assert r.status == "shadow"
    assert r.field == "daily_budget"
    assert r.new_value == 24000  # planned value still computed for the audit trail


def test_hold_and_refresh_are_not_platform_writes() -> None:
    w = MetaWriter(token="TEST")
    for verb in ("HOLD", "REFRESH_CREATIVE"):
        r = w.apply_decision("c1", verb)
        assert r.status == "skipped"
        assert r.field == ""


def test_scale_live_sets_daily_budget_in_cents(monkeypatch: pytest.MonkeyPatch) -> None:
    ent = FakeEntity(daily_budget=20000)
    w = _wire(monkeypatch, ent)
    r = w.apply_decision("c1", "SCALE", new_budget=240.0, label="Meta_v3")
    assert r.status == "applied"
    assert r.field == "daily_budget"
    assert r.old_value == 20000
    assert r.new_value == 24000
    assert ent.updates == [{"daily_budget": 24000}]


def test_pause_live_sets_status(monkeypatch: pytest.MonkeyPatch) -> None:
    ent = FakeEntity(status="ACTIVE")
    w = _wire(monkeypatch, ent)
    r = w.apply_decision("c1", "PAUSE")
    assert r.status == "applied"
    assert r.field == "status"
    assert ent.updates == [{"status": "PAUSED"}]


def test_pause_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    ent = FakeEntity(status="PAUSED")
    w = _wire(monkeypatch, ent)
    r = w.apply_decision("c1", "PAUSE")
    assert r.status == "skipped"
    assert "idempotent" in r.detail
    assert ent.updates == []  # no write sent


def test_dry_run_reads_but_never_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    ent = FakeEntity(daily_budget=20000)
    w = _wire(monkeypatch, ent)
    r = w.apply_decision("c1", "SCALE", new_budget=300.0, dry_run=True)
    assert r.status == "shadow"
    assert r.old_value == 20000   # snapshot was read for the preview
    assert ent.updates == []      # but nothing was written


def test_verify_catches_a_write_that_did_not_land(monkeypatch: pytest.MonkeyPatch) -> None:
    ent = FakeEntity(daily_budget=20000)

    def stubborn(params: dict[str, object] | None = None) -> None:  # records but doesn't apply
        ent.updates.append(dict(params or {}))

    ent.api_update = stubborn  # type: ignore[method-assign]
    w = _wire(monkeypatch, ent)
    r = w.apply_decision("c1", "SCALE", new_budget=240.0)
    assert r.status == "failed"
    assert "!=" in r.detail


# --- money-safety guards ---------------------------------------------------


def test_guard_allows_reasonable_scale() -> None:
    caps = safety.Caps(budget_cap=500.0, max_change_pct=0.5)
    safety.guard_change(action="SCALE", old_budget=200.0, new_budget=240.0, caps=caps)


def test_guard_blocks_over_budget_cap() -> None:
    caps = safety.Caps(budget_cap=500.0, max_change_pct=0.5)
    with pytest.raises(safety.GuardError):
        safety.guard_change(action="SCALE", old_budget=200.0, new_budget=600.0, caps=caps)


def test_guard_blocks_learning_phase_reset() -> None:
    caps = safety.Caps(budget_cap=0.0, max_change_pct=0.5)  # no cap, but magnitude limited
    with pytest.raises(safety.GuardError):
        safety.guard_change(action="SCALE", old_budget=100.0, new_budget=300.0, caps=caps)


def test_guard_always_allows_pause() -> None:
    caps = safety.Caps(budget_cap=10.0, max_change_pct=0.1)
    safety.guard_change(action="PAUSE", old_budget=200.0, new_budget=0.0, caps=caps)


def test_audit_appends_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "writes.jsonl"
    monkeypatch.setenv("DRIP_AUDIT_PATH", str(path))
    safety.audit({"action": "SCALE", "status": "applied"})
    safety.audit({"action": "PAUSE", "status": "applied"})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["action"] == "SCALE"


def test_write_result_to_dict_roundtrips() -> None:
    r = WriteResult(platform="meta", target_id="c1", action="SCALE", new_value=24000)
    d = r.to_dict()
    assert d["platform"] == "meta" and d["new_value"] == 24000
