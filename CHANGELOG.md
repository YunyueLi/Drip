# Changelog

All notable changes to **Drip** will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- **Dead parallel orchestration stack** (~1k LOC, never reachable from the shipped `run`/`apply`/`watch`/`autopilot`/`doctor`/`bench` path): `orchestrator.py`, the `workers/` pool (audience/bidding/creative/reporter), `graph.py` (the unwired LangGraph scaffold), `adapters/bidding.py`, `adapters/simulation.py` (OASIS), the `AdsAdapter` launch stub, `Allocator.execute()`, and the `drip launch` / `drip demo` commands. Dropped the now-unused `camel-oasis` dependency (`sim` extra).
- Dead `config` credential getters and `config.get_mode()`; `RunMode` now lives in `drip.config`. Removed the unused, mislabelled `RunResult.by_category()`.

### Changed
- **Creative generation is actually wired now.** `Creative.produce` drives the real `gpt-image` / `Seedance` adapters when `OPENAI_API_KEY` / `ARK_API_KEY` is set; with no key (or an unshipped generator like ComfyUI) it falls back to deterministic `dry` placeholders, so the loop still runs offline.
- **Docs/README aligned with the code.** Dropped claims about the LangGraph daemon, ComfyUI/Arcads/OASIS integrations, and "every release publishes a bench score"; clarified the `drip` bench agent is an LLM under the 8-signal methodology prompt (not the rule engine directly); flagged that 快手 write is unconfirmed and China-platform reads are sample-only.
- `requires-python` relaxed to `>=3.11,<3.13` (the `<3.12` OASIS lock is gone).
- Collapsed the per-allocation write loop duplicated across `drip apply` / `autopilot` into one `_apply_allocations` helper.

### Fixed
- **Window-vs-daily spend.** Live collectors now normalise cumulative window insights to per-day rates, so a multi-day pull is no longer read as one giant day (which inflated `daily_spend` and the budget-headroom signal).
- **Money-safety caps fail loud.** A malformed `DRIP_BUDGET_CAP` / `DRIP_MAX_CHANGE_PCT` now raises instead of silently disabling the cap (fail-closed, not fail-open).
- **Uniform audit schema.** The denied-write path now records the same fields (`field`/`old_value`/`new_value`) as the applied path, so every audit line has one shape.
- **China "fake read → real write" guard.** The sample-only China collectors warn loudly when a token is set, so live writes aren't driven off placeholder data.
- `drip doctor --metrics` reads YAML as UTF-8 (was locale-dependent on Windows).
- CI ran the removed `drip demo`; it now runs `drip run` for the offline smoke check.

### Tests
- Added unit suites for previously-untested modules: `drip.eval` (scorer math, schema validators, an offline `run_bench` smoke), `attribution.py` (haircut / MMP / over-investment), `drip.llm` (resolution, HTTP error mapping, template fallback), and `config` (cap fail-loud, `RunMode`). Fixed two vacuously-conditional assertions in `test_allocator.py`. Suite: **198 tests**.

### Planned for v0.1
- Public Drip-Bench leaderboard with baseline scores for `dummy`, `claude-sonnet-4-6`, `gpt-4o`, and `drip`.
- **First _live_ Meta write verified on a real ad account** (the `drip apply` write path shipped in 0.0.4 — this is the live-credentials confirmation).
- First Knowledge Pack — `drip-pack-anime` — extra signals + prompt overrides for anime / gacha titles.
- Drip-Bench grows to 20 cases.

## [0.0.7] — 2026-06-02

### Added
- **Autonomous orchestration — `drip autopilot`.** A signal-driven supervisor replaces the fixed pipeline order: it classifies the situation (**bleeding / scaling / fatigued / steady**) and routes accordingly (stop-loss first, then scale, refresh, allocate), runs the loop end-to-end, and — in autonomous mode — applies within the money-safety caps behind a **circuit breaker** that halts *before any write* on a data anomaly (most of the account wanting to pause) and *mid-run* on write failures.
  - `drip.supervisor` — `classify` / `route` (situation → an ordered, reasoned plan) + `CircuitBreaker` (pre-apply anomaly + post-write failure halts). Deterministic + auditable — rules route, not an LLM, so every routing step carries its reason. 6 tests.

## [0.0.6] — 2026-06-02

### Added
- **China-platform writers — 腾讯广告 / 巨量引擎 / 快手.** `drip.adapters.writers` adds REST-API write adapters (over `httpx`, no SDK) on the same `WriteResult` contract + token gate + shadow fallback + money-safety guards as the Meta path. `build_writer(platform)` routes each campaign to its platform's writer (accepts aliases like 巨量 / 腾讯 / 快手; unknown platform → a shadow writer).
  - **Tencent**: `campaigns/update` (daily_budget 分 / configured_status). **Ocean Engine**: `promotion/budget/update` + `promotion/status/update`. **Kuaishou**: contract mapped; endpoint pending confirmation, so shadow until then.
  - `drip apply` and `drip watch` now dispatch **per platform** (no longer Meta-only); the collector returns cross-platform samples so routing is demoable offline.
  - Live HTTP paths are gated and untested without credentials — same maturity as the Meta path. Verify each platform's auth ceremony + budget unit (分 vs 元) per `docs/intraday-research.md`. 9 tests.

## [0.0.5] — 2026-06-02

### Added
- **Intraday spend-side control — `drip watch`.** The hourly layer above the daily engine: pacing, cost-spike, and budget-exhaustion signals → conservative **throttle / pause / small-raise** actions, every N minutes, through the same gated + audited write path as `drip apply`.
  - `drip.engine.intraday` — `evaluate_intraday` (pace ratio · cost ratio · spike vs baseline · projected exhaustion) + `decide_intraday` (deterministic rules with a rule chain + confidence). ROI is **never** optimised here (ROAS isn't stable intraday); changes stay small to avoid resetting the learning phase, and thin recent samples can't pause or raise.
  - `drip watch [--once] [--interval N]` — runs the cycle; offline on a sample intraday series, live with a token + hourly data. shadow by default.
  - 9 tests for the spend-side signals + rules.

## [0.0.4] — 2026-06-02

### Added
- **Real Meta write path — `drip apply`.** The first command that pushes decisions to a live platform: collect → diagnose → allocate → **apply**. Each scale/pause becomes a real Meta Marketing API mutate (`facebook-business` SDK, lazy-imported), gated three ways and audited.
  - `drip.adapters.ads.MetaWriter` — maps `SCALE`/`REDUCE` → `daily_budget` (in cents) and `PAUSE` → `status=PAUSED` on a campaign (or adset via `--level adset`). Snapshots the old value first, re-reads after to **verify** the change landed, and is **idempotent** (an already-paused campaign is skipped, not re-written).
  - `drip.safety` — money-safety guards + an append-only audit trail. `DRIP_BUDGET_CAP` caps any single daily budget; new `DRIP_MAX_CHANGE_PCT` (default 0.5) refuses one-step jumps large enough to reset the platform learning phase. Every write (real or shadow) is appended to `DRIP_AUDIT_PATH`.
  - Three-way safety: **shadow** sends nothing · **copilot** prompts y/N per write · **autonomous** (or `--yes`) applies within caps. With no `META_ACCESS_TOKEN`, every write is shadow — so `drip apply` runs safely offline.
- 14 tests for the write path and guards (action→params mapping, token gate, idempotency, dry-run, post-write verify, budget/learning-phase caps, audit trail).

### Note
- The write path is implemented and tested; the roadmap's "first live Meta write" is checked once it runs against a real account with your credentials. TikTok/China-platform writers are still shadow (tracked for v0.3).

## [0.0.3] — 2026-06-02

### Added
- **`docs/intraday-research.md`** — a research dossier covering three things, in Drip's read-it-don't-trust-us spirit:
  - An honest **capability self-audit** of the open-source build (what's a real deterministic/auditable path vs. what's still a shadow stub or roadmap — e.g. the decision engine, allocator, attribution, and LLM layer are real and offline-runnable; the live ad-platform *write* path is still a v0.2 stub).
  - **Platform "minute-level" capability research** across Meta, Tencent Ads (腾讯广告), Ocean Engine (巨量引擎), Kuaishou (快手磁力), and TikTok — finest report granularity, data latency/retroactive correction, native auto-rule cadence, mutate-API write endpoints, and rate limits, with first-party sources and adversarial fact-checking. Headline: every major platform tops out at **hourly** reporting and **30-min–1-hour** native auto-rules; true "minute-level ROI optimisation" is marketing, while **spend-side pacing/cost-control** is genuinely near-real-time.
  - A **two-tier intraday-control design** (daily strategic layer + an hourly spend-side intraday layer) and a staged plan to wire the real write path.

### Changed
- **Web console (`web/app.html`) overhaul** — unified Manus-style sidebar (collapsible, drag-resizable, identical expanded/collapsed layout with no jump), a settings modal with light/dark/auto theme, a brand-native line-art water-droplet welcome illustration, 12 authored end-to-end UA conversations, platform-logo SVG sprites, a taller chat composer, and a low-key GitHub star button. Punctuation and i18n base strings cleaned up across 10 languages.
- The live demo now points at the chat-driven console (`web/app.html`) rather than the static landing page.

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
