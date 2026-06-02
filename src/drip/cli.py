"""drip CLI — `drip launch`, `drip demo`, `drip bench {list,show,run}`."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from drip import __version__
from drip.orchestrator import DripOrchestrator, GameSpec, RunMode

if TYPE_CHECKING:
    from drip.engine.intraday import IntradayMetrics

console = Console()


def _load_env() -> None:
    load_dotenv()


def _read_game(path: Path) -> GameSpec:
    if not path.exists():
        raise click.ClickException(f"game spec not found: {path}")
    data = yaml.safe_load(path.read_text())
    return GameSpec.model_validate(data)


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
    mode_enum = RunMode(mode) if mode else RunMode(os.getenv("DRIP_MODE", "shadow"))

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
    import datetime

    from rich.table import Table

    from drip.pipeline import Pipeline

    until = until or datetime.date.today().isoformat()
    since = since or (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

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
    import datetime

    from rich.table import Table

    from drip import safety
    from drip.adapters.writers import build_writer
    from drip.allocator import Allocator
    from drip.collectors import Collector
    from drip.engine.rules import Action

    mode_enum = RunMode(mode) if mode else RunMode(os.getenv("DRIP_MODE", "copilot"))
    until = until or datetime.date.today().isoformat()
    since = since or (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
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

    audit_file: object | None = None
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

        try:
            safety.guard_change(action=verb, old_budget=old_b, new_budget=new_b, caps=caps)
        except safety.GuardError as exc:
            tbl.add_row(plat, a.metrics.label, verb, change, f"[red]denied[/red] — {exc}")
            safety.audit({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                          "mode": mode_enum.value, "platform": plat,
                          "target_id": a.metrics.campaign_id, "action": verb,
                          "status": "denied", "detail": str(exc), "label": a.metrics.label})
            continue

        approved = True
        if send_live and mode_enum is RunMode.COPILOT and not yes:
            approved = click.confirm(f"  apply {verb}  {a.metrics.label}  {change} ?", default=False)

        r = build_writer(plat, level=level).apply_decision(
            a.metrics.campaign_id, verb, new_budget=new_b,
            dry_run=not (send_live and approved), label=a.metrics.label,
        )
        if not approved:
            r.status, r.detail = "skipped", "declined by operator"

        rec = r.to_dict()
        rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        rec["mode"] = mode_enum.value
        audit_file = safety.audit(rec)

        colour = {"applied": "green", "shadow": "bright_black", "skipped": "yellow",
                  "failed": "red", "denied": "red"}.get(r.status, "white")
        if r.status == "applied":
            n_applied += 1
        tbl.add_row(plat, a.metrics.label, verb, change, f"[{colour}]{r.status}[/{colour}]")

    console.print(tbl)
    if audit_file is not None:
        console.print(f"\naudit trail → [bright_black]{audit_file}[/bright_black]")
    if mode_enum is RunMode.SHADOW:
        console.print("[yellow]shadow mode — nothing sent. Use --mode copilot to apply.[/yellow]")
    elif n_applied:
        console.print(f"[green]{n_applied} change(s) applied.[/green]")
    else:
        console.print("[yellow]nothing applied — set each platform's token + --mode copilot to go live.[/yellow]")


def _sample_intraday(cpa_target: float) -> list[IntradayMetrics]:
    """Deterministic within-day sample so `drip watch` runs offline.

    Four campaigns mid-day, each in a different spend-side state.
    """
    from drip.engine.intraday import IntradayMetrics
    return [
        # healthy, on pace
        IntradayMetrics(campaign_id="meta-0001", daily_budget=200.0, spend_so_far=100.0,
                        day_fraction=0.5, cpa_recent=18.0, cpa_baseline=18.0, cpa_target=cpa_target,
                        conversions_recent=9, label="Meta_Prospecting_v3"),
        # cost spiking over the ceiling → throttle/pause
        IntradayMetrics(campaign_id="meta-0002", daily_budget=240.0, spend_so_far=150.0,
                        day_fraction=0.5, cpa_recent=44.0, cpa_baseline=26.0, cpa_target=cpa_target,
                        conversions_recent=7, label="Meta_Broad_v1"),
        # burning budget too early while cost is soft → gentle trim
        IntradayMetrics(campaign_id="meta-0003", daily_budget=180.0, spend_so_far=150.0,
                        day_fraction=0.5, cpa_recent=27.0, cpa_baseline=26.0, cpa_target=cpa_target,
                        conversions_recent=8, label="Meta_Lookalike_v2"),
        # underpacing a healthy line → small raise
        IntradayMetrics(campaign_id="meta-0004", daily_budget=160.0, spend_so_far=40.0,
                        day_fraction=0.5, cpa_recent=15.0, cpa_baseline=16.0, cpa_target=cpa_target,
                        conversions_recent=10, label="Meta_Retarget_v4"),
    ]


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
    import datetime
    import time

    from rich.table import Table

    from drip import safety
    from drip.adapters.writers import build_writer
    from drip.engine.intraday import IntradayAction, decide_intraday, evaluate_intraday

    mode_enum = RunMode(mode) if mode else RunMode(os.getenv("DRIP_MODE", "copilot"))
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
        metrics = _sample_intraday(cpa_target)
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
            try:
                safety.guard_change(action=verb, old_budget=d.current_budget,
                                    new_budget=d.projected_budget, caps=caps)
            except safety.GuardError as exc:
                tbl.add_row(m.label, sig.summary, d.headline, f"[red]denied[/red] — {exc}")
                continue
            approved = True
            if send_live and mode_enum is RunMode.COPILOT and not yes:
                approved = click.confirm(f"  {d.headline}  ({m.label}) ?", default=False)
            r = build_writer(m.platform, level=level).apply_decision(
                m.campaign_id, verb, new_budget=d.projected_budget,
                dry_run=not (send_live and approved), label=m.label,
            )
            if not approved:
                r.status, r.detail = "skipped", "declined by operator"
            rec = r.to_dict()
            rec["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
            rec["mode"], rec["layer"] = mode_enum.value, "intraday"
            safety.audit(rec)
            colour = {"applied": "green", "shadow": "bright_black", "skipped": "yellow",
                      "failed": "red"}.get(r.status, "white")
            tbl.add_row(m.label, sig.summary, d.headline, f"[{colour}]{r.status}[/{colour}]")
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
