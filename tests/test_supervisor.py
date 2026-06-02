"""Tests for the signal-driven supervisor — classification, routing, breaker."""

from __future__ import annotations

from drip.engine.rules import Action
from drip.supervisor import CircuitBreaker, Situation, classify, route


def test_classify_is_safety_first() -> None:
    assert classify([Action.SCALE, Action.PAUSE, Action.HOLD]) is Situation.BLEEDING
    assert classify([Action.SCALE, Action.HOLD]) is Situation.SCALING
    assert classify([Action.REFRESH_CREATIVE, Action.HOLD]) is Situation.FATIGUED
    assert classify([Action.HOLD, Action.HOLD]) is Situation.STEADY


def test_route_bleeding_stops_loss_first() -> None:
    r = route([Action.PAUSE, Action.SCALE])
    assert r.situation is Situation.BLEEDING
    assert r.steps[0].step == "stop-loss"
    assert all(s.why for s in r.steps)          # every step carries its reason
    assert "→" in r.summary


def test_route_scaling_and_steady() -> None:
    assert route([Action.SCALE]).steps[0].step == "scale-winners"
    assert route([Action.HOLD]).situation is Situation.STEADY


def test_breaker_halts_on_pause_anomaly() -> None:
    cb = CircuitBreaker()
    tripped, why = cb.pre_apply(n_total=10, n_pause=7)   # 70% want pause
    assert tripped and "anomaly" in why
    assert cb.pre_apply(n_total=10, n_pause=3) == (False, "")


def test_breaker_halts_on_write_failures() -> None:
    cb = CircuitBreaker()
    tripped, why = cb.post_write(n_attempted=6, n_failed=3)  # 50% failed
    assert tripped and "failed" in why
    assert cb.post_write(n_attempted=6, n_failed=1) == (False, "")


def test_breaker_no_campaigns_never_trips() -> None:
    cb = CircuitBreaker()
    assert cb.pre_apply(0, 0) == (False, "")
    assert cb.post_write(0, 0) == (False, "")
