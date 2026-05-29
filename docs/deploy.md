# Deploying Drip to production

Drip runs fully offline out of the box (sample data, template reports, dry
creative, shadow bidding). Going live is three steps — no code change, just
configuration. This is the path from "runs on my laptop" to "spends real
money safely".

## The three steps from offline → live

1. **Credentials** — connect the ad platforms and an LLM.
2. **Extras** — install the provider SDKs (lazy-imported; only needed live).
3. **Orchestration** — switch from the lightweight Pipeline to the LangGraph
   graph (checkpointing + approval + retries) for a long-running daemon.

Each is independent — you can connect Meta and stay in shadow mode for weeks
before flipping a single campaign to live.

## 1. Install

```bash
uv venv -p 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"          # core + tests, runs offline
uv pip install -e ".[all]"          # + provider SDKs for live runs
uv pip install langgraph            # for the production graph (step 3)
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

The lightweight `drip run` (Pipeline) is fine for one-shot and cron. For a
long-running daemon that survives crashes and pauses for human approval before
spending, use the LangGraph graph:

```python
from drip.graph import build_graph
from langgraph.checkpoint.postgres import PostgresSaver  # or SqliteSaver

graph = build_graph(checkpointer=PostgresSaver(...), approve_before_spend=True)
# interrupt_before=["allocate"] pauses before budget moves; resume after sign-off.
```

- **checkpointing** → resume mid-run after a crash, don't restart the cycle.
- **interrupt-before-spend** → the accountability gate; a human approves the
  budget move, then you resume the graph from that checkpoint.
- wrap in **Temporal** if you need scheduled runs + crash-replay at scale.

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
- [ ] LangGraph graph with a Postgres checkpointer for the daemon
- [ ] monitoring: Langfuse via OpenTelemetry (traces, token cost, audit)
- [ ] only then consider `autonomous` for proven campaigns
```
