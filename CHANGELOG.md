# Changelog

All notable changes to **Drip** will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v0.1
- Replace the deterministic concept brainstorm with a Claude Agent SDK subagent.
- First end-to-end run against a real Meta test account (`mode=copilot`).
- First 20 Drip-Bench cases curated from public benchmark data.

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
