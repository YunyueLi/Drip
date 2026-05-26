# Drip Architecture

## Layers

```
┌────────────────────────────────────────────────────────────┐
│  L2  Orchestrator (Claude Agent SDK · supervisor pattern)  │
│      drip.orchestrator.DripOrchestrator                    │
│      Owns budget, mode, HITL gating, artifact passing.     │
└────────────────────────────────────────────────────────────┘
                              │ delegate
                              ▼
┌────────────────────────────────────────────────────────────┐
│  L1  Workers — domain experts (one slice of the pipeline)  │
│      Creative · Audience · Bidding · Reporter              │
│      drip.workers.*                                        │
└────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────┐
│  L0  Adapters — narrow domain interfaces over providers    │
│      Image (gpt-image-2)                                   │
│      Video (Seedance 2.0 via Volc Engine ARK)              │
│      Simulation (OASIS · multi-agent social sim)           │
│      Ads (Meta + TikTok via MCP — v0.2)                    │
└────────────────────────────────────────────────────────────┘
```

## Run lifecycle

1. **CLI** parses flags, loads the game spec YAML, applies budget cap.
2. **Orchestrator** creates a `RunContext` (game, budget, regions, mode) and
   walks the workers in deterministic order — v0 is a fixed pipeline; v0.2
   replaces it with an Agent-SDK supervisor that re-routes on intermediate
   signals.
3. **Creative** brainstorms N concepts, then asks the image adapter for a
   keyframe and the video adapter for a 5-6s spot per concept. Artifacts land
   under `artifacts/images/` and `artifacts/videos/`.
4. **Audience** spawns an OASIS social graph of synthetic gachas, exposes
   each creative, and aggregates likes/comments into predicted CTR. Ranks
   creatives and picks top-3.
5. **Bidding** plans the spend across (creatives × regions × platforms).
   In shadow mode it stops here; in copilot mode it asks for approval; in
   autonomous mode it pushes via MCP.
6. **Reporter** narrates the run, recommends next steps, and emits the
   transcript to stdout (Slack / Lark integration arrives in v0.2).

## Why these provider choices

| Layer       | Choice                | Why                                                       |
|-------------|-----------------------|-----------------------------------------------------------|
| Orchestrator| Claude Agent SDK      | Anthropic-native, built-in subagents, HITL primitives.    |
| Supervisor  | Sonnet 4.6            | Best routing-quality / cost trade for v0.                 |
| Image       | gpt-image-2           | Strongest in-image text + multilingual; native 2K output. |
| Video       | Seedance 2.0          | $0.14/s — half the price of Kling, third of Sora; cinematic motion. |
| Simulation  | OASIS                 | Apache 2.0, up to 1M agents, native Reddit/Twitter sims.  |
| Ads         | MCP (Meta + TikTok)   | 2026 protocol standard; we don't reinvent the API client. |
| Observability| Langfuse self-hosted | MIT, US/EU/JP compliant, OTel-native.                     |

## What Drip v0 deliberately doesn't do

- No real ad-platform writes (mode defaults to `shadow`).
- No fine-tuning. Everything is prompt + tool use.
- No multi-tenant. One process == one run.
- No web UI. CLI only — landing page is marketing surface.

These all arrive in v0.2 once the demo pipeline is proven.
