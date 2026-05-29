# Contributing to Drip

Drip is in **early alpha**. The most useful contributions right now:

1. **Run [Drip-Bench](benchmarks/) against any agent** — yours, ours, a competitor's — and PR the result bundle. Win or lose. See [`benchmarks/README.md`](benchmarks/README.md).
2. **Add a benchmark case.** See [`benchmarks/SCHEMA.md`](benchmarks/SCHEMA.md). We need ≥ 3 reviewer +1s on the ground truth, and the case must discriminate (median agent score should land between 30% and 70%).
3. **Knowledge Packs.** YAML-only contributions: baselines, signal thresholds, and prompt overrides for a specific vertical (anime / gacha, DTC, tools-app, B2B SaaS) or region. No Python required.
4. **Provider adapters.** Apple Search Ads, Pangle, 巨量引擎. Each is a tight ~150-line PR.
5. **Worker improvements** — especially `bidding.py` (decision logic) and `reporter.py` (decision-card formatting).
6. **Try Drip end-to-end** on a real campaign and file what breaks.

## Dev setup

```bash
git clone https://github.com/YunyueLi/Drip.git
cd Drip
uv venv -p 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Smoke checks (no API keys needed)
drip demo                              # dry-run agent pipeline
drip bench run --agent dummy           # dummy baseline against bench v0

# Lint / types / tests
ruff check .
mypy src
pytest
```

Python is pinned to **3.11** because OASIS has a `<3.12` upper bound. Don't try to relax this until upstream ships 3.12 support.

## Coding style

- **`ruff` is the source of truth.** Run it before pushing.
- Public APIs get type hints; we run `mypy --strict` on `src/`.
- One-line module docstrings; no multi-paragraph blocks.
- Don't add comments that restate the code. Comments explain *why*, not *what*.

## Architecture notes for PR authors

- The orchestrator owns budget + mode + artifact passing. Workers must not touch the budget directly — they request work, the orchestrator decides.
- Adapters must support a deterministic fallback (`dry_run=True`) so `drip demo` works without any API keys. See `simulation.py::_deterministic_stub` for the pattern.
- Real ad-platform writes are gated by `RunMode != SHADOW` *and* by the relevant token being set. Don't bypass either check.
- Every decision the agent makes should be reproducible from disk. If you add a new decision path, it must write to the run bundle alongside `signals`, `reasoning`, and `score` so it can be replayed.

## Adding a benchmark case

1. Copy `benchmarks/cases/001_scale_dilemma.yaml` as a template.
2. Fill in `context`, `choices`, `ground_truth`, and at least 3 items in `reasoning_must_mention`.
3. Pick a `category` (existing categories preferred for v0; new ones need an issue first).
4. Cite your `source`. Synthetic cases are fine if the numbers are plausible — reviewers will ask.
5. PR title: `bench: add case NNN — <short slug>`.
6. PR description must include a baseline run of `drip bench run --agent dummy --case NNN` and `drip bench run --agent claude --case NNN` so reviewers can see the case discriminates.
7. Needs ≥ 3 reviewer +1s on the ground truth before merge.

## Adding a Knowledge Pack

Knowledge Packs live in `packs/` (coming in v0.1) and contain only YAML + Markdown. A pack registers:

- Extra signals on top of the core 10 (e.g. anime: `character_preference`, `core_vs_casual_ratio`).
- Prompt overrides for `creative.py` and `reporter.py`.
- Default baselines and guardrails for the vertical.

Knowledge Pack PRs do not require Python review and have a separate review path.

## Commits

Conventional Commits, please:

```
feat: add Pangle ads adapter
fix(video): handle 24h URL expiry race in download path
bench: add case 011 — frequency cap negotiation
docs: expand quickstart for Windows users
refactor(workers): extract concept brainstorm into a subagent
```

## License

By contributing you agree your contributions are licensed under Apache-2.0.

## Code of conduct

Be kind. Don't be racist, sexist, or otherwise terrible. Maintainers reserve the right to remove anyone failing this bar.
