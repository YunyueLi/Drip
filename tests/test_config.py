"""Config behaviour lock — money-safety env knobs fail loud, RunMode round-trips."""

from __future__ import annotations

import pytest

from drip import config
from drip.config import RunMode


def test_budget_cap_unset_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRIP_BUDGET_CAP", raising=False)
    assert config.get_budget_cap() == 0.0


def test_budget_cap_valid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIP_BUDGET_CAP", "500")
    assert config.get_budget_cap() == 500.0


def test_budget_cap_malformed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # A money-safety cap must fail loud, never silently disable itself (fail-open).
    monkeypatch.setenv("DRIP_BUDGET_CAP", "abc")
    with pytest.raises(ValueError, match="DRIP_BUDGET_CAP"):
        config.get_budget_cap()


def test_max_change_pct_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRIP_MAX_CHANGE_PCT", raising=False)
    assert config.get_max_change_pct() == config.DEFAULT_MAX_CHANGE_PCT


def test_max_change_pct_malformed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIP_MAX_CHANGE_PCT", "xyz")
    with pytest.raises(ValueError, match="DRIP_MAX_CHANGE_PCT"):
        config.get_max_change_pct()


def test_runmode_round_trips() -> None:
    for m in RunMode:
        assert RunMode(m.value) is m
    assert {m.value for m in RunMode} == {"shadow", "copilot", "autonomous"}
