# Contributing to Drip

Drip is in **early alpha** — the most useful contributions right now are:

1. **Trying it** on a real anime / gacha game and filing what breaks.
2. **Drip-Bench cases.** We need 20 hand-curated UA decision cases. See [#3](https://github.com/drip-agent/drip/issues/3).
3. **Provider adapters.** Apple Search Ads, Pangle, 巨量引擎. Each is a tight ~150-line PR.
4. **Worker improvements.** Especially `creative.py` (concept brainstorm) and `bidding.py` (allocation strategy).

## Dev setup

```bash
git clone https://github.com/drip-agent/drip.git
cd drip
uv venv -p 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run the dry-run demo (no API calls).
drip demo

# Lint + types + tests
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

## Commits

Conventional Commits, please:

```
feat: add Pangle ads adapter
fix(video): handle 24h URL expiry race in download path
docs: expand quickstart for Windows users
refactor(workers): extract concept brainstorm into a subagent
```

## License

By contributing you agree your contributions are licensed under Apache-2.0.

## Code of conduct

Be kind. Don't be racist, sexist, or otherwise terrible. Maintainers reserve the right to remove anyone failing this bar.
