"""Ads adapter — the WRITE side (reads live in ``drip.collectors``).

:class:`MetaWriter` pushes a SCALE / REDUCE / PAUSE decision to an **existing**
Meta campaign through the official Marketing API (``facebook-business`` SDK,
lazy-imported, same path the collector reads through). This is the real
money-moving write, gated three ways:

1. **DRIP_MODE** (upstream) — ``shadow`` never sends, ``copilot`` needs
   per-write human approval, ``autonomous`` sends within caps.
2. **token** — no ``META_ACCESS_TOKEN`` → returns a *shadow* result and never
   calls the API, so an accidental run can't move money before keys exist.
3. **money-safety guards** (:mod:`drip.safety`) — budget cap + max single-step
   change, checked by the caller before ``apply_decision``.

Every live write snapshots the old value first (verify + manual rollback) and
re-reads after to confirm the change actually landed. China-platform writers
live in :mod:`drip.adapters.writers`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_BUDGET_ACTIONS = {"SCALE", "REDUCE"}
_PAUSE_ACTIONS = {"PAUSE"}


def _cents(amount: float | None) -> int | None:
    """Meta budgets are minor units of the account currency (e.g. cents)."""
    return None if amount is None else round(float(amount) * 100)


@dataclass
class WriteResult:
    """Outcome of one mutate against an existing campaign."""

    platform: str
    target_id: str
    action: str
    field: str = ""              # "daily_budget" | "status" | ""
    old_value: Any = None
    new_value: Any = None
    status: str = "shadow"       # applied | shadow | skipped | denied | failed
    detail: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MetaWriter:
    """Real Meta Marketing API writer.

    ``level`` selects the entity that holds budget/status: ``"campaign"`` (CBO;
    matches the campaign-level pull in the collector) or ``"adset"``.
    """

    platform = "meta"

    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        *,
        level: str = "campaign",
    ) -> None:
        self.token = token if token is not None else os.getenv("META_ACCESS_TOKEN")
        self.account_id = account_id if account_id is not None else os.getenv("META_AD_ACCOUNT_ID")
        self.level = level

    @property
    def live(self) -> bool:
        """True only when a token is present — the gate against accidental spend."""
        return bool(self.token)

    def apply_decision(
        self,
        target_id: str,
        action: str,
        *,
        new_budget: float | None = None,
        dry_run: bool = False,
        label: str = "",
    ) -> WriteResult:
        """Push one decision to Meta. ``dry_run`` plans the write but never sends.

        Returns a :class:`WriteResult`; never raises (SDK/network errors become
        ``status="failed"``). Money-safety caps are the caller's responsibility
        (see :func:`drip.safety.guard_change`) — this method enforces only the
        token gate.
        """
        action = action.upper()
        res = WriteResult(platform="meta", target_id=target_id, action=action, label=label)

        # HOLD / REFRESH_CREATIVE never touch budget or status on the platform.
        if action not in _BUDGET_ACTIONS and action not in _PAUSE_ACTIONS:
            res.status = "skipped"
            res.detail = f"{action} is not a platform write"
            return res

        is_pause = action in _PAUSE_ACTIONS
        res.field = "status" if is_pause else "daily_budget"
        res.new_value = "PAUSED" if is_pause else _cents(new_budget)

        if not self.live:
            res.status = "shadow"
            res.detail = "no META_ACCESS_TOKEN — planned, not sent"
            return res

        try:
            return self._apply_live(res, is_pause, dry_run)
        except Exception as exc:  # pragma: no cover — only reachable with a live SDK
            from drip.log import logger
            logger.error("Meta write failed for %s: %s", res.target_id, exc, exc_info=True)
            res.status = "failed"
            res.detail = f"{type(exc).__name__}: {exc}"
            return res

    # -- live path -----------------------------------------------------------

    def _entity(self, target_id: str) -> Any:  # pragma: no cover — needs the SDK + a token
        from facebook_business.api import FacebookAdsApi

        FacebookAdsApi.init(access_token=self.token)
        if self.level == "adset":
            from facebook_business.adobjects.adset import AdSet

            return AdSet(target_id)
        from facebook_business.adobjects.campaign import Campaign

        return Campaign(target_id)

    def _apply_live(self, res: WriteResult, is_pause: bool, dry_run: bool) -> WriteResult:
        ent = self._entity(res.target_id)
        snap = ent.api_get(fields=["name", "status", "daily_budget"])
        res.old_value = _read(snap, "status" if is_pause else "daily_budget")

        if is_pause and str(res.old_value) == "PAUSED":
            res.status = "skipped"
            res.detail = "already PAUSED (idempotent — no write sent)"
            return res

        if dry_run:
            res.status = "shadow"
            res.detail = "dry-run — planned, not sent"
            return res

        params = {"status": "PAUSED"} if is_pause else {"daily_budget": res.new_value}
        ent.api_update(params=params)

        after = ent.api_get(fields=["status", "daily_budget"])
        got = _read(after, "status" if is_pause else "daily_budget")
        if str(got) == str(res.new_value):
            res.status = "applied"
        else:
            res.status = "failed"
            res.detail = f"post-write value {got!r} != intended {res.new_value!r}"
        return res


def _read(obj: Any, key: str) -> Any:
    """Field access that works across facebook-business object shapes and dicts."""
    getter = getattr(obj, "get", None)
    if callable(getter):
        return getter(key)
    try:
        return obj[key]
    except Exception:  # pragma: no cover
        return None
