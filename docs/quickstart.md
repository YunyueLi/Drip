# Quickstart

5 minutes from a fresh clone of **Drip** to a benchmark run.

## Prereqs

- Python **3.11+**
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
# Validate the CLI wiring
drip --help

# Walk the whole loop on offline samples (no keys, no writes)
drip run

# Diagnose a campaign into 8-signal decision cards
drip doctor --metrics ./examples/account.yaml
```

`drip run` chains collect → diagnose → strategize → create → allocate → learn on
deterministic sample data — entirely offline and plan-only.

### 3. A real run (shadow → copilot)

Push the budget / pause decisions to the platforms. `shadow` plans only;
`copilot` asks before each write; both land in the audit trail:

```bash
drip apply --mode copilot     # diagnose → allocate → push (per-write approval)
drip watch --once             # intraday spend-side guard (pacing / cost-spike)
drip autopilot                # the whole loop, signal-routed + circuit breaker
```

With no `META_ACCESS_TOKEN` every write stays shadow, so this is safe offline.
For real creative assets, install the generator SDKs and set a key:

```bash
uv pip install -e ".[providers]"   # openai, volcenginesdkarkruntime
OPENAI_API_KEY=sk-... drip run --generator gpt-image   # else falls back to dry
```

## Copilot / autonomous

Set `DRIP_MODE=copilot` or `DRIP_MODE=autonomous` in `.env`. Then:

- **Copilot** — every platform write is staged and waits for Slack approval.
- **Autonomous** — writes go through up to `DRIP_BUDGET_CAP`.

You will also need `META_ACCESS_TOKEN` / `TIKTOK_ACCESS_TOKEN` / a configured AppsFlyer integration. See `.env.example`.

## What to look at next

- [`benchmarks/README.md`](../benchmarks/README.md) — why Drip-Bench exists, how scoring works, how to contribute a case.
- [`docs/architecture.md`](./architecture.md) — how the layers (CLI, pipeline, agents, decision engine, slots) fit together.
- [`src/drip/engine/`](../src/drip/engine/) — the deterministic core: 8 signals → rules → card, the part you can audit.
- [`src/drip/eval/`](../src/drip/eval/) — the bench harness; this is where Drip earned its place in the open vs. the closed-source crowd.
