<div align="center">

# Drip

### One agent replaces a 5-person UA team.

**The open-source autonomous user-acquisition agent for anime / gacha mobile games.**
Plans creatives. Simulates the audience. Runs the campaigns. Tells you what to do next.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/YunyueLi/Drip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/YunyueLi/Drip/actions)
[![Stars](https://img.shields.io/github/stars/YunyueLi/Drip?style=flat-square&color=fbbf24)](https://github.com/YunyueLi/Drip/stargazers)
[![X follow](https://img.shields.io/twitter/follow/drip_agent?style=flat-square&label=%40drip_agent&color=000)](https://x.com/drip_agent)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg?style=flat-square)](#status)

[**Quickstart**](#-quickstart) · [**How it thinks**](#-how-it-thinks) · [**Roadmap**](#%EF%B8%8F-roadmap) · [**Contributing**](CONTRIBUTING.md) · [**Discord**](https://discord.gg/drip-agent)

**English** · [简体中文](README.zh-CN.md)

</div>

---

> Anime / gacha titles burn **$5B+ a year** on user acquisition. They still hand-craft every creative, eyeball every spreadsheet, and run every A/B by hand.
>
> Drip is the agent stack that does it for you — end to end, in shadow mode by default, with a real human safety net.

```text
$ drip launch --game ./astral-drift.yaml --budget 500 --regions jp,sg,tw

▸ creative
  brainstormed 6 ad concepts via claude-agent-sdk
  [1/6] cinematic intro of Hina with cherry blossom particles ………… 3.2s
  [2/6] gameplay loop hero shot — Riku performing a signature skill  4.1s
  …
  produced 6 candidate creatives (gpt-image-2 + Seedance 2.0)

▸ audience
  simulated 5,000 synthetic gachas via OASIS
    ctr≈1.62%  install≈0.11%  cinematic intro of Hina…
    ctr≈1.54%  install≈0.10%  gameplay loop — Riku…
    ctr≈1.41%  install≈0.09%  emotional reveal of Vesper…

▸ bidding
  planned 18 ad groups across 3 regions × 2 platforms
  [shadow mode] not pushing to platforms

▸ reporter
  $432 spend  →  5,234 installs  →  CPI $0.083  →  D7 ROAS 36%
  recommendation: pause Meta SG, scale TikTok JP +50%
```

---

## ✨ What Drip does

Six steps, one command, one agent.

| # | Step | What it does | Powered by |
|---|---|---|---|
| 1 | **Brainstorm** | Six anime-tuned ad concepts per run | `claude-agent-sdk` |
| 2 | **Render keyframes** | Hero stills, multilingual CTA, 1024–2048px | OpenAI `gpt-image-2` |
| 3 | **Render video** | 6-second vertical spots for Reels & TikTok | ByteDance `Seedance 2.0` |
| 4 | **Predict reaction** | 5,000 synthetic gachas react *before* you spend | CAMEL-AI `OASIS` |
| 5 | **Plan & bid** | Auto-allocates across regions × platforms | `MCP` · Meta + TikTok |
| 6 | **Report** | Narrative summary, ranked decisions, next steps | Claude `Haiku 4.5` |

> **Note** — every step degrades gracefully. With no API keys at all, `drip demo` still walks the full pipeline using deterministic stubs. You can read the code on a flight.

---

## 🎯 Why Drip exists

Three things shifted in **2025–2026**:

**1. Platform AI ate the bidding layer.**
Meta GEM, AppLovin AXON 2.0, TikTok Smart+, Unity Vector — they have collectively automated the "tweak the bid" job out of existence. AppLovin alone runs $1.4B/quarter in software revenue on AXON. The new battleground is the **creative pipeline and cross-platform orchestration**.

**2. One vertical is still wide open.**
Sett raised a $30M Series B doing this for general mobile gaming — *closed source*. The anime / gacha niche burns $5B+/year on UA and still hand-crafts every creative. **There is no credible open-source equivalent.**

**3. The agent stack is finally good enough.**
`claude-sonnet-4-6` + Agent SDK ship today with enough determinism for real money decisions. `gpt-image-2` and `Seedance 2.0` produce in-language CTAs and cinematic 6-second spots at **<$0.20 per clip**.

Drip is the missing piece.

---

## ⚡️ Quickstart

**Requirements:** Python **3.11** (locked by OASIS' `<3.12` bound), [`uv`](https://docs.astral.sh/uv/) recommended.

```bash
# 1. Clone & enter
git clone https://github.com/YunyueLi/Drip.git
cd Drip

# 2. Install
uv venv -p 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. Configure
cp .env.example .env  # set at minimum ANTHROPIC_API_KEY

# 4. Dry-run (zero API calls, zero provider SDKs)
drip demo

# 5. Live run — install provider SDKs first, then go (still shadow mode by default)
uv pip install -e ".[all]"   # openai (gpt-image-2), seedance, oasis…
drip launch \
  --game ./examples/demo_game.yaml \
  --budget 500 \
  --regions jp,sg,tw
```

> The core install is deliberately tiny. `drip demo` runs on it with no provider SDKs at all — provider packages (`.[all]`) are only needed for a live run.

Need more? See [`docs/quickstart.md`](docs/quickstart.md).

---

## 🧠 How it thinks

Drip is a **supervisor + workers** agent system built on Anthropic's Claude Agent SDK. The supervisor owns the run lifecycle, budget, and HITL gating. Each worker is a domain expert that reports structured results back. The supervisor decides what comes next.

```
                    ┌──────────────────────────────┐
                    │   Drip Supervisor            │   claude-agent-sdk
                    │   (Sonnet 4.6)               │   supervisor pattern
                    └──────────────────────────────┘
                                │
       ┌────────────┬───────────┼───────────┬─────────────┐
       ▼            ▼           ▼           ▼             ▼
  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐
  │Creative │ │ Audience │ │ Bidding │ │ Reporter│ │  Eval    │
  │Sonnet + │ │ OASIS    │ │ Sonnet  │ │  Haiku  │ │ Trajectory│
  │Seedance │ │ sim      │ │         │ │         │ │          │
  └─────────┘ └──────────┘ └─────────┘ └─────────┘ └──────────┘
       │            │           │           │
       └────────────┴───────────┴───────────┘
                         │
                         ▼
            ┌────────────────────────────────┐
            │   MCP Tool Layer               │
            │   meta-ads · tiktok-ads        │
            │   appsflyer · gpt-image · …    │
            └────────────────────────────────┘
```

### Design tenets

- **Shadow by default.** Real platform writes require `DRIP_MODE != shadow` *and* a configured token. Even forgetting the safety check still won't burn money.
- **Budget cap is a hard wall.** `DRIP_BUDGET_CAP` is enforced before the supervisor even starts.
- **Adapters degrade gracefully.** No API keys? Adapters return deterministic stubs so `drip demo` works on a plane.
- **Workers are pure functions of context.** They take a `RunContext`, return a `WorkerResult`. No global state. Easy to test, easy to replace.
- **Provider-swappable.** Switch from `gpt-image-2` to Midjourney, or from Seedance to Kling, by editing one file.

Read the full design notes in [`docs/architecture.md`](docs/architecture.md).

---

## 📦 What's in `v0.0.1`

```
drip/
├── src/drip/
│   ├── cli.py               drip launch / demo / eval
│   ├── orchestrator.py      supervisor, RunContext, RunMode
│   ├── workers/
│   │   ├── creative.py      → gpt-image-2 + Seedance 2.0
│   │   ├── audience.py      → OASIS social simulation
│   │   ├── bidding.py       → cross-platform allocator
│   │   └── reporter.py      → narrative summary
│   ├── adapters/            ← provider-specific, swappable
│   └── eval/bench.py        Drip-Bench v0 (case curation in progress)
├── examples/demo_game.yaml  fictional sample game spec
├── web/index.html           drip.dev landing
└── docs/                    architecture, quickstart
```

---

## 🛠️ Configuration

All settings via `.env` (see [`.env.example`](.env.example) for the full list).

| Variable | Required | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Claude Agent SDK + every worker brain |
| `OPENAI_API_KEY` | for live | `gpt-image-2` keyframes |
| `ARK_API_KEY` | for live | ByteDance Seedance 2.0 (Volc Engine ARK) |
| `META_ACCESS_TOKEN` | for live | Meta Marketing API |
| `TIKTOK_ACCESS_TOKEN` | for live | TikTok Marketing API |
| `APPSFLYER_API_TOKEN` | optional | Attribution / MMP |
| `LANGFUSE_*` | optional | Trace + cost observability |
| `DRIP_MODE` | — | `shadow` (default) · `copilot` · `autonomous` |
| `DRIP_BUDGET_CAP` | — | Hard ceiling in USD per run |

---

## 🗺️ Roadmap

### `v0.0.1` — Day 0 *(you are here)*
- [x] Project scaffold, CLI, orchestrator skeleton
- [x] Four workers (Creative, Audience, Bidding, Reporter)
- [x] Adapters: gpt-image-2, Seedance 2.0, OASIS, MCP-ready ads stub
- [x] Three-mode runtime (shadow / copilot / autonomous)
- [x] Budget cap enforcement
- [x] Apache-2.0 + CI + issue/PR templates

### `v0.1` — Week 2–4
- [ ] Claude Agent SDK subagents replace the deterministic concept brainstorm
- [ ] OASIS audience profiles tuned for anime gachas (JP / TW / SG / KR)
- [ ] First end-to-end run on a real Meta test account
- [ ] First 20 Drip-Bench cases
- [ ] Langfuse trace + cost dashboard

### `v0.2` — Month 2
- [ ] Real Supervisor agent (replace fixed pipeline with dynamic routing)
- [ ] TikTok creative variants (vertical 9:16, 6s / 15s)
- [ ] LiveOps tie-in worker (banner rotation → creative refresh)
- [ ] KOL Scout worker (HoYoCreators / Twitch / YouTube)
- [ ] Public Discord + first community contributors

### `v1.0` — Quarter 2
- [ ] Multi-market run (JP + SEA + NA + EU + KR)
- [ ] Cross-promotion across multiple games in the same publisher
- [ ] PyPI release, full Drip-Bench (50+ cases)
- [ ] Public AdLoop-Bench leaderboard for the broader community

Follow the build log: [@drip_agent](https://x.com/drip_agent).

---

## 🤝 Contributing

Drip is in early alpha. The most useful contributions today are:

1. **Try it** on a real anime / gacha game and file what breaks.
2. **Curate Drip-Bench cases** — we need 20 hand-picked UA decision cases. See [#3](https://github.com/YunyueLi/Drip/issues/3).
3. **New ad-platform adapters** — Apple Search Ads, Pangle, 巨量引擎. Each is a tight ~150-line PR.
4. **Worker improvements**, especially `creative.py` (concept brainstorm) and `bidding.py` (allocation strategy).

Setup is in [CONTRIBUTING.md](CONTRIBUTING.md). PRs should run `ruff check .`, `mypy src`, `pytest`.

---

## 🙏 Acknowledgements

Drip stands on the shoulders of:

- [**Anthropic Claude Agent SDK**](https://github.com/anthropics/claude-agent-sdk-python) — supervisor runtime
- [**CAMEL-AI OASIS**](https://github.com/camel-ai/oasis) — million-scale social simulation
- [**pipeboard-co/meta-ads-mcp**](https://github.com/pipeboard-co/meta-ads-mcp) — Meta Ads MCP
- [**amekala/ads-mcp**](https://github.com/amekala/ads-mcp) — multi-platform ads MCP
- [**Volc Engine ARK**](https://www.volcengine.com/product/ark) — Seedance 2.0
- [**OpenAI Images API**](https://openai.com/api/) — `gpt-image-2`
- [**Langfuse**](https://langfuse.com) — open-source LLM observability

And the prior art that proved this niche was worth building for: [**Sett**](https://www.sett.ai/), [**Kohort**](https://www.kohort.ai/), [**AppsFlyer Agent Hub**](https://www.appsflyer.com/products/agentic-ai/).

---

## 📜 License

[Apache 2.0](LICENSE) — use it, fork it, ship it. Just keep the notice.

---

<div align="center">

**Drip** · Built in the open by [@YunyueLi](https://github.com/YunyueLi)

If Drip saves you a week, give it a ⭐ — it's the only metric we have.

</div>
