# Drip-Bench case schema

Every case is a YAML file in `benchmarks/cases/`. Filename pattern:
`NNN_<short-slug>.yaml` where `NNN` is a zero-padded 3-digit id.

## Required fields

```yaml
id: 1                           # int, matches filename prefix
category: scale_decision        # see categories below
title: "Signals green but sample on the edge"
difficulty: medium              # easy | medium | hard

# Free-form prose describing the situation the agent is presented with.
# Numbers should be realistic (cite source in the `source` field).
context: |
  You manage a Meta US prospecting campaign. Over the last 72h:
    spend       $200/day (cap $240)
    CPP         $18  (target $25)
    ROAS        3.8x (target 3.0x)
    ...

# Multiple-choice anchors. Agent must pick one of these keys.
# Use plain capitalised verbs + a numeric delta where meaningful.
question: "What is your decision?"
choices:
  A: "SCALE +20%"
  B: "SCALE +50%"
  C: "HOLD"
  D: "PAUSE"

# The single correct answer + the reasoning a good answer should cover.
ground_truth:
  action: A
  numeric_delta: +0.20           # optional, used by direction_match scorer
  reasoning: |
    The signals are green but daily conversions (11) are barely above
    minimum sample size (10). Past data shows aggressive scales on
    thin samples regress hard. Conservative +20% preserves upside
    while keeping the campaign in the same risk regime.
  reasoning_must_mention:
    - "daily conversions are close to minimum sample"
    - "history of aggressive scale regressing CPP"
    - "preference for conservative step over aggressive step"

# How this case is scored. Defaults shown; usually you only override
# `reasoning_must_mention` weights or remove `direction_match` for
# categorical cases.
scoring:
  action_match_max: 40           # full marks if `action` matches
  direction_match_max: 20        # partial marks for same-direction wrong magnitude
  reasoning_max: 40              # LLM-as-judge over `reasoning_must_mention`
  partial_credit:                # optional per-choice partial credit
    A: 40
    B: 20                        # right direction, wrong magnitude
    C: 10                        # safe but suboptimal
    D: 0                         # wrong direction

# Provenance. Required.
source: "synthetic — informed by AppsFlyer 2025 benchmark report"
tags: ["meta", "prospecting", "scale", "sample-size"]
```

## Categories

`v0` covers 10 categories, one case each:

| id  | category              | what it tests                                              |
| --- | --------------------- | ---------------------------------------------------------- |
| 001 | `scale_decision`      | Should the agent scale? By how much?                       |
| 002 | `pause_decision`      | When to cut losses                                         |
| 003 | `budget_reallocation` | Move spend across channels/accounts/campaigns              |
| 004 | `creative_fatigue`    | Detect saturation and trigger creative refresh             |
| 005 | `anomaly_diagnosis`   | Root-cause a sudden metric shift                           |
| 006 | `cohort_quality`      | Distinguish good D1 retention from a noisy spike           |
| 007 | `audience_expansion`  | When to broaden targeting vs hold lookalikes               |
| 008 | `bid_strategy_switch` | Switch from `lowest cost` → `cost cap` etc.                |
| 009 | `market_entry`        | Should the agent open a new region/locale?                 |
| 010 | `crisis_response`     | Policy change, tracking break, platform outage — what now? |

## Scoring formula

```
case_score = action_part + direction_part + reasoning_part
              [0..40]       [0..20]          [0..40]
total_score = sum(case_scores)     # /1000 for v0
```

### action_part

If `chosen_action == ground_truth.action`, award `action_match_max`.
Otherwise look up `scoring.partial_credit` for the chosen action; default
to 0.

### direction_part

For numeric cases (`ground_truth.numeric_delta` is present): if the
agent's delta has the same sign as ground truth, award proportional
credit based on magnitude proximity. For pure-categorical cases this
field is 0 and `action_match_max` should be raised to 60 to compensate.

### reasoning_part

LLM-as-judge (Claude Sonnet by default) scores each item in
`reasoning_must_mention` independently:

- **fully covered (clear, specific reference)** → 1.0
- **partially covered (vague but adjacent)** → 0.5
- **not mentioned** → 0.0

Average across items × `reasoning_max`.

## Agent interface

An agent is anything that implements:

```python
class Agent(Protocol):
    name: str

    def answer(self, case: Case) -> AgentResponse:
        ...

class AgentResponse(BaseModel):
    chosen_action: str          # one of case.choices keys, e.g. "A"
    numeric_delta: float | None # optional, used by direction_match
    reasoning: str              # free text — graded by judge
```

Drip ships three built-in agents:

- `dummy` — picks a fixed choice; useful as a sanity baseline.
- `claude-<model>` — calls Anthropic API directly with a standard prompt.
- `drip` — invokes Drip's own Bidding worker.

To add your own agent, write a Python module that exposes `answer(case)`
and register it via `--agent module.path:agent_name`.

## Reproducibility

Every `bench run` writes a directory `benchmarks/runs/<timestamp>/`
containing:

```
benchmarks/runs/2026-05-28T14-23-00/
├── manifest.json          # agent name, version, env hash, case ids
├── 001.case.yaml          # exact case used
├── 001.response.json      # agent's raw response
├── 001.score.json         # full score breakdown + judge transcript
├── ...
└── summary.json           # aggregate score, percentile per category
```

Anyone with the manifest can rerun the same agent on the same cases and
diff the score. That is the reproducibility contract.
