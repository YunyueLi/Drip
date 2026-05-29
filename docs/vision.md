# Drip Vision

The north star: **AI-ify the entire UA line — media buying, growth, and
analytics — as a team of collaborating agents.** Not a toy, not another black
box. The honest, open, end-to-end reference.

This document is the compass. Any "should we build X?" is answered by: *which
layer is it in, and does it clear the three walls?*

---

## The end state

Not a zero-person growth team. The realistic terminal state is:

> **One person who owns the budget and the brand, commanding a team of agents
> that run execution and analysis.**

The human retreats to goal-setting, accountability sign-off, and crisis/ethics
— the three things agents can't touch. Everything else trends toward
lights-out. Gartner: marketing-work automation 16% (2026) → 36% (2028), i.e.
~2/3 still human at 2028. The centaur (human + AI), not full replacement.

---

## Three layers of AI-ification

| Layer | Includes | Ceiling | Who owns it |
| --- | --- | --- | --- |
| **Execution** | bidding, scheduling, budget micro-adjust, creative mass-production, A/B, reporting | near lights-out | platforms + plug-in slots |
| **Decision** | scale/pause, cross-platform allocation, attribution reconciliation, over-invest check | agent proposes, human signs | **Drip builds this** |
| **Strategy / accountability** | goals, brand voice, ethics, crisis, budget accountability | stays human | the person |

Platforms (Meta GEM, AppLovin AXON, TikTok Smart+) are eating the execution
layer — Zuckerberg has publicly committed to fully automated ad creation by
end-2026. **Do not fight platforms on execution; you'll be carried for free
and lose.**

---

## Three walls (why it's never 100%)

1. **Accountability.** No exec explains a brand incident with "the algorithm
   did it." The EU AI Act makes the marketer the liable "deployer" (fines up
   to 7% of global revenue). Someone firable must sign.
2. **Black box + sameness.** Full auto on dirty signals self-reinforces (~20%
   of programmatic traffic is invalid/non-human in 2026); generative "AI slop"
   converges on look-alike creative.
3. **Attribution truth (UA's Achilles' heel).** Post-ATT, multi-touch coverage
   fell to 30–60%. Platforms are judge and player — reports suggest Meta
   inflates ROAS 17–19%. The signal the agents optimise on is itself polluted;
   automate deeper and you amplify the error faster.

Each wall is, inverted, **a structural opening for an open, auditable, neutral
tool.**

---

## Where Drip stands

> **Drip is the open, trustworthy, neutral control room that lets the
> accountable person hand over the wheel.**

Not "another fully-automated UA" (platforms do that, free and stronger), but:

- platforms optimise inside their own walled garden → Drip is the
  **cross-platform** neutral referee (it has no ad inventory to sell)
- platforms/closed SaaS are black boxes → **every decision is explainable and
  reversible** (signal vector + rule chain + replay)
- full auto needs accountability → Drip is **that person's trustworthy
  dashboard** — agents run, the human always understands, can veto, can roll back

The deeper platforms push full-auto-but-opaque, the more the accountable person
needs a neutral, transparent, cross-platform control room. That's Drip.

---

## Build vs. plug-in (the slot philosophy)

**Build the orchestration, the judgement, and the evaluation. Leave every
"can't-win / no-data" hard part as a standard slot.**

| | Build | Plug-in slot |
| --- | --- | --- |
| orchestration / supervisor | ✅ | |
| decision engine (8 signals) | ✅ | |
| cross-platform allocation | ✅ | |
| open benchmark | ✅ | |
| LLM | | 🔌 12 providers + OpenRouter fallback |
| creative generation | | 🔌 AdCreative/Creatify/ComfyUI |
| bid execution | | 🔌 platform auto / Madgicx / shadow |
| LTV / value model | | 🔌 Kohort/Voyantis / heuristic |
| attribution truth | | 🔌 AppsFlyer/Adjust / haircut heuristic |

Drip is the UA **operating system / control room**, not a player that tries to
self-build everything. This is the natural shape of open + neutral.

---

## The agent matrix

```
        ── investing side ──                ── analytics side ──
   Strategist  next creative      build    Collector   pull data      build
   Creative    external gen       plug     Attribution truth/over-invest build
   Audience    pre-flight sim     build    Analyst     diagnose/report  build
   Allocator   cross-platform $   build    Feedback    learnings回流     build
   Decision    scale/pause        build ✅
        │                                        │
   [bid slot] 🔌 platform/3rd-party        [value slot] 🔌 Kohort/own
        └──────────── Feedback loop: spend → next creative + budget ──────────┘
```

**Deliberately NOT built:** core auction bidding (platform walled gardens win),
LTV/MMM model training (data moat). Both are slots, not gaps.

---

## Tech choices (from the research, not invented)

- **Orchestration:** LangGraph (native checkpointing + `interrupt()` approval +
  retries); Temporal as the long-running outer layer at scale.
- **Ad APIs:** official SDKs as the floor (`facebook-business`,
  `tiktok-business-api-sdk`), MCP as an optional upper入口. System User token,
  async insights, parse `actions[]`, honour the 2026-01 attribution-window change.
- **Analytics:** reuse PyMC-Marketing (MMM+LTV), GeoLift (incrementality),
  WrenAI/Vanna (NL query + semantic layer), Prophet+ADTK (anomaly). SKAN value
  mapping and MMP ground-truth stay as interfaces.
- **Creative:** ComfyUI + Wan for generation; the performance→creative feedback
  loop is self-built (open source's weak spot).

---

## Roadmap (bench-driven)

```
done      decision engine · LLM layer · bid/value slots · Drip-Bench
done      7 agents + end-to-end pipeline (offline samples)
next      drip run CLI · docs · tests/CI
then      LangGraph supervisor (checkpoint + approval + retry)
then      live Meta/TikTok via SDK (needs credentials)
v1.0      drip.cloud (same code, hosted) · 50-case bench · first enterprise
```

Every release publishes its own Drip-Bench score. We don't claim "we're
accurate" — we show a reproducible number.
