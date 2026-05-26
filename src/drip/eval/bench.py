"""Drip-Bench — v0 placeholder.

Goal: 20 hand-curated UA decision cases. Each case is
  (campaign_state_json, ground_truth_action).

Drip runs Bidding worker against each state; we score by:
  - exact-match on action_type (pause / scale / hold)
  - direction agreement on budget delta
  - rationale BLEU against a senior UA's notes

v0 ships an empty scaffold so the CLI command resolves. The first 20 cases
are sourced from public Sensor Tower data + AppsFlyer aggregate benchmarks.
"""

from __future__ import annotations

from rich.console import Console

console = Console()


def run_bench(suite: str = "v0") -> None:
    if suite == "v0":
        console.print("[yellow]drip-bench v0 — cases not yet curated.[/yellow]")
        console.print("see https://github.com/drip-agent/drip/issues/3 to follow progress.")
        return
    raise SystemExit(f"unknown bench suite: {suite}")
