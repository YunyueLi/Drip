# Drip-Bench

**The open benchmark for AI user-acquisition agents.**

Drip-Bench is a curated set of UA decision cases that any agent — Drip, a
plain LLM, a competitor SaaS, or a hand-written script — can be evaluated
against. Same inputs, same scoring, same leaderboard.

We publish the cases, the rubric, and the harness. You publish your score.

---

## Why this exists

Three things are true today:

1. **Every UA-agent vendor claims "70% lower CPA" or "5x ROAS lift."** None
   publish the cases that produced those numbers. None publish their
   reasoning. None invite reproduction.
2. **A "good UA decision" is more than `pause` vs. `scale`.** It is *why*,
   *how much*, *what to monitor*, and *what to revert to*. A benchmark that
   only checks the action label is a benchmark you can game.
3. **The agent stack is moving fast** (Meta Ads CLI, MCP Connectors, Claude
   Agent SDK subagents). Without a common yardstick, every release reads
   like marketing.

Drip-Bench fills that gap.

---

## What's in v0

- **10 hand-curated cases** across the core UA decision surface (scale,
  pause, reallocate, fatigue, anomaly, cohort, audience, bid strategy,
  market entry, crisis).
- **A three-part rubric**: action match (40), direction match (20),
  reasoning quality (40, LLM-as-judge with required-mention coverage).
- **A pluggable agent interface** — bring your own LLM, your own SaaS, or
  Drip itself.
- **Reproducible runs**: every result is a JSON bundle (prompt, response,
  intermediate signals, score breakdown) that anyone can replay.

---

## Quickstart

```bash
# List cases
drip bench list

# Inspect a case
drip bench show 001

# Run all cases against the bundled baseline (no API key needed)
drip bench run --agent dummy

# Run against raw Claude (needs ANTHROPIC_API_KEY)
drip bench run --agent claude-sonnet-4-6

# Run against Drip itself (uses the Bidding worker)
drip bench run --agent drip

# Run a single case
drip bench run --case 001 --agent claude-sonnet-4-6
```

Results write to `benchmarks/runs/<timestamp>/` as JSON. Aggregate
scoreboard prints to stdout.

---

## Design philosophy

### Cases are real, not toy

Every case is grounded in patterns we have personally seen managing UA
budgets, cross-referenced against public sources (AppsFlyer aggregate
benchmarks, Sensor Tower estimates, anonymized practitioner anecdotes).
We do not invent numbers that don't happen.

### Cases are adversarial-by-default

A naive "all green → scale" agent will pass case 001 and fail cases 002,
005, and 010. A naive "never pause" agent will fail 002. Cases are
designed to discriminate.

### Scoring is layered, not binary

A correct action with hand-wavy reasoning scores worse than a correct
action that names the right risks. We grade reasoning by checking
whether the agent mentions the specific signals that should drive the
decision (`reasoning_must_mention` in each case YAML).

### The benchmark is also a teaching tool

Each case YAML doubles as a worked example. A new growth engineer can
read `001_scale_dilemma.yaml` and learn *what good looks like* — the
ground-truth `reasoning` field is the model answer.

### v0 is small on purpose

10 cases is not enough to claim statistical significance. It is enough
to expose obvious weaknesses (a SaaS that scores < 600/1000 on 10 cases
is in trouble). v1 targets 50 cases with at least 3 cases per category
and human-verified ground truth from > 3 reviewers.

---

## What Drip-Bench is *not*

- **Not a backtest.** We do not replay historical campaign data. We test
  whether the agent makes the right *decision* given a snapshot.
- **Not a creative quality benchmark.** Image / video generation is
  evaluated separately (see `benchmarks/creative/`, not yet shipped).
- **Not a platform-integration test.** We test reasoning, not whether
  the agent can authenticate to Meta Marketing API.
- **Not closed.** Pull requests welcome. Anyone can add a case (see
  `SCHEMA.md`). Cases survive review if (a) at least 3 senior UA
  reviewers agree on the ground truth and (b) the case discriminates
  (median agent score should fall between 30% and 70%).

---

## Leaderboard

Public leaderboard: `bench.drip.dev` (planned for v0.3).

We run baselines on every release:

| Agent                  | Score (v0) | Last run |
| ---------------------- | ---------- | -------- |
| Dummy (random)         | TBD        | —        |
| Claude Sonnet 4.6 raw  | TBD        | —        |
| GPT-4o raw             | TBD        | —        |
| Drip v0.0.1            | TBD        | —        |

If you ship a UA agent, run Drip-Bench against it and send us the JSON
bundle. We publish the result, win or lose. We will publish ours too.

---

## How to contribute a case

See [SCHEMA.md](./SCHEMA.md). TL;DR:

1. Copy `cases/001_scale_dilemma.yaml` as a template.
2. Fill in the context, choices, ground truth, and `reasoning_must_mention`.
3. Cite your source. Synthetic cases are fine as long as the numbers are
   plausible — we'll ask in review.
4. Open a PR. We need at least 3 reviewer +1s on the ground truth.

---

## Citation

If you use Drip-Bench in research, please cite:

```
@misc{dripbench2026,
  title  = {Drip-Bench: An Open Benchmark for UA Agent Decisions},
  author = {Drip Contributors},
  year   = {2026},
  url    = {https://github.com/YunyueLi/Drip/tree/main/benchmarks}
}
```

License: same as Drip — Apache-2.0. Use it, fork it, beat us.
