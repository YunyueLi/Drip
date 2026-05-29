# Quickstart

5 minutes from a fresh clone of **Drip** to a benchmark run.

## Prereqs

- Python **3.11** (OASIS does not yet support 3.12)
- [uv](https://docs.astral.sh/uv/) — strongly recommended

## Install

```bash
git clone https://github.com/YunyueLi/Drip.git
cd Drip
uv venv -p 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
# `ANTHROPIC_API_KEY` is the only key needed for the bench to run with
# a real LLM agent + judge. Without it, Drip-Bench falls back to a
# heuristic judge and a dummy agent — you can still see the harness work.
```

## Three things to try, in order

### 1. Drip-Bench (the headline feature)

```bash
# What's in the suite?
drip bench list

# Look at one case in detail (context, choices, ground truth, must-mentions)
drip bench show 1

# Run the dummy baseline — zero API calls, sanity check that everything wired
drip bench run --agent dummy --no-bundle

# Run raw Claude over the whole suite
export ANTHROPIC_API_KEY=sk-ant-...
drip bench run --agent claude

# Drill into one case
drip bench run --case 5 --agent claude
```

After each run, look at `benchmarks/runs/<timestamp>__<agent>/` — that bundle is fully reproducible and ready to PR.

### 2. The end-to-end agent pipeline

```bash
# Validate the CLI wiring and demo campaign spec
drip --help
drip demo
```

This walks the orchestrator through creative → audience → bidding → reporter against the bundled `examples/demo_game.yaml`, with no external API calls.

### 3. A real run (shadow mode)

Install the provider SDKs (they're not in the core install):

```bash
uv pip install -e ".[all]"   # openai, volcenginesdkarkruntime, camel-oasis…
```

Then:

```bash
drip launch \
  --game ./examples/demo_game.yaml \
  --budget 500 \
  --regions jp,sg,tw
```

Even in shadow mode, this hits the image, video, and (if installed) OASIS adapters — so you'll burn a small amount of OpenAI / ARK credits.

## Copilot / autonomous

Set `DRIP_MODE=copilot` or `DRIP_MODE=autonomous` in `.env`. Then:

- **Copilot** — every platform write is staged and waits for Slack approval.
- **Autonomous** — writes go through up to `DRIP_BUDGET_CAP`.

You will also need `META_ACCESS_TOKEN` / `TIKTOK_ACCESS_TOKEN` / a configured AppsFlyer integration. See `.env.example`.

## What to look at next

- [`benchmarks/README.md`](../benchmarks/README.md) — why Drip-Bench exists, how scoring works, how to contribute a case.
- [`docs/architecture.md`](./architecture.md) — how the layers (orchestrator, workers, adapters, bench) fit together.
- [`src/drip/orchestrator.py`](../src/drip/orchestrator.py) — the supervisor today is a fixed pipeline; v0.2 replaces it with Claude Agent SDK subagent routing.
- [`src/drip/eval/`](../src/drip/eval/) — the bench harness; this is where Drip earned its place in the open vs. the closed-source crowd.
