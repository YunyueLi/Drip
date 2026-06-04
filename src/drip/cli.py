"""drip CLI — `drip launch`, `drip demo`, `drip bench {list,show,run}`."""

from __future__ import annotations

import asyncio
import datetime
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from drip import __version__, safety
from drip.adapters.writers import build_writer
from drip.orchestrator import DripOrchestrator, GameSpec, RunMode

console = Console()

_STATUS_COLOUR: dict[str, str] = {
    "applied": "green",
    "shadow": "bright_black",
    "skipped": "yellow",
    "failed": "red",
    "denied": "red",
}


@dataclass
class WriteRequest:
    """A single budget/status change to push to an ad platform."""

    platform: str
    campaign_id: str
    label: str
    action: str          # "SCALE" | "REDUCE" | "PAUSE"
    old_budget: float
    new_budget: float
    change_display: str  # "→ $0/day" or "$200 → $300/day"


@dataclass
class WriteResult:
    """Outcome of one attempted write."""

    status: str          # applied | shadow | skipped | failed | denied
    detail: str = ""
    audit_file: Path | None = None
    colour: str = "white"


def _execute_write(
    req: WriteRequest,
    *,
    caps: safety.Caps,
    mode_enum: RunMode,
    send_live: bool,
    yes: bool,
    level: str,
    confirm_prompt: str | None = None,
    extra_audit_fields: dict[str, object] | None = None,
) -> WriteResult:
    """Guard, approve, write, audit — the common write path for all commands."""
    # 1. Money-safety guard
    try:
        safety.guard_change(
            action=req.action, old_budget=req.old_budget,
            new_budget=req.new_budget, caps=caps,
        )
    except safety.GuardError as exc:
        rec: dict[str, object] = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "mode": mode_enum.value, "platform": req.platform,
            "target_id": req.campaign_id, "action": req.action,
            "status": "denied", "detail": str(exc), "label": req.label,
        }
        if extra_audit_fields:
            rec.update(extra_audit_fields)
        audit_file = safety.audit(rec)
        return WriteResult(status="denied", detail=str(exc),
                          audit_file=audit_file, colour="red")

    # 2. Human approval (copilot mode)
    approved = True
    if send_live and mode_enum is RunMode.COPILOT and not yes:
        prompt = confirm_prompt or f"  {req.action}  {req.label}  {req.change_display} ?"
        approved = click.confirm(prompt, default=False)

    # 3. Write
    r = build_writer(req.platform, level=level).apply_decision(
        req.campaign_id, req.action, new_budget=req.new_budget,
        dry_run=not (send_live and approved), label=req.label,
    )
    if not approved:
        r.status, r.detail = "skipped", "declined by operator"

    # 4. Audit
    rec = r.to_dict()
    rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    rec["mode"] = mode_enum.value
    if extra_audit_fields:
        rec.update(extra_audit_fields)
    audit_file = safety.audit(rec)

    colour = _STATUS_COLOUR.get(r.status, "white")
    return WriteResult(status=r.status, detail=r.detail,
                      audit_file=audit_file, colour=colour)


def _load_env() -> None:
    load_dotenv()


def _read_game(path: Path) -> GameSpec:
    if not path.exists():
        raise click.ClickException(f"game spec not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GameSpec.model_validate(data)


def _resolve_mode(mode: str | None, default: str = "shadow") -> RunMode:
    """Resolve DRIP_MODE from CLI arg, env var, or default."""
    return RunMode(mode) if mode else RunMode(os.getenv("DRIP_MODE", default))


def _default_window(since: str | None, until: str | None,
                    lookback_days: int = 7) -> tuple[str, str]:
    """Fill in default since/until date strings when not provided via CLI."""
    today = datetime.date.today()
    until = until or today.isoformat()
    since = since or (today - datetime.timedelta(days=lookback_days)).isoformat()
    return since, until


@click.group()
@click.version_option(__version__, "-V", "--version")
def main() -> None:
    """drip — open-source reference implementation for AI user-acquisition agents."""
    _load_env()


@main.command()
@click.option("--game", "game_path", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to game spec YAML (see examples/demo_game.yaml).")
@click.option("--budget", type=float, required=True, help="Total USD budget for this run.")
@click.option("--regions", required=True, help="Comma-separated region codes, e.g. jp,sg,tw.")
@click.option("--mode", type=click.Choice([m.value for m in RunMode]),
              default=None, help="Override DRIP_MODE env var.")
@click.option("--dry-run", is_flag=True, help="Plan only, do not call any external API.")
def launch(game_path: Path, budget: float, regions: str, mode: str | None, dry_run: bool) -> None:
    """Launch an end-to-end UA run."""
    game = _read_game(game_path)
    region_list = [r.strip() for r in regions.split(",") if r.strip()]
    mode_enum = _resolve_mode(mode, "shadow")

    cap = float(os.getenv("DRIP_BUDGET_CAP", "0") or 0)
    if cap and budget > cap:
        raise click.ClickException(
            f"requested budget ${budget:.2f} exceeds DRIP_BUDGET_CAP ${cap:.2f}"
        )

    console.print(Panel.fit(
        f"[bold]{game.title}[/bold]  ·  ${budget:,.0f}  ·  {', '.join(region_list)}\n"
        f"mode = [yellow]{mode_enum.value}[/yellow]   dry-run = {dry_run}",
        title="drip launch", border_style="bright_black",
    ))

    orchestrator = DripOrchestrator(mode=mode_enum, dry_run=dry_run)
    try:
        asyncio.run(orchestrator.run(game=game, budget=budget, regions=region_list))
    except KeyboardInterrupt:
        console.print("[red]interrupted[/red]")
        sys.exit(130)


@main.command()
def demo() -> None:
    """Run a dry-run against the bundled demo game (no API calls)."""
    demo_path = Path(__file__).resolve().parents[2] / "examples" / "demo_game.yaml"
    game = _read_game(demo_path)
    console.print(Panel.fit(f"running demo: {game.title}", border_style="bright_black"))
    orchestrator = DripOrchestrator(mode=RunMode.SHADOW, dry_run=True)
    asyncio.run(orchestrator.run(game=game, budget=500.0, regions=["jp", "sg", "tw"]))


@main.group()
def bench() -> None:
    """Drip-Bench — open evaluation for UA agent decisions."""


@bench.command("list")
def bench_list() -> None:
    """List all benchmark cases."""
    from drip.eval import list_cases
    list_cases()


@bench.command("show")
@click.argument("case_id", type=int)
def bench_show(case_id: int) -> None:
    """Show a single case in detail."""
    from drip.eval import show_case
    show_case(case_id)


@bench.command("run")
@click.option("--agent", "agent_name", default="dummy",
              help="Agent to evaluate. e.g. dummy · openai/gpt-4o · "
                   "anthropic/claude-sonnet-4-6 · drip · drip:openai/gpt-4o · "
                   "openrouter/google/gemini-2.0-flash")
@click.option("--judge", "judge_model", default=None,
              help="Model to judge reasoning (any drip.llm spec). "
                   "Default auto-detects; falls back to heuristic.")
@click.option("--case", "case_id", type=int, default=None,
              help="Run only one case by id.")
@click.option("--no-bundle", is_flag=True,
              help="Do not write a reproducible run bundle.")
def bench_run(agent_name: str, judge_model: str | None,
              case_id: int | None, no_bundle: bool) -> None:
    """Run the bench against an agent."""
    from drip.eval import run_bench
    run_bench(agent_name=agent_name, case_id=case_id,
              write_bundle=not no_bundle, judge_model=judge_model)


@main.command()
@click.option("--metrics", "metrics_path",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="YAML/JSON of campaign metrics. Omit to run built-in samples.")
@click.option("--narrate", "narrate_model", default=None,
              help="LLM to narrate the 'why' (any drip.llm spec). "
                   "Omit for a template (no API call).")
def doctor(metrics_path: Path | None, narrate_model: str | None) -> None:
    """Diagnose a campaign with the 8-signal decision engine.

    The open, self-hostable take on a Midas-style Meta copilot: feed it a
    campaign's metrics and it returns a SCALE/HOLD/PAUSE decision card with
    the full signal vector, rule chain, and guardrails.
    """
    from drip.engine import CampaignMetrics, DecisionEngine
    from drip.engine.cards import print_card

    engine = DecisionEngine(narrate_model=narrate_model)
    if metrics_path:
        data = yaml.safe_load(Path(metrics_path).read_text())
        records = data if isinstance(data, list) else [data]
        campaigns = [CampaignMetrics(**rec) for rec in records]
    else:
        from drip.engine.engine import _DEMO_CASES
        campaigns = [m for _, m in _DEMO_CASES]

    for m in campaigns:
        result = engine.run(m)
        print_card(result.decision, result.signals, label=m.label, why=result.why)
        console.print()


@main.command()
@click.option("--since", default=None, help="Window start YYYY-MM-DD (default: 7 days ago).")
@click.option("--until", default=None, help="Window end YYYY-MM-DD (default: today).")
@click.option("--budget", type=float, default=1000.0, help="Total budget to allocate.")
@click.option("--narrate", "narrate_model", default=None,
              help="LLM for reports/briefs (any drip.llm spec). Omit for templates.")
@click.option("--generator", default="dry",
              help="Creative generator: dry / gpt-image / seedance / comfyui.")
@click.option("--cpp-target", type=float, default=25.0)
@click.option("--roas-target", type=float, default=3.0)
def run(since: str | None, until: str | None, budget: float, narrate_model: str | None,
        generator: str, cpp_target: float, roas_target: float) -> None:
    """Run the full one-stop pipeline end to end.

    collect → diagnose → strategy → creative → allocate → feedback.
    Offline by default (samples + templates); plug credentials/LLM/generator
    to go live, no code change.
    """
    from rich.table import Table

    from drip.pipeline import Pipeline

    since, until = _default_window(since, until)

    console.print(Panel.fit(
        f"one-stop run · {since} → {until} · budget ${budget:,.0f}",
        title="drip run", border_style="bright_black",
    ))
    result = Pipeline(
        total_budget=budget, narrate_model=narrate_model,
        creative_generator=generator, cpp_target=cpp_target, roas_target=roas_target,
    ).run(since=since, until=until)

    console.print(f"\n[bold]diagnosis[/bold]\n  {result.report.summary}")
    console.print("\n[bold]strategy[/bold]")
    for h in result.strategy.hypotheses:
        console.print(f"  [{h.direction}] {h.target} — {h.brief}")
    console.print(f"\n[bold]creative[/bold]  {len(result.variants)} variants produced")
    console.print("\n[bold]allocation[/bold]")
    tbl = Table(border_style="bright_black")
    tbl.add_column("platform")
    tbl.add_column("campaign")
    tbl.add_column("action")
    tbl.add_column("budget", justify="right")
    for a in result.plan.allocations:
        tbl.add_row(a.metrics.platform, a.metrics.label, a.reason, f"${a.new_budget:,.0f}")
    console.print(tbl)
    console.print("\n[bold]feedback[/bold]")
    for learning in result.feedback.learnings:
        console.print(f"  · {learning.insight}")


@main.command()
@click.option("--since", default=None, help="Window start YYYY-MM-DD (default: 7 days ago).")
@click.option("--until", default=None, help="Window end YYYY-MM-DD (default: today).")
@click.option("--budget", type=float, default=1000.0, help="Total budget to allocate before pushing.")
@click.option("--cpp-target", type=float, default=25.0)
@click.option("--roas-target", type=float, default=3.0)
@click.option("--mode", type=click.Choice([m.value for m in RunMode]), default=None,
              help="Override DRIP_MODE. `apply` defaults to copilot (approve each write).")
@click.option("--level", type=click.Choice(["campaign", "adset"]), default="campaign",
              help="Meta entity that holds budget/status.")
@click.option("--dry-run", is_flag=True, help="Plan and show every write, but never call the write API.")
@click.option("--yes", is_flag=True, help="Skip per-write prompts (autonomous-style; still capped).")
def apply(since: str | None, until: str | None, budget: float, cpp_target: float,
          roas_target: float, mode: str | None, level: str, dry_run: bool, yes: bool) -> None:
    """Diagnose, allocate, and PUSH the budget/pause decisions to Meta — the real write path.

    Defaults to copilot: every change waits for your y/N. `shadow` sends nothing;
    `autonomous` (or --yes) applies within the money-safety caps (DRIP_BUDGET_CAP,
    DRIP_MAX_CHANGE_PCT). With no META_ACCESS_TOKEN every write is shadow, so this
    runs safely offline. Every write — real or shadow — lands in the audit trail.
    """
    from rich.table import Table

    from drip.allocator import Allocator
    from drip.collectors import Collector
    from drip.engine.rules import Action

    mode_enum = _resolve_mode(mode, "copilot")
    since, until = _default_window(since, until)
    caps = safety.Caps.from_env()
    send_live = mode_enum is not RunMode.SHADOW and not dry_run

    console.print(Panel.fit(
        f"apply · mode=[yellow]{mode_enum.value}[/yellow] · "
        f"dry-run={dry_run} · writes route per-platform (shadow without that platform's token)",
        title="drip apply", border_style="bright_black",
    ))

    metrics = Collector().collect(since=since, until=until)
    plan = Allocator().plan(metrics, total_budget=budget,
                            cpp_target=cpp_target, roas_target=roas_target)

    tbl = Table(border_style="bright_black")
    for col in ("platform", "campaign", "action", "change", "result"):
        tbl.add_column(col)

    audit_file: Path | None = None
    n_applied = 0
    for a in plan.allocations:
        action = a.result.decision.action
        verb = action.value
        plat = a.metrics.platform
        old_b, new_b = a.old_budget, a.new_budget

        if action in (Action.HOLD, Action.REFRESH_CREATIVE):
            tbl.add_row(plat, a.metrics.label, verb, "—", "[bright_black]no write[/bright_black]")
            continue

        change = "→ $0/day" if action is Action.PAUSE else f"${old_b:,.0f} → ${new_b:,.0f}/day"
        req = WriteRequest(
            platform=plat, campaign_id=a.metrics.campaign_id, label=a.metrics.label,
            action=verb, old_budget=old_b, new_budget=new_b, change_display=change,
        )
        result = _execute_write(
            req, caps=caps, mode_enum=mode_enum, send_live=send_live,
            yes=yes, level=level,
            confirm_prompt=f"  apply {verb}  {a.metrics.label}  {change} ?",
        )
        if result.status == "applied":
            n_applied += 1
        if result.audit_file is not None:
            audit_file = result.audit_file
        detail = f" — {result.detail}" if result.detail else ""
        tbl.add_row(plat, a.metrics.label, verb, change,
                    f"[{result.colour}]{result.status}[/{result.colour}]{detail}")

    console.print(tbl)
    if audit_file is not None:
        console.print(f"\naudit trail → [bright_black]{audit_file}[/bright_black]")
    if mode_enum is RunMode.SHADOW:
        console.print("[yellow]shadow mode — nothing sent. Use --mode copilot to apply.[/yellow]")
    elif n_applied:
        console.print(f"[green]{n_applied} change(s) applied.[/green]")
    else:
        console.print("[yellow]nothing applied — set each platform's token + --mode copilot to go live.[/yellow]")


@main.command()
@click.option("--once", is_flag=True, help="Run a single cycle and exit (default loops).")
@click.option("--interval", type=int, default=30, help="Minutes between cycles in continuous mode.")
@click.option("--mode", type=click.Choice([m.value for m in RunMode]), default=None,
              help="Override DRIP_MODE. `watch` defaults to copilot.")
@click.option("--level", type=click.Choice(["campaign", "adset"]), default="campaign")
@click.option("--cpa-target", type=float, default=25.0, help="Acceptable cost-per-action ceiling.")
@click.option("--dry-run", is_flag=True, help="Plan throttles/pauses, never call the write API.")
@click.option("--yes", is_flag=True, help="Skip per-write prompts (autonomous-style; still capped).")
def watch(once: bool, interval: int, mode: str | None, level: str,
          cpa_target: float, dry_run: bool, yes: bool) -> None:
    """Intraday spend-side guard — pacing / cost-spike / anti-overspend, every N min.

    The hourly layer above `drip apply` (which is daily / ROI). Pulls within-day
    metrics, runs the spend-side rules (throttle / pause / small raise), and writes
    through the same gated, audited path. ROI is never optimised here — that stays
    daily. Offline it uses a sample intraday series; plug a token + hourly data to
    go live. shadow by default.
    """
    import time

    from rich.table import Table

    from drip.engine.intraday import (
        IntradayAction,
        decide_intraday,
        evaluate_intraday,
        sample_intraday,
    )

    mode_enum = _resolve_mode(mode, "copilot")
    caps = safety.Caps.from_env()
    send_live = mode_enum is not RunMode.SHADOW and not dry_run
    verb_map = {IntradayAction.THROTTLE: "REDUCE", IntradayAction.RAISE: "SCALE",
                IntradayAction.PAUSE: "PAUSE"}

    console.print(Panel.fit(
        f"watch · mode=[yellow]{mode_enum.value}[/yellow] · cpa-target=${cpa_target:,.0f} · "
        f"dry-run={dry_run} · writes route per-platform (shadow without that platform's token)",
        title="drip watch", border_style="bright_black",
    ))

    def cycle() -> None:
        metrics = sample_intraday(cpa_target)
        tbl = Table(border_style="bright_black")
        for col in ("campaign", "signals", "action", "result"):
            tbl.add_column(col)
        for m in metrics:
            sig = evaluate_intraday(m)
            d = decide_intraday(sig, m)
            if d.action is IntradayAction.HOLD:
                tbl.add_row(m.label, sig.summary, "HOLD", "[bright_black]—[/bright_black]")
                continue
            verb = verb_map[d.action]
            req = WriteRequest(
                platform=m.platform, campaign_id=m.campaign_id, label=m.label,
                action=verb, old_budget=d.current_budget, new_budget=d.projected_budget,
                change_display=d.headline,
            )
            result = _execute_write(
                req, caps=caps, mode_enum=mode_enum, send_live=send_live,
                yes=yes, level=level,
                confirm_prompt=f"  {d.headline}  ({m.label}) ?",
                extra_audit_fields={"layer": "intraday"},
            )
            detail = f" — {result.detail}" if result.detail else ""
            tbl.add_row(m.label, sig.summary, d.headline,
                        f"[{result.colour}]{result.status}[/{result.colour}]{detail}")
        console.print(tbl)

    if once:
        cycle()
        return
    console.print("[bright_black]continuous mode — Ctrl-C to stop[/bright_black]")
    try:
        while True:
            cycle()
            console.print(f"[bright_black]next cycle in {interval} min …[/bright_black]")
            time.sleep(interval * 60)
    except KeyboardInterrupt:
        console.print("[red]stopped[/red]")
        sys.exit(130)


@main.command()
@click.option("--since", default=None, help="Window start YYYY-MM-DD (default: 7 days ago).")
@click.option("--until", default=None, help="Window end YYYY-MM-DD (default: today).")
@click.option("--budget", type=float, default=1000.0)
@click.option("--cpp-target", type=float, default=25.0)
@click.option("--roas-target", type=float, default=3.0)
@click.option("--mode", type=click.Choice([m.value for m in RunMode]), default=None,
              help="Override DRIP_MODE. `autopilot` defaults to copilot; --mode autonomous for hands-off.")
@click.option("--level", type=click.Choice(["campaign", "adset"]), default="campaign")
@click.option("--dry-run", is_flag=True)
@click.option("--yes", is_flag=True, help="Skip per-write prompts (autonomous-style; still capped).")
def autopilot(since: str | None, until: str | None, budget: float, cpp_target: float,
              roas_target: float, mode: str | None, level: str, dry_run: bool, yes: bool) -> None:
    """Autonomous orchestration — diagnose → route → allocate → apply → learn, end to end.

    A signal-driven supervisor classifies the situation (bleeding / scaling /
    fatigued / steady) and routes accordingly, then — in autonomous mode —
    applies within the money-safety caps behind a circuit breaker that halts the
    run on a data anomaly (most of the account wanting to pause) or on write
    failures. Deterministic + auditable; shadow by default.
    """
    from rich.table import Table

    from drip.allocator import Allocator
    from drip.collectors import Collector
    from drip.engine.rules import Action
    from drip.feedback import FeedbackLoop
    from drip.supervisor import CircuitBreaker, route

    mode_enum = _resolve_mode(mode, "copilot")
    since, until = _default_window(since, until)
    caps = safety.Caps.from_env()
    send_live = mode_enum is not RunMode.SHADOW and not dry_run
    breaker = CircuitBreaker()

    console.print(Panel.fit(
        f"autopilot · mode=[yellow]{mode_enum.value}[/yellow] · dry-run={dry_run} · "
        f"writes route per-platform (shadow without that platform's token)",
        title="drip autopilot", border_style="bright_black",
    ))

    metrics = Collector().collect(since=since, until=until)
    plan = Allocator().plan(metrics, total_budget=budget,
                            cpp_target=cpp_target, roas_target=roas_target)
    actions = [a.result.decision.action for a in plan.allocations]

    rr = route(actions)
    console.print(f"\n[bold]situation[/bold]  [yellow]{rr.situation.value}[/yellow]")
    for s in rr.steps:
        console.print(f"  → [bold]{s.step}[/bold] — [bright_black]{s.why}[/bright_black]")

    n_total = len(actions)
    n_pause = sum(1 for x in actions if x is Action.PAUSE)
    tripped, why = breaker.pre_apply(n_total, n_pause)
    if tripped:
        console.print(f"\n[red]⛔ circuit breaker — {why}[/red]")
        console.print("[yellow]nothing applied. Review the data pull, then re-run.[/yellow]")
        return

    console.print()
    tbl = Table(border_style="bright_black")
    for col in ("platform", "campaign", "action", "change", "result"):
        tbl.add_column(col)
    n_attempted = n_failed = n_applied = 0
    halted = False
    for a in plan.allocations:
        action = a.result.decision.action
        verb, plat = action.value, a.metrics.platform
        old_b, new_b = a.old_budget, a.new_budget
        if action in (Action.HOLD, Action.REFRESH_CREATIVE):
            tbl.add_row(plat, a.metrics.label, verb, "—", "[bright_black]no write[/bright_black]")
            continue
        change = "→ $0/day" if action is Action.PAUSE else f"${old_b:,.0f} → ${new_b:,.0f}/day"
        req = WriteRequest(
            platform=plat, campaign_id=a.metrics.campaign_id, label=a.metrics.label,
            action=verb, old_budget=old_b, new_budget=new_b, change_display=change,
        )
        result = _execute_write(
            req, caps=caps, mode_enum=mode_enum, send_live=send_live,
            yes=yes, level=level,
            confirm_prompt=f"  {verb}  {a.metrics.label}  {change} ?",
            extra_audit_fields={"layer": "autopilot"},
        )
        n_attempted += 1
        if result.status == "applied":
            n_applied += 1
        elif result.status == "failed":
            n_failed += 1
        detail = f" — {result.detail}" if result.detail else ""
        tbl.add_row(plat, a.metrics.label, verb, change,
                    f"[{result.colour}]{result.status}[/{result.colour}]{detail}")
        tripped, why = breaker.post_write(n_attempted, n_failed)
        if tripped:
            halted = True
            break
    console.print(tbl)
    if halted:
        console.print(f"[red]⛔ circuit breaker — {why}[/red]")

    feedback = FeedbackLoop(roas_target=roas_target).review(metrics)
    if feedback.learnings:
        console.print("\n[bold]feedback[/bold]")
        for learning in feedback.learnings:
            console.print(f"  · {learning.insight}")

    if mode_enum is RunMode.SHADOW:
        console.print("\n[yellow]shadow — planned only. --mode autonomous to run hands-off (within caps).[/yellow]")
    elif n_applied:
        console.print(f"\n[green]{n_applied} change(s) applied.[/green]")


@main.command()
def llm() -> None:
    """List supported LLM providers and how to address them."""
    from rich.table import Table

    from drip.llm import list_providers
    table = Table(title="drip · supported LLM providers", border_style="bright_black")
    table.add_column("provider")
    table.add_column("protocol")
    table.add_column("key env")
    table.add_column("notes", style="bright_black")
    for p in list_providers():
        table.add_row(p.name, p.protocol, p.key_env or "(none / local)", p.notes)
    console.print(table)
    console.print(
        "\nAddress any model as [bold]provider/model[/bold] — "
        "e.g. openai/gpt-4o, anthropic/claude-sonnet-4-6, "
        "openrouter/google/gemini-2.0-flash.\n"
        "Unknown names route via OpenRouter automatically."
    )


# Backwards-compat alias for the previous ``drip eval`` command.
@main.command(hidden=True)
@click.option("--agent", "agent_name", default="dummy")
def eval(agent_name: str) -> None:
    """Deprecated — use `drip bench run --agent <name>`."""
    console.print("[yellow]`drip eval` is deprecated; use `drip bench run`.[/yellow]")
    from drip.eval import run_bench
    run_bench(agent_name=agent_name)


if __name__ == "__main__":
    main()
