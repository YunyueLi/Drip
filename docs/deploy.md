# Deploying Drip to production

Drip runs fully offline out of the box (sample data, template reports, dry
creative, shadow bidding). Going live is three steps — no code change, just
configuration. This is the path from "runs on my laptop" to "spends real
money safely".

## The three steps from offline → live

1. **Credentials** — connect the ad platforms and an LLM.
2. **Extras** — install the provider SDKs (lazy-imported; only needed live).
3. **Mode** — climb the `DRIP_MODE` ladder (shadow → copilot → autonomous) and
   schedule the gated write commands (`drip apply` / `watch` / `autopilot`).

Each is independent — you can connect Meta and stay in shadow mode for weeks
before flipping a single campaign to live.

## 1. Install

```bash
uv venv -p 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"          # core + tests, runs offline
uv pip install -e ".[all]"          # + provider SDKs for live runs
```

## 2. Credentials

Copy `.env.example` → `.env` and fill only what you use.

**Meta (most important details, per the API):**
- Use a **System User token** (Business Settings → System Users), never a
  60-day user token for a daemon. Scopes: `ads_read`, `ads_management`.
- `META_AD_ACCOUNT_ID`, `META_ACCESS_TOKEN`.
- The Collector pulls campaign insights, parses conversions out of `actions[]`,
  reads ROAS from `purchase_roas`, and honours the `X-Business-Use-Case-Usage`
  header for rate limiting. Large pulls should use async insights.
- Note the **2026-01-12 attribution change**: `7d_view`/`28d_view` are gone;
  default is `1d_view` + `7d_click`. The Collector already requests that.

**TikTok:** `TIKTOK_ADVERTISER_ID`, `TIKTOK_ACCESS_TOKEN` (OAuth).

**LLM:** any one of the providers in `drip llm` (e.g. `ANTHROPIC_API_KEY`).
Pass `--narrate <provider/model>` to turn template reports/briefs into AI ones.

**Attribution truth:** Drip applies a documented haircut to platform-reported
ROAS by default. For ground truth, plug an MMP (AppsFlyer/Adjust) into
`Attribution.reconcile(..., mmp_roas_by_campaign=...)`.

## 3. Production orchestration

The lightweight `drip run` (Pipeline) is fine for one-shot and cron. To actually
push decisions on a schedule, use the gated write commands — each snapshots the
old value, re-reads to verify it landed, and appends to the audit trail:

```bash
# daily: diagnose → allocate → push (copilot asks before each write)
drip apply --mode copilot

# intraday: pacing / cost-spike / anti-overspend guard, every 30 min
drip watch --interval 30

# the whole loop, signal-routed, behind a circuit breaker
drip autopilot --mode autonomous
```

- **approval gate** (`copilot`) → every budget move waits for a human y/N before it's sent.
- **circuit breaker** (`autopilot`) → halts on a data anomaly (most of the
  account wanting to pause) or repeated write failures.
- **audit trail** → every write, real or shadow, lands in `DRIP_AUDIT_PATH` as
  append-only JSONL.
- wrap any of these in **cron / systemd / Temporal** for scheduled runs +
  crash-replay at scale.

## 4. Run modes (the money safety ladder)

Set `DRIP_MODE`:

| Mode | Behaviour | Use when |
| --- | --- | --- |
| `shadow` (default) | plan only, never write to platforms | first weeks, building trust |
| `copilot` | every write waits for approval | careful scaling, new accounts |
| `autonomous` | writes up to `DRIP_BUDGET_CAP` | steady state, proven setup |

`DRIP_BUDGET_CAP` is a hard wall checked before the supervisor starts. Even an
accidental `autonomous` run can't exceed it.

## 5. Go-live checklist

- [ ] `drip run` works offline (samples) — sanity check the loop
- [ ] `.env` has a System User token + LLM key
- [ ] `drip run --narrate <model>` produces a real AI report
- [ ] one campaign in `copilot` mode, approve one decision, verify the platform write
- [ ] `drip bench run --agent drip` — record your decision-quality score
- [ ] schedule `drip apply` / `autopilot` (cron / systemd) with the audit trail wired
- [ ] monitoring: Langfuse via OpenTelemetry (traces, token cost, audit)
- [ ] only then consider `autonomous` for proven campaigns
```
