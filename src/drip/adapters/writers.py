"""Platform write adapters beyond Meta — Tencent Ads, Ocean Engine, Kuaishou.

Same contract as :class:`drip.adapters.ads.MetaWriter`: ``apply_decision`` returns
a :class:`~drip.adapters.ads.WriteResult`, gated on a per-platform token (no
token → a *shadow* result, never a network call), with the money-safety guards
(:mod:`drip.safety`) enforced by the caller. These speak the platforms' REST
Marketing APIs over ``httpx`` (a core dep — no per-vendor SDK).

Endpoints + field mappings are from ``docs/intraday-research.md`` (official docs
/ SDK source). The live HTTP methods are ``# pragma: no cover`` — exercised only
with real credentials, same maturity as the Meta path. **Verify against your own
account**: each platform's auth ceremony (timestamp / nonce / signature) and
budget unit (分 vs 元) must match its current spec before a live run.

Use :func:`build_writer` to get the right writer for a platform; unknown or
token-less platforms degrade to a shadow writer so the pipeline always runs.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

import httpx

from drip.adapters.ads import MetaWriter, WriteResult, _cents
from drip.log import logger

_BUDGET_ACTIONS = {"SCALE", "REDUCE"}
_PAUSE_ACTIONS = {"PAUSE"}


@runtime_checkable
class PlatformWriter(Protocol):
    """The write contract every platform implements (MetaWriter included)."""

    platform: str

    @property
    def live(self) -> bool: ...

    def apply_decision(
        self, target_id: str, action: str, *,
        new_budget: float | None = None, dry_run: bool = False, label: str = "",
    ) -> WriteResult: ...


class _RestWriter:
    """Shared skeleton for REST-API writers (Tencent / Ocean Engine / Kuaishou).

    Subclasses set ``platform`` and implement ``_send`` (the live HTTP call) and
    ``_plan`` (action → field + intended value). Everything else — the token
    gate, shadow fallback, dry-run, and error handling — is shared.
    """

    platform = "rest"

    def __init__(self, token: str | None = None, account_id: str | None = None,
                 *, level: str = "campaign") -> None:
        self.token = token
        self.account_id = account_id
        self.level = level

    @property
    def live(self) -> bool:
        return bool(self.token and self.account_id)

    # subclasses override -----------------------------------------------------

    def _plan(self, res: WriteResult, is_pause: bool, new_budget: float | None) -> None:
        """Fill res.field + res.new_value for this platform."""
        res.field = "status" if is_pause else "daily_budget"
        res.new_value = "PAUSED" if is_pause else _cents(new_budget)

    def _send(self, res: WriteResult, is_pause: bool) -> None:  # pragma: no cover — needs creds
        raise NotImplementedError

    # shared ------------------------------------------------------------------

    def apply_decision(
        self, target_id: str, action: str, *,
        new_budget: float | None = None, dry_run: bool = False, label: str = "",
    ) -> WriteResult:
        action = action.upper()
        res = WriteResult(platform=self.platform, target_id=target_id, action=action, label=label)
        if action not in _BUDGET_ACTIONS and action not in _PAUSE_ACTIONS:
            res.status, res.detail = "skipped", f"{action} is not a platform write"
            return res
        is_pause = action in _PAUSE_ACTIONS
        self._plan(res, is_pause, new_budget)
        if not self.live:
            res.status = "shadow"
            res.detail = f"no {self.platform.upper()} token/account — planned, not sent"
            return res
        if dry_run:
            res.status, res.detail = "shadow", "dry-run — planned, not sent"
            return res
        try:
            self._send(res, is_pause)
            res.status = "applied"
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, httpx.HTTPError) as exc:  # pragma: no cover — live only
            logger.error("write failed for %s/%s: %s", self.platform, res.target_id, exc, exc_info=True)
            res.status, res.detail = "failed", f"{type(exc).__name__}: {exc}"
        return res


class TencentWriter(_RestWriter):
    """腾讯广告 Marketing API v3.0 — campaigns/update (daily_budget 分 / configured_status)."""

    platform = "tencent"
    BASE = "https://api.e.qq.com/v3.0"

    def __init__(self, token: str | None = None, account_id: str | None = None,
                 *, level: str = "campaign") -> None:
        super().__init__(
            token if token is not None else os.getenv("TENCENT_ACCESS_TOKEN"),
            account_id if account_id is not None else os.getenv("TENCENT_ACCOUNT_ID"),
            level=level,
        )

    def _plan(self, res: WriteResult, is_pause: bool, new_budget: float | None) -> None:
        res.field = "configured_status" if is_pause else "daily_budget"
        res.new_value = "AD_STATUS_SUSPEND" if is_pause else _cents(new_budget)  # 分

    def _send(self, res: WriteResult, is_pause: bool) -> None:  # pragma: no cover — needs creds
        import time

        import httpx

        path = "campaigns/update" if self.level == "campaign" else "adgroups/update"
        id_field = "campaign_id" if self.level == "campaign" else "adgroup_id"
        body: dict[str, Any] = {"account_id": self.account_id, id_field: int(res.target_id)}
        if is_pause:
            body["configured_status"] = "AD_STATUS_SUSPEND"
        else:
            body["daily_budget"] = res.new_value
        # NOTE: verify the common params (timestamp/nonce) against the current v3.0 spec.
        params = {"access_token": self.token, "timestamp": int(time.time()), "nonce": str(time.time_ns())}
        r = httpx.post(f"{self.BASE}/{path}", params=params, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(f"tencent code={data.get('code')}: {data.get('message')}")


class OceanEngineWriter(_RestWriter):
    """巨量引擎 Marketing API v3.0 — promotion/budget/update + promotion/status/update."""

    platform = "oceanengine"
    BASE = "https://api.oceanengine.com/open_api/v3.0"

    def __init__(self, token: str | None = None, account_id: str | None = None,
                 *, level: str = "promotion") -> None:
        super().__init__(
            token if token is not None else os.getenv("OCEANENGINE_ACCESS_TOKEN"),
            account_id if account_id is not None else os.getenv("OCEANENGINE_ADVERTISER_ID"),
            level=level,
        )

    def _plan(self, res: WriteResult, is_pause: bool, new_budget: float | None) -> None:
        res.field = "opt_status" if is_pause else "budget"
        # NOTE: Ocean Engine budget unit (元 vs 分) — verify per the report API; sent as 元 here.
        res.new_value = "disable" if is_pause else (None if new_budget is None else round(float(new_budget), 2))

    def _send(self, res: WriteResult, is_pause: bool) -> None:  # pragma: no cover — needs creds
        import httpx

        headers = {"Access-Token": self.token or "", "Content-Type": "application/json"}
        body: dict[str, Any]
        if is_pause:
            url = f"{self.BASE}/promotion/status/update/"
            body = {"advertiser_id": self.account_id,
                    "promotion_ids": [int(res.target_id)], "opt_status": "disable"}
        else:
            url = f"{self.BASE}/promotion/budget/update/"
            body = {"advertiser_id": self.account_id,
                    "data": [{"promotion_id": int(res.target_id), "budget": res.new_value}]}
        r = httpx.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("code") not in (0, None):
            raise RuntimeError(f"oceanengine code={data.get('code')}: {data.get('message')}")


class KuaishouWriter(_RestWriter):
    """快手磁力引擎 Marketing API — unit/budget update.

    Public docs for the write endpoints are thin (see research caveats); this
    maps the contract and gates on a token, but the exact path/fields **must be
    confirmed** against the 磁力开放平台 before a live run. Shadow until then.
    """

    platform = "kuaishou"
    BASE = "https://gw.e.kuaishou.com/rest/openapi/v1"

    def __init__(self, token: str | None = None, account_id: str | None = None,
                 *, level: str = "unit") -> None:
        super().__init__(
            token if token is not None else os.getenv("KUAISHOU_ACCESS_TOKEN"),
            account_id if account_id is not None else os.getenv("KUAISHOU_ADVERTISER_ID"),
            level=level,
        )

    def _plan(self, res: WriteResult, is_pause: bool, new_budget: float | None) -> None:
        res.field = "put_status" if is_pause else "day_budget"
        res.new_value = "PAUSE" if is_pause else _cents(new_budget)  # 厘? verify unit

    def _send(self, res: WriteResult, is_pause: bool) -> None:  # pragma: no cover — endpoint unconfirmed
        raise RuntimeError("kuaishou write endpoint unconfirmed — see docs/intraday-research.md")


_WRITERS: dict[str, type[_RestWriter]] = {
    "tencent": TencentWriter,
    "oceanengine": OceanEngineWriter,
    "kuaishou": KuaishouWriter,
}
# friendly aliases
_ALIAS = {"巨量": "oceanengine", "巨量引擎": "oceanengine", "ocean": "oceanengine",
          "腾讯": "tencent", "腾讯广告": "tencent", "tencent_ads": "tencent",
          "快手": "kuaishou", "ks": "kuaishou"}


def build_writer(platform: str, *, level: str | None = None) -> PlatformWriter:
    """Return the write adapter for a platform. Meta uses the SDK writer; the
    others use REST writers. Unknown platform → a token-less shadow writer."""
    key = _ALIAS.get(platform, platform).lower()
    if key == "meta":
        return MetaWriter(level=level or "campaign")
    cls = _WRITERS.get(key)
    if cls is None:
        # unknown platform: a Tencent-shaped writer with no token → always shadow
        w = TencentWriter(token="", account_id="")
        w.platform = key
        return w
    return cls(level=level) if level else cls()
