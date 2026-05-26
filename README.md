# Drip

> **One agent replaces a 5-person UA team.**
> Open-source autonomous user-acquisition agent for anime / gacha mobile games.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](#status)

---

**Drip** is an open-source agent stack that runs your mobile game's overseas UA pipeline end-to-end — from creative generation, audience simulation, multi-platform bidding, to ROAS reporting and next-step decisions. Built for **anime / gacha titles** where character drip-feed is the marketing core.

## Why now

- Platform AI 已接管出价（Meta GEM、AppLovin AXON、TikTok Smart+）— 战场转到**跨平台编排 + 创意 pipeline**
- Sett（Series B $30M）闭源 — **开源版至今空白**
- 二次元手游年消耗 > $5B — 但 creative pipeline 完全 manual

## Quick start

```bash
# install
pip install drip-agent  # 或 uv pip install drip-agent

# config
cp .env.example .env  # 填 ANTHROPIC_API_KEY / OPENAI_API_KEY / VOLC_AK_SK / META_TOKEN / TIKTOK_TOKEN

# 跑一次
drip launch --game ./examples/demo_game.yaml --budget 500 --regions jp,sg,tw
```

输出：

```
[creative]  generated 12 ad variants in 3m22s
[audience]  simulated 5,000 anime gachas with OASIS — predicted CTR distribution
[bidding]   launched 6 ad groups across Meta JP / TikTok SG / TikTok TW
            waiting 48h for stats…
[reporter]  $432 spend  →  5,234 installs  →  CPI $0.083  →  D7 ROAS 36%
            recommendation: pause Meta SG, scale TikTok JP +50%
```

## Architecture

```
                    ┌──────────────────────────┐
                    │   Drip Orchestrator      │  Claude Agent SDK
                    │   (Sonnet 4.6)           │  supervisor pattern
                    └──────────────────────────┘
                                 │
       ┌────────────┬────────────┼────────────┬─────────────┐
       ▼            ▼            ▼            ▼             ▼
  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │Creative │ │ Audience │ │ Bidding  │ │ Reporter │ │  Eval    │
  │Sonnet + │ │ OASIS    │ │ Sonnet   │ │ Haiku    │ │ Trajectory│
  │Seedance │ │ sim      │ │          │ │          │ │          │
  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
       │            │            │            │
       └────────────┴────────────┴────────────┘
                          │
                          ▼
            ┌────────────────────────────────┐
            │   MCP Tool Layer               │
            │   meta-ads · tiktok-ads        │
            │   appsflyer · gpt-image · …    │
            └────────────────────────────────┘
```

详见 [docs/architecture.md](docs/architecture.md).

## What it does (today, MVP scope)

- [x] Project scaffold + CLI + orchestrator skeleton
- [ ] Creative Worker — GPT-Image-2.0 关键帧 + Seedance 2.0 视频
- [ ] Audience Simulator — OASIS multi-agent 群体反应预测
- [ ] Bidding Worker — Meta / TikTok via MCP
- [ ] Reporter — Slack / Lark narrative report
- [ ] Drip-Bench v0 — 20 个 UA 决策评测 case

## Status

> **Day 0 — public scaffold up. Week 1 will ship the first end-to-end demo against a real Meta test account.**

Follow the build log: [@drip_agent](https://x.com/drip_agent) · [drip.dev](https://drip.dev)

## Contributing

Drip is early — issues, design discussions, and PRs all welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

## Acknowledgements

- [Anthropic Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) — orchestrator runtime
- [CAMEL-AI OASIS](https://github.com/camel-ai/oasis) — multi-agent social simulation
- [pipeboard-co/meta-ads-mcp](https://github.com/pipeboard-co/meta-ads-mcp) — Meta Ads MCP
- [amekala/ads-mcp](https://github.com/amekala/ads-mcp) — multi-platform ads MCP
