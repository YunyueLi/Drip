# Changelog

All notable changes to **Drip** will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v0.1
- Public Drip-Bench leaderboard with baseline scores for `dummy`, `claude-sonnet-4-6`, `gpt-4o`, and `drip`.
- First real Meta Marketing API call from `BiddingWorker` (`mode=copilot`).
- First Knowledge Pack — `drip-pack-anime` — extra signals + prompt overrides for anime / gacha titles.
- Drip-Bench grows to 20 cases.

## [0.0.2] — 2026-05-28

### Added
- **Drip-Bench v0** — open evaluation suite for UA agent decisions.
  - 10 hand-curated cases across `scale_decision`, `pause_decision`, `budget_reallocation`, `creative_fatigue`, `anomaly_diagnosis`, `cohort_quality`, `audience_expansion`, `bid_strategy_switch`, `market_entry`, `crisis_response`.
  - Three-part rubric: `action_match` (0–40) + `direction_match` (0–20) + `reasoning_quality` (0–40, LLM-as-judge with heuristic fallback).
  - Reproducible run bundles in `benchmarks/runs/<timestamp>/`.
- New CLI command group: `drip bench {list, show, run}`.
- Agent adapters in `drip.eval.agents`: `DummyAgent`, `ClaudeAgent`, `DripAgent` (stub forwards to Claude until `BiddingWorker` exposes a `decide(case_json)` entry point — tracked in #4).
- LLM-as-judge in `drip.eval.judges` using the Anthropic Messages API directly via `httpx` (no SDK dep beyond core).
- Heuristic judge fallback (keyword overlap) when `ANTHROPIC_API_KEY` is unset, so local development never blocks on credentials.
- `benchmarks/README.md` and `benchmarks/SCHEMA.md` documenting the bench design and case YAML contract.

### Changed
- **Repositioned** the project from "anime / gacha vertical" to a general-purpose open reference implementation. The anime / gacha angle survives as a first-party Knowledge Pack (`drip-pack-anime`, landing in v0.1).
- README rewritten — new sections on Drip-Bench, the open-source vs closed-source comparison, and a bench-driven roadmap. English and Simplified Chinese versions in sync.
- `drip eval` is now a deprecated alias for `drip bench run`. It still works; new code should use `drip bench`.

### Deprecated
- `drip eval` CLI verb (hidden, emits a deprecation notice; use `drip bench run` instead).

## [0.0.1] — 2026-05-26

### Added
- Project scaffold (`src/drip/{cli,orchestrator,workers,adapters,eval}/`).
- Four workers: Creative, Audience, Bidding, Reporter.
- Adapters: `gpt-image-2`, Seedance 2.0 (Volc Engine ARK), OASIS, MCP-ready ads stub.
- CLI: `drip launch`, `drip demo`, `drip eval`.
- Three-mode runtime: `shadow` (default) / `copilot` / `autonomous`.
- Budget cap enforcement (`DRIP_BUDGET_CAP`).
- Landing page (`web/index.html`).
- Apache-2.0 license.
