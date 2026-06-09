"""Drip-Bench runner.

Wire-up between cases, agent, judge, and scorer. Writes a reproducible
run bundle to ``benchmarks/runs/<timestamp>/`` and prints a rich-table
scoreboard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from drip.eval.agents import Agent, build_agent
from drip.eval.judges import Judge, default_judge
from drip.eval.loader import load_all, load_one
from drip.eval.schema import AgentResponse, Case, CaseScore, RunResult
from drip.eval.scorer import score

console = Console()


def _runs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks" / "runs"


def _write_bundle(
    run_dir: Path,
    agent_name: str,
    judge_name: str,
    cases: list[Case],
    responses: list[AgentResponse],
    scores: list[CaseScore],
    started: datetime,
    finished: datetime,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "agent": agent_name,
        "judge": judge_name,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "case_ids": [c.id for c in cases],
        "total_score": sum(s.total for s in scores),
        "max_score": 100.0 * len(scores),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for case, resp, sc in zip(cases, responses, scores, strict=True):
        prefix = f"{case.id:03d}"
        (run_dir / f"{prefix}.case.yaml").write_text(
            json.dumps(case.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
        (run_dir / f"{prefix}.response.json").write_text(
            json.dumps(resp.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
        (run_dir / f"{prefix}.score.json").write_text(
            json.dumps(sc.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )

    summary = {
        **manifest,
        "per_case": [
            {
                "case_id": s.case_id,
                "total": s.total,
                "action": s.action_part,
                "direction": s.direction_part,
                "reasoning": s.reasoning_part,
                "chosen": s.chosen_action,
                "ground_truth": s.ground_truth_action,
            }
            for s in scores
        ],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))


def _print_header(agent_name: str, judge_name: str, n_cases: int) -> None:
    console.print(Panel.fit(
        f"agent  = [bold]{agent_name}[/bold]\n"
        f"judge  = {judge_name}\n"
        f"cases  = {n_cases}",
        title="drip-bench v0",
        border_style="bright_black",
    ))


def _print_scoreboard(cases: list[Case], scores: list[CaseScore]) -> None:
    table = Table(title="case-by-case", border_style="bright_black")
    table.add_column("id", style="bright_black")
    table.add_column("category")
    table.add_column("pick")
    table.add_column("truth")
    table.add_column("action", justify="right")
    table.add_column("dir", justify="right")
    table.add_column("reasoning", justify="right")
    table.add_column("total", justify="right", style="bold")
    for case, s in zip(cases, scores, strict=True):
        ok = s.chosen_action == s.ground_truth_action
        table.add_row(
            f"{case.id:03d}",
            case.category,
            f"[green]{s.chosen_action}[/green]" if ok else f"[red]{s.chosen_action}[/red]",
            s.ground_truth_action,
            f"{s.action_part:.1f}",
            f"{s.direction_part:.1f}",
            f"{s.reasoning_part:.1f}",
            f"{s.total:.1f}",
        )
    total = sum(s.total for s in scores)
    max_total = 100.0 * len(scores)
    table.add_section()
    table.add_row(
        "—", "—", "—", "—",
        f"{sum(s.action_part for s in scores):.1f}",
        f"{sum(s.direction_part for s in scores):.1f}",
        f"{sum(s.reasoning_part for s in scores):.1f}",
        f"[bold]{total:.1f} / {max_total:.0f}[/bold]",
    )
    console.print(table)


def run_bench(
    agent_name: str = "dummy",
    case_id: int | None = None,
    write_bundle: bool = True,
    judge_model: str | None = None,
) -> RunResult:
    """Run the whole suite (or one case) against ``agent_name``.

    ``judge_model`` optionally pins the LLM-as-judge to a specific model
    (any drip.llm spec). Defaults to auto-detect, then heuristic fallback.
    """
    agent: Agent = build_agent(agent_name)
    judge: Judge = default_judge(judge_model)

    if case_id is not None:
        cases = [load_one(case_id)]
    else:
        cases = load_all()

    if not cases:
        console.print("[yellow]no cases found — check benchmarks/cases/[/yellow]")
        raise SystemExit(2)

    _print_header(agent.name, judge.name, len(cases))

    started = datetime.now(UTC)
    responses: list[AgentResponse] = []
    scores: list[CaseScore] = []
    for case in cases:
        console.print(f"\n[bold cyan]▸ {case.id:03d}[/bold cyan]  {case.title}")
        try:
            resp = agent.answer(case)
        except Exception as exc:
            # One bad/empty model response shouldn't abort the whole run — score
            # the case zero and carry on, keeping the error in the bundle.
            console.print(f"  [red]agent error — scored 0:[/red] {str(exc)[:160]}")
            resp = AgentResponse(chosen_action="", reasoning="", raw={"error": str(exc)})
        checks = judge.evaluate(
            resp.reasoning, case.ground_truth.reasoning_must_mention
        )
        sc = score(case, resp, checks)
        responses.append(resp)
        scores.append(sc)
        console.print(
            f"  chose [bold]{sc.chosen_action}[/bold] "
            f"(truth: {sc.ground_truth_action}) — "
            f"{sc.total:.1f}/100"
        )

    finished = datetime.now(UTC)
    _print_scoreboard(cases, scores)

    if write_bundle:
        ts = started.strftime("%Y-%m-%dT%H-%M-%S")
        run_dir = _runs_dir() / f"{ts}__{agent.name.replace(':', '-').replace('/', '-')}"
        _write_bundle(
            run_dir, agent.name, judge.name, cases,
            responses, scores, started, finished,
        )
        console.print(f"\n  bundle → [cyan]{run_dir}[/cyan]")

    return RunResult(
        agent_name=agent.name,
        started_at=started,
        finished_at=finished,
        case_scores=scores,
    )


def list_cases() -> None:
    """Print available cases."""
    cases = load_all()
    table = Table(title=f"drip-bench v0 · {len(cases)} cases",
                  border_style="bright_black")
    table.add_column("id", style="bright_black")
    table.add_column("category")
    table.add_column("difficulty")
    table.add_column("title")
    for case in cases:
        table.add_row(
            f"{case.id:03d}",
            case.category,
            case.difficulty,
            case.title,
        )
    console.print(table)


def show_case(case_id: int) -> None:
    case = load_one(case_id)
    console.print(Panel.fit(
        f"[bold]{case.title}[/bold]\n"
        f"category = {case.category}   difficulty = {case.difficulty}",
        title=f"case {case.id:03d}",
        border_style="bright_black",
    ))
    console.print("\n[bold]CONTEXT[/bold]")
    console.print(case.context)
    console.print(f"\n[bold]QUESTION[/bold]  {case.question}")
    console.print("\n[bold]CHOICES[/bold]")
    for k, v in case.choices.items():
        console.print(f"  {k}: {v}")
    console.print("\n[bold]GROUND TRUTH[/bold]")
    console.print(f"  action = {case.ground_truth.action}")
    if case.ground_truth.numeric_delta is not None:
        console.print(f"  delta  = {case.ground_truth.numeric_delta:+.2f}")
    console.print("  reasoning:")
    for line in case.ground_truth.reasoning.strip().split("\n"):
        console.print(f"    {line}")
    console.print("\n[bold]MUST-MENTION[/bold]")
    for m in case.ground_truth.reasoning_must_mention:
        console.print(f"  · {m}")
    console.print(f"\n[dim]source: {case.source}[/dim]")
