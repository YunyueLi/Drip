"""Decision card rendering — the GrowthGPT-style output, but open.

``card_text`` returns a plain-text card (works anywhere, used in bench
bundles and logs). ``print_card`` renders the same with rich when a
console is available.
"""

from __future__ import annotations

from drip.engine.rules import Decision
from drip.engine.signals import SignalVector


def card_text(
    decision: Decision,
    sv: SignalVector,
    *,
    label: str = "campaign",
    why: str = "",
) -> str:
    """Render a decision as a plain-text card."""
    lines: list[str] = []
    lines.append(f"▼ DECISION · {decision.headline}")
    lines.append(f"  Target      {label}")
    lines.append(f"  Signals     {sv.summary}")
    for s in sv.signals:
        lines.append(
            f"    {s.status.mark} {s.name:<13} {s.value_str:<12} "
            f"(target {s.target_str})  {s.note}"
        )
    lines.append(f"  Confidence  {decision.confidence.value}")
    if why:
        wrapped = _wrap(why, width=64, indent="              ")
        lines.append(f"  Why         {wrapped.lstrip()}")
    if decision.reasons:
        lines.append("  Rule chain")
        for r in decision.reasons:
            lines.append(f"    · [{r.rule_id}] {r.message}")
    if decision.guardrails:
        conds = "  OR  ".join(g.condition for g in decision.guardrails)
        lines.append(f"  Guardrails  auto-revert if {conds}")
    lines.append(f"  Next check  {decision.next_check_hours}h")
    return "\n".join(lines)


def _wrap(text: str, width: int, indent: str) -> str:
    import textwrap
    body = textwrap.fill(text.strip(), width=width,
                         subsequent_indent=indent)
    return body


def print_card(
    decision: Decision,
    sv: SignalVector,
    *,
    label: str = "campaign",
    why: str = "",
) -> None:
    """Pretty card via rich; falls back to plain text if rich is absent."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
    except ImportError:  # pragma: no cover
        print(card_text(decision, sv, label=label, why=why))
        return

    console = Console()
    colour = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}[
        decision.confidence.value
    ]

    tbl = Table(show_header=True, header_style="bright_black",
                border_style="bright_black", expand=False)
    tbl.add_column("", width=2)
    tbl.add_column("signal")
    tbl.add_column("actual", justify="right")
    tbl.add_column("target", justify="right")
    tbl.add_column("note", style="bright_black")
    smark = {"green": "[green]✓[/green]", "yellow": "[yellow]~[/yellow]",
             "red": "[red]✗[/red]"}
    for s in sv.signals:
        tbl.add_row(smark[s.status.value], s.name, s.value_str,
                    s.target_str, s.note)

    body_lines = [
        f"[bold]{decision.headline}[/bold]",
        f"signals   {sv.summary}     confidence [{colour}]{decision.confidence.value}[/{colour}]",
    ]
    if why:
        body_lines.append(f"\n[italic]{why.strip()}[/italic]")
    head = "\n".join(body_lines)

    console.print(Panel.fit(head, title=f"decision · {label}",
                            border_style="bright_black"))
    console.print(tbl)
    if decision.reasons:
        console.print("[bright_black]rule chain[/bright_black]")
        for r in decision.reasons:
            console.print(f"  [bright_black]·[/bright_black] [{r.rule_id}] {r.message}")
    if decision.guardrails:
        conds = "  OR  ".join(g.condition for g in decision.guardrails)
        console.print(f"[bright_black]guardrails[/bright_black] auto-revert if {conds}")
    console.print(f"[bright_black]next check[/bright_black] {decision.next_check_hours}h")
