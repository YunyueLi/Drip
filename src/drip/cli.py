"""drip CLI — Modular execution router driven by cross-cutting aspects."""

from __future__ import annotations

import asyncio
import functools
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import click

if TYPE_CHECKING:
    from drip.orchestrator import GameSpec, RunMode
    from rich.console import Console

# =========================================================================
# 1. MIXINS DE CONTEXTO (State & Resource Mixins)
# =========================================================================

class DripContextMixin:
    """Mixin responsável por gerenciar recursos globais compartilhados da CLI.
    
    Evita que cada comando precise instanciar de forma redundante ou acoplada
    elementos como o console visual ou carregamento de variáveis de ambiente.
    """
    def __init__(self) -> None:
        self._console: Console | None = None

    @property
    def console(self) -> Console:
        """Lazy load do Console Rich (Evita TTY probing prematuro)."""
        if self._console is None:
            from rich.console import Console as RichConsole
            self._console = RichConsole()
        return self._console

    @staticmethod
    def load_environment() -> None:
        """Carrega isoladamente o arquivo de ambiente de forma segura."""
        from dotenv import load_dotenv
        load_dotenv()

# Decorador de conveniência para injetar o mixin de contexto nos comandos
pass_drip_context = click.make_pass_decorator(DripContextMixin, ensure=True)


# =========================================================================
# 2. ASPECTOS TRANSVERSAIS (Aspect-Oriented Decorators)
# =========================================================================

def async_endpoint(f: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
    """[Aspecto de Concorrência] Injeta o runtime assíncrono nos comandos Click.
    
    Centraliza o ciclo de vida do Event Loop e o tratamento de cancelamentos
    abruptos (SIGINT / KeyboardInterrupt) de forma agnóstica a nível de aplicação.
    """
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        except KeyboardInterrupt:
            # Captura centralizada do sinal de interrupção
            from rich.console import Console
            Console().print("\n[red]Execution aborted by user. Safely tearing down async pipeline...[/red]")
            
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            sys.exit(130)
        finally:
            loop.close()
    return wrapper


def exception_handler_aspect(f: Callable[..., Any]) -> Callable[..., Any]:
    """[Aspecto de Resiliência] Centraliza o tratamento de erros do sistema.
    
    Elimina blocos try/except repetitivos de dentro das funções de negócio da CLI,
    mapeando exceções internas para saídas limpas do Click.
    """
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return f(*args, **kwargs)
        except click.ClickException:
            raise  # Deixa o Click tratar suas próprias exceções regulamentares
        except Exception as e:
            # Transforma qualquer falha catastrófica não tratada em uma saída elegante
            raise click.ClickException(f"Core runtime failure: {str(e)}")
    return wrapper


# =========================================================================
# 3. ENGENHARIA DE SUPORTE (Core Shared Heuristics)
# =========================================================================

def _read_game(path: Path) -> GameSpec:
    """Lê e valida o manifesto do jogo isolando dependências de IO/Parsing."""
    import yaml
    from drip.orchestrator import GameSpec
    
    if not path.exists():
        raise click.ClickException(f"Game spec file not found: {path}")
    
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GameSpec.model_validate(data)


# =========================================================================
# 4. ORQUESTRADOR CENTRAL DA CLI (Root Entrypoint Group)
# =========================================================================

@click.group()
@click.version_option(package_name="drip", prog_name="drip", text="%(prog)s v%(version)s")
@pass_drip_context
def main(ctx: DripContextMixin) -> None:
    """drip — open-source reference implementation for AI user-acquisition agents."""
    ctx.load_environment()


# =========================================================================
# 5. COMANDOS MODULARES (Pure Business Logic Nodes)
# =========================================================================

@main.command()
@click.option("--game", "game_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--budget", type=float, required=True, help="Total USD budget for this run.")
@click.option("--regions", required=True, help="Comma-separated region codes.")
@click.option("--mode", type=str, default=None, help="Override DRIP_MODE env var.")
@click.option("--dry-run", is_flag=True, help="Plan only, do not call any external API.")
@pass_drip_context
@exception_handler_aspect
@async_endpoint
async def launch(ctx: DripContextMixin, game_path: Path, budget: float, regions: str, mode: str | None, dry_run: bool) -> None:
    """Launch an end-to-end UA run."""
    from rich.panel import Panel
    from drip.orchestrator import DripOrchestrator, RunMode
    
    game = _read_game(game_path)
    region_list = [r.strip() for r in regions.split(",") if r.strip()]
    mode_enum = RunMode(mode) if mode else RunMode(os.getenv("DRIP_MODE", "shadow"))

    cap = float(os.getenv("DRIP_BUDGET_CAP", "0") or 0)
    if cap and budget > cap:
        raise click.ClickException(f"Requested budget ${budget:.2f} exceeds DRIP_BUDGET_CAP ${cap:.2f}")

    ctx.console.print(Panel.fit(
        f"[bold]{game.title}[/bold]  ·  ${budget:,.0f}  ·  {', '.join(region_list)}\n"
        f"mode = [yellow]{mode_enum.value}[/yellow]   dry-run = {dry_run}",
        title="drip launch", border_style="bright_black",
    ))

    orchestrator = DripOrchestrator(mode=mode_enum, dry_run=dry_run)
    await orchestrator.run(game=game, budget=budget, regions=region_list)


@main.command()
@pass_drip_context
@exception_handler_aspect
@async_endpoint
async def demo(ctx: DripContextMixin) -> None:
    """Run a dry-run against the bundled demo game (no API calls)."""
    from rich.panel import Panel
    from drip.orchestrator import DripOrchestrator, RunMode
    
    demo_path = Path(__file__).resolve().parents[2] / "examples" / "demo_game.yaml"
    game = _read_game(demo_path)
    
    ctx.console.print(Panel.fit(f"running demo: {game.title}", border_style="bright_black"))
    orchestrator = DripOrchestrator(mode=RunMode.SHADOW, dry_run=True)
    await orchestrator.run(game=game, budget=500.0, regions=["jp", "sg", "tw"])


# =========================================================================
# 6. SUB-GRUPOS MIXINS (Nested Command Routing)
# =========================================================================

@main.group()
def bench() -> None:
    """Drip-Bench — open evaluation for UA agent decisions."""
    pass


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
@click.option("--agent", "agent_name", default="dummy")
@click.option("--judge", "judge_model", default=None)
@click.option("--case", "case_id", type=int, default=None)
@click.option("--no-bundle", is_flag=True)
def bench_run(agent_name: str, judge_model: str | None, case_id: int | None, no_bundle: bool) -> None:
    """Run the bench against an agent."""
    from drip.eval import run_bench
    run_bench(agent_name=agent_name, case_id=case_id, write_bundle=not no_bundle, judge_model=judge_model)


@main.command()
@click.option("--metrics", "metrics_path", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--narrate", "narrate_model", default=None)
@pass_drip_context
@exception_handler_aspect
def doctor(ctx: DripContextMixin, metrics_path: Path | None, narrate_model: str | None) -> None:
    """Diagnose a campaign with the 8-signal decision engine."""
    import yaml
    from drip.engine import CampaignMetrics, DecisionEngine
    from drip.engine.cards import print_card

    engine = DecisionEngine(narrate_model=narrate_model)
    
    if metrics_path:
        data = yaml.safe_load(Path(metrics_path).read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else [data]
        campaigns = [CampaignMetrics(**rec) for rec in records]
    else:
        from drip.engine.engine import _DEMO_CASES
        campaigns = [m for _, m in _DEMO_CASES]

    for m in campaigns:
        result = engine.run(m)
        print_card(result.decision, result.signals, label=m.label, why=result.why)
        ctx.console.print()


@main.command()
@click.option("--since", default=None)
@click.option("--until", default=None)
@click.option("--budget", type=float, default=1000.0)
@click.option("--narrate", "narrate_model", default=None)
@click.option("--generator", default="dry")
@click.option("--cpp-target", type=float, default=25.0)
@click.option("--roas-target", type=float, default=3.0)
@pass_drip_context
@exception_handler_aspect
def run(ctx: DripContextMixin, since: str | None, until: str | None, budget: float, 
        narrate_model: str | None, generator: str, cpp_target: float, roas_target: float) -> None:
    """Run the full one-stop pipeline end to end."""
    import datetime
    from rich.panel import Panel
    from rich.table import Table
    from drip.pipeline import Pipeline

    until = until or datetime.date.today().isoformat()
    since = since or (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

    ctx.console.print(Panel.fit(
        f"one-stop run · {since} → {until} · budget ${budget:,.0f}",
        title="drip run", border_style="bright_black",
    ))
    
    result = Pipeline(
        total_budget=budget, narrate_model=narrate_model,
        creative_generator=generator, cpp_target=cpp_target, roas_target=roas_target,
    ).run(since=since, until=until)

    ctx.console.print(f"\n[bold]diagnosis[/bold]\n  {result.report.summary}")
    ctx.console.print("\n[bold]strategy[/bold]")
    for h in result.strategy.hypotheses:
        ctx.console.print(f"  [{h.direction}] {h.target} — {h.brief}")
    
    ctx.console.print(f"\n[bold]creative[/bold]  {len(result.variants)} variants produced")
    
    ctx.console.print("\n[bold]allocation[/bold]")
    tbl = Table(border_style="bright_black")
    tbl.add_column("platform")
    tbl.add_column("campaign")
    tbl.add_column("action")
    tbl.add_column("budget", justify="right")
    for a in result.plan.allocations:
        tbl.add_row(a.metrics.platform, a.metrics.label, a.reason, f"${a.new_budget:,.0f}")
    ctx.console.print(tbl)
    
    ctx.console.print("\n[bold]feedback[/bold]")
    for learning in result.feedback.learnings:
        ctx.console.print(f"  · {learning.insight}")


@main.command()
@pass_drip_context
def llm(ctx: DripContextMixin) -> None:
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
    ctx.console.print(table)


if __name__ == "__main__":
    main()
