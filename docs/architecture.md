# Drip Architecture

Drip is a **supervisor + agents + swappable slots** system. The decision core
is deterministic (rules over an 8-signal vector); the LLM only narrates. Every
hard part we can't win or lack data for is a slot, not a self-build. See
[vision.md](./vision.md) for *why*; this doc is *how*.

## Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  Entry — CLI                                                       │
│  drip  run · doctor · bench · llm · launch · demo                  │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  Orchestration                                                     │
│  Pipeline   — lightweight, framework-agnostic, runs offline        │
│  Graph      — LangGraph: checkpointing + interrupt() approval +    │
│               retries (production daemon). Nodes map 1:1 to agents.│
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  Agents                                                            │
│   investing            analytics                                   │
│   Strategist  drip.strategist     Collector    drip.collectors     │
│   Creative    drip.creative       Analyst      drip.analyst        │
│   Allocator   drip.allocator      Attribution  drip.attribution    │
│   Audience    drip.workers        Feedback     drip.feedback       │
└──────────────────────────────────────────────────────────────────┘
                               │ every "should I scale/pause?" goes through ↓
┌──────────────────────────────────────────────────────────────────┐
│  Decision Engine (deterministic core)   drip.engine                │
│  signals (8) → rules → card    + LLM narration (why)               │
└──────────────────────────────────────────────────────────────────┘
                               │ speaks one data contract ↓
┌──────────────────────────────────────────────────────────────────┐
│  Data contract   drip.data.AdMetrics  (normalised across platforms)│
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  Slots — all swappable                                             │
│  LLM (drip.llm · 12 providers)   bidding (adapters.bidding)        │
│  value/LTV (adapters.prediction) image/video/sim (adapters.*)      │
│  ads write (adapters.ads)                                          │
└──────────────────────────────────────────────────────────────────┘
                               │
        External: Meta/TikTok API · Claude/GPT/Qwen/… · OASIS · Kohort

   ═══ cross-cutting: Drip-Bench (drip.eval) — scores any agent ═══
```

## The one-stop loop

`drip run` (or the LangGraph graph) walks the full cycle:

```
Collector  pull insights → AdMetrics (samples offline, Meta/TikTok SDK live)
   → Analyst     run each through the engine; scan anomalies; write a report
   → Strategist  rank winners/losers; propose the next creative test + brief
   → Creative    produce N variants for the winning direction (external gen)
   → Allocator   reallocate a fixed budget across platforms (pause→0, fund winners)
   → Feedback    distil learnings (platform weights, CTR bar) → next cycle
```

Each agent is a pure-ish function of `AdMetrics`; `Pipeline` chains them, the
LangGraph `Graph` adds checkpointing + a human-approval interrupt before the
Allocator spends. Reference flow and production graph share the same agent
boundaries, so they never drift.

## Decision engine

The heart, and the only fully-built core. `drip.engine`:

1. `signals.py` — evaluate 8 signals (CPP, ROAS, CVR, daily spend, purchases,
   CTR, frequency, budget headroom) against thresholds → GREEN/YELLOW/RED.
2. `rules.py` — a decision (SCALE/REDUCE/HOLD/PAUSE/REFRESH) + confidence +
   auto-generated guardrails + an auditable rule chain. **Rules decide, not the LLM.**
3. `cards.py` — render a GrowthGPT-style card (signals + why + guardrails).
4. `engine.py` — wire it together; the LLM (any `drip.llm` model) writes the
   human "why", template fallback when no key.

Thin sample → conservative scale + capped confidence (the lesson encoded from
Drip-Bench case 001). Decisions are deterministic and replayable.

## Slots — swap anything

| Slot | Module | Plug in | Fallback |
|---|---|---|---|
| LLM | `drip.llm` | 12 providers + OpenRouter | — |
| bidding | `adapters.bidding` | platform auto / Madgicx | shadow |
| value/LTV | `adapters.prediction` | Kohort/Voyantis | null / heuristic |
| creative gen | `adapters.image/video` | gpt-image / Seedance / ComfyUI | dry |
| ads write | `adapters.ads` | Meta/TikTok MCP | shadow |
| attribution truth | `attribution` | AppsFlyer/Adjust | documented haircut |

## Run modes (money safety)

`DRIP_MODE`: `shadow` (plan only, default) · `copilot` (approve each write) ·
`autonomous` (write up to `DRIP_BUDGET_CAP`, checked before start). See
[deploy.md](./deploy.md) for the go-live ladder.

## Tech choices (from research, not invented)

- **Orchestration**: LangGraph (checkpoint + `interrupt()` + retries); Temporal at scale.
- **Ad APIs**: official SDKs as the floor (`facebook-business`, `tiktok-business-api-sdk`); MCP optional. System User token, async insights, parse `actions[]`, 2026-01 attribution window.
- **Analytics**: reuse PyMC-Marketing (MMM/LTV), GeoLift (incrementality), WrenAI/Vanna (NL query), Prophet+ADTK (anomaly). SKAN/MMP truth as interfaces.
- **Creative**: ComfyUI + Wan; performance→creative feedback self-built.

## What Drip deliberately doesn't build

- **Core auction bidding** — platform walled gardens (GEM/AXON/Smart+) win; it's a slot.
- **LTV/MMM model training** — a data moat (Kohort $6B); it's a slot.
- **Closed-source deps in the core** — every slot has a deterministic fallback, so `drip run` / `drip bench run --agent dummy` work with zero keys.

The discipline: anything we ship must be visible in a Drip-Bench bundle, and
the decision core must stay auditable end-to-end.
