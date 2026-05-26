# Quickstart

5 minutes from a fresh clone of **Drip** to a dry-run.

## Prereqs

- Python **3.11** (OASIS does not yet support 3.12)
- [uv](https://docs.astral.sh/uv/) — strongly recommended

## Install

```bash
git clone https://github.com/YunyueLi/Drip.git
cd drip
uv venv -p 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
# At minimum, set ANTHROPIC_API_KEY. The other keys can stay blank for
# shadow / dry-run mode.
```

## Sanity check

```bash
# Validates the CLI is wired and the demo game spec parses.
drip --help
drip demo
```

You should see the orchestrator walk through creative → audience → bidding →
reporter against the bundled `examples/demo_game.yaml`, with no external API
calls.

## Real run (shadow mode)

```bash
drip launch \
  --game ./examples/demo_game.yaml \
  --budget 500 \
  --regions jp,sg,tw
```

Even in shadow mode, this hits the image, video, and (if installed) OASIS
adapters — so you'll burn a small amount of OpenAI / ARK credits.

## Copilot / autonomous

Set `DRIP_MODE=copilot` or `DRIP_MODE=autonomous` in `.env`. Then:

- Copilot: every platform write is staged and waits for Slack approval.
- Autonomous: writes go through up to `DRIP_BUDGET_CAP`.

You will also need `META_ACCESS_TOKEN` / `TIKTOK_ACCESS_TOKEN` / a
configured AppsFlyer integration. See `.env.example`.

## What to check next

- `docs/architecture.md` — how the workers and adapters fit together.
- `src/drip/orchestrator.py` — the supervisor today is a fixed pipeline; v0.2
  replaces it with Claude Agent SDK subagent routing.
- `src/drip/eval/bench.py` — empty in v0; the first 20 Drip-Bench cases are
  the bigger lever for evaluating *decision* quality over time.
