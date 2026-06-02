"""Tests for the China-platform write adapters + the build_writer factory."""

from __future__ import annotations

import pytest

from drip.adapters.ads import MetaWriter, WriteResult
from drip.adapters.writers import (
    KuaishouWriter,
    OceanEngineWriter,
    PlatformWriter,
    TencentWriter,
    build_writer,
)


def test_no_token_is_shadow_never_sends() -> None:
    for w in (TencentWriter(token="", account_id=""),
              OceanEngineWriter(token="", account_id=""),
              KuaishouWriter(token="", account_id="")):
        assert w.live is False
        r = w.apply_decision("123", "SCALE", new_budget=240.0)
        assert r.status == "shadow"
        assert r.new_value is not None  # planned value still computed for the audit trail


def test_hold_and_refresh_are_not_writes() -> None:
    w = TencentWriter(token="t", account_id="a")
    for verb in ("HOLD", "REFRESH_CREATIVE"):
        assert w.apply_decision("123", verb).status == "skipped"


def test_tencent_field_mapping() -> None:
    w = TencentWriter(token="", account_id="")
    assert w.apply_decision("1", "PAUSE").field == "configured_status"
    assert w.apply_decision("1", "PAUSE").new_value == "AD_STATUS_SUSPEND"
    scale = w.apply_decision("1", "SCALE", new_budget=240.0)
    assert scale.field == "daily_budget" and scale.new_value == 24000  # 分


def test_oceanengine_field_mapping() -> None:
    w = OceanEngineWriter(token="", account_id="")
    assert w.apply_decision("1", "PAUSE").field == "opt_status"
    assert w.apply_decision("1", "PAUSE").new_value == "disable"
    scale = w.apply_decision("1", "REDUCE", new_budget=199.5)
    assert scale.field == "budget" and scale.new_value == 199.5  # 元


def test_dry_run_never_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    w = TencentWriter(token="t", account_id="a")
    sent = []
    monkeypatch.setattr(w, "_send", lambda res, is_pause: sent.append(res.target_id))
    r = w.apply_decision("1", "SCALE", new_budget=240.0, dry_run=True)
    assert r.status == "shadow" and sent == []


def test_live_path_calls_send(monkeypatch: pytest.MonkeyPatch) -> None:
    w = TencentWriter(token="t", account_id="acc")
    sent: list[str] = []
    monkeypatch.setattr(w, "_send", lambda res, is_pause: sent.append(res.field))
    r = w.apply_decision("9", "SCALE", new_budget=300.0)
    assert r.status == "applied"
    assert sent == ["daily_budget"]
    assert r.new_value == 30000


def test_failure_is_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    w = OceanEngineWriter(token="t", account_id="acc")

    def boom(res: WriteResult, is_pause: bool) -> None:
        raise RuntimeError("api 40001")

    monkeypatch.setattr(w, "_send", boom)
    r = w.apply_decision("9", "PAUSE")
    assert r.status == "failed" and "40001" in r.detail


def test_build_writer_routing() -> None:
    assert isinstance(build_writer("meta"), MetaWriter)
    assert isinstance(build_writer("tencent"), TencentWriter)
    assert isinstance(build_writer("巨量"), OceanEngineWriter)      # alias
    assert isinstance(build_writer("oceanengine"), OceanEngineWriter)
    assert isinstance(build_writer("kuaishou"), KuaishouWriter)
    # all satisfy the PlatformWriter contract
    for p in ("meta", "tencent", "oceanengine", "kuaishou"):
        assert isinstance(build_writer(p), PlatformWriter)


def test_build_writer_unknown_is_shadow() -> None:
    w = build_writer("snapchat")              # not implemented
    assert w.live is False
    assert w.apply_decision("1", "SCALE", new_budget=100.0).status == "shadow"
