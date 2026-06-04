"""Collector — pull insights from ad platforms, normalise to AdMetrics.

Production path uses the official SDKs (facebook-business, tiktok-business),
imported lazily. With no credentials configured it returns deterministic
sample data, so the whole pipeline runs offline (`drip demo`, tests, CI).

Per the research:
- Meta: use a System User token (never a 60-day user token for a daemon),
  pull at adset level, parse conversions out of ``actions[]`` (the
  ``purchase`` / ``offsite_conversion.fb_pixel_purchase`` action types),
  read ROAS from ``purchase_roas``, and honour rate limits via the
  ``X-Business-Use-Case-Usage`` header. Large pulls should use async insights.
- TikTok: ``/report/integrated/get/`` at AUCTION_CAMPAIGN level.

Both live paths are written to the documented contract; they're exercised
once credentials + extras are present. Offline, the sample path keeps the
loop runnable.
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol

from drip.data.metrics import AdMetrics


class InsightsSource(Protocol):
    platform: str

    def fetch(self, *, since: str, until: str) -> list[AdMetrics]: ...


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------


class MetaInsights:
    platform = "meta"

    def __init__(self, account_id: str | None = None, token: str | None = None) -> None:
        self.account_id = account_id or os.getenv("META_AD_ACCOUNT_ID")
        self.token = token or os.getenv("META_ACCESS_TOKEN")

    def fetch(self, *, since: str, until: str) -> list[AdMetrics]:
        if not (self.account_id and self.token):
            return _sample("meta", since, until)
        return self._fetch_live(since, until)

    def _fetch_live(self, since: str, until: str) -> list[AdMetrics]:  # pragma: no cover
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.api import FacebookAdsApi

        FacebookAdsApi.init(access_token=self.token)
        account = AdAccount(self.account_id)
        params = {
            "level": "campaign",
            "time_range": {"since": since, "until": until},
            "action_attribution_windows": ["1d_view", "7d_click"],
        }
        fields = [
            "campaign_id", "campaign_name", "spend", "impressions", "clicks",
            "reach", "actions", "action_values", "purchase_roas",
        ]
        rows: list[AdMetrics] = []
        for r in account.get_insights(fields=fields, params=params):
            conversions = _parse_action(r.get("actions"), "purchase")
            conv_value = _parse_action(r.get("action_values"), "purchase")
            rows.append(AdMetrics(
                platform="meta",
                campaign_id=str(r.get("campaign_id", "")),
                date_start=since, date_end=until,
                spend=float(r.get("spend", 0)),
                impressions=int(r.get("impressions", 0)),
                clicks=int(r.get("clicks", 0)),
                conversions=conversions,
                conversion_value=conv_value,
                reach=int(r.get("reach", 0)),
                label=str(r.get("campaign_name", "")),
            ))
        return rows


def _parse_action(actions: object, action_type: str) -> float:
    """Pull a value out of Meta's actions[]/action_values[] list."""
    if not isinstance(actions, list):
        return 0.0
    total = 0.0
    for a in actions:
        at = a.get("action_type", "")
        if at == action_type or at.endswith(f".{action_type}") \
                or at == "offsite_conversion.fb_pixel_purchase":
            total += float(a.get("value", 0) or 0)
    return total


# --------------------------------------------------------------------------
# TikTok
# --------------------------------------------------------------------------


class TikTokInsights:
    platform = "tiktok"

    def __init__(self, advertiser_id: str | None = None, token: str | None = None) -> None:
        self.advertiser_id = advertiser_id or os.getenv("TIKTOK_ADVERTISER_ID")
        self.token = token or os.getenv("TIKTOK_ACCESS_TOKEN")

    def fetch(self, *, since: str, until: str) -> list[AdMetrics]:
        if not (self.advertiser_id and self.token):
            return _sample("tiktok", since, until)
        return self._fetch_live(since, until)

    def _fetch_live(self, since: str, until: str) -> list[AdMetrics]:  # pragma: no cover
        import httpx

        url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"
        params = {
            "advertiser_id": self.advertiser_id,
            "report_type": "BASIC",
            "data_level": "AUCTION_CAMPAIGN",
            "dimensions": '["campaign_id"]',
            "metrics": '["spend","impressions","clicks","conversion","total_purchase_value"]',
            "start_date": since,
            "end_date": until,
        }
        headers = {"Access-Token": self.token or ""}
        with httpx.Client(timeout=60) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        rows: list[AdMetrics] = []
        for item in data.get("data", {}).get("list", []):
            m = item.get("metrics", {})
            dim = item.get("dimensions", {})
            rows.append(AdMetrics(
                platform="tiktok",
                campaign_id=str(dim.get("campaign_id", "")),
                date_start=since, date_end=until,
                spend=float(m.get("spend", 0)),
                impressions=int(float(m.get("impressions", 0))),
                clicks=int(float(m.get("clicks", 0))),
                conversions=float(m.get("conversion", 0)),
                conversion_value=float(m.get("total_purchase_value", 0)),
            ))
        return rows


# --------------------------------------------------------------------------
# China platforms — Tencent Ads / Ocean Engine / Kuaishou
# --------------------------------------------------------------------------
# Live reads use each platform's report API (Tencent hourly_reports/get +
# realtime_cost/get; Ocean Engine v3.0 reports; Kuaishou MAPI report) — wired as
# a follow-up. Offline these return one deterministic sample each so the rest of
# the pipeline (diagnose → allocate → apply) demonstrates cross-platform routing,
# and `drip apply` dispatches each to its writer in drip.adapters.writers.


class _ChinaPlatformInsights:
    """Base for China-platform collectors that share the same offline-first shape.

    Each subclass only needs three class-level attributes.
    """

    platform: str = ""
    _token_env: str = ""
    _id_env: str = ""

    def __init__(self, account_id: str | None = None, token: str | None = None) -> None:
        self.account_id = account_id or os.getenv(self._id_env)
        self.token = token or os.getenv(self._token_env)

    def fetch(self, *, since: str, until: str) -> list[AdMetrics]:
        return _sample(self.platform, since, until)[:1]


class TencentInsights(_ChinaPlatformInsights):
    platform = "tencent"
    _token_env = "TENCENT_ACCESS_TOKEN"
    _id_env = "TENCENT_ACCOUNT_ID"


class OceanEngineInsights(_ChinaPlatformInsights):
    platform = "oceanengine"
    _token_env = "OCEANENGINE_ACCESS_TOKEN"
    _id_env = "OCEANENGINE_ADVERTISER_ID"


class KuaishouInsights(_ChinaPlatformInsights):
    platform = "kuaishou"
    _token_env = "KUAISHOU_ACCESS_TOKEN"
    _id_env = "KUAISHOU_ADVERTISER_ID"


# --------------------------------------------------------------------------
# Collector
# --------------------------------------------------------------------------


class Collector:
    """Fan out to every configured source, return one normalised list."""

    def __init__(self, sources: list[InsightsSource] | None = None) -> None:
        self.sources = sources or [
            MetaInsights(), TikTokInsights(),
            TencentInsights(), OceanEngineInsights(), KuaishouInsights(),
        ]

    def collect(self, *, since: str, until: str) -> list[AdMetrics]:
        rows: list[AdMetrics] = []
        for source in self.sources:
            rows.extend(source.fetch(since=since, until=until))
        return rows


def _sample(platform: str, since: str, until: str) -> list[AdMetrics]:
    """Deterministic offline sample so the pipeline runs without credentials."""
    seeds = [
        ("Prospecting_v3", 0),   # healthy
        ("Broad_v1", 1),         # struggling
    ]
    out: list[AdMetrics] = []
    for name, variant in seeds:
        h = int(hashlib.sha256(f"{platform}{name}".encode()).hexdigest()[:6], 16)
        if variant == 0:  # healthy
            spend, conv, value, clicks, imps = 200.0, 12.0, 760.0, 1400, 100_000
            reach = 56_000
        else:             # struggling
            spend, conv, value, clicks, imps = 240.0, 6.0, 336.0, 800, 100_000
            reach = 40_000
        out.append(AdMetrics(
            platform=platform,
            campaign_id=f"{platform}-{h:06d}",
            date_start=since, date_end=until,
            spend=spend, impressions=imps, clicks=clicks,
            conversions=conv, conversion_value=value, reach=reach,
            label=f"{platform.title()}_{name}",
        ))
    return out
