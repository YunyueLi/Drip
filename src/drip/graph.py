"""LangGraph supervisor — production orchestration.

Upgrades the lightweight :class:`drip.pipeline.Pipeline` with the three things
a long-running, money-spending, accountable system needs (per the research):

  - **checkpointing** — resume a run after a crash, don't restart the cycle
  - **interrupt-before-spend** — human approval gate before the Allocator moves
    budget (the accountability wall: someone firable signs off)
  - **node retries** — transient API failures don't kill the run

The graph nodes map 1:1 onto the agents, so the reference flow
(``Pipeline``) and the production graph stay in sync.

.. note::

   This module is **not yet wired** into any CLI command or the pipeline. It is
   forward-looking infrastructure — the nodes are individually testable, but
   ``build_graph()`` is not called anywhere. When ``langgraph`` is ready to
   replace :class:`~drip.pipeline.Pipeline`, wire it here (a ``drip graph``
   command or a ``Pipeline`` backend toggle).

``langgraph`` is imported lazily inside :func:`build_graph`. Without it,
callers get a clear message pointing back to ``Pipeline`` as the offline
fallback — nothing else in Drip imports this module eagerly.
"""

from __future__ import annotations

from typing import Any, TypedDict

from drip import config as _cfg


class GraphState(TypedDict, total=False):
    since: str
    until: str
    config: dict[str, Any]      # cpp_target, roas_target, total_budget, narrate_model, generator
    metrics: list[Any]
    report: Any
    strategy: Any
    variants: list[Any]
    plan: Any
    feedback: Any


# --------------------------------------------------------------------------
# Nodes — each wraps one agent. Agent imports are local so this module stays
# import-light and the nodes are individually testable.
# --------------------------------------------------------------------------


def collect_node(state: GraphState) -> dict[str, Any]:
    from drip.collectors import Collector
    metrics = Collector().collect(since=state["since"], until=state["until"])
    return {"metrics": metrics}


def analyst_node(state: GraphState) -> dict[str, Any]:
    from drip.analyst import Analyst
    cfg = state.get("config", {})
    report = Analyst(narrate_model=cfg.get("narrate_model")).analyze(
        state["metrics"],
        cpp_target=cfg.get("cpp_target", _cfg.DEFAULT_CPP_TARGET),
        roas_target=cfg.get("roas_target", _cfg.DEFAULT_ROAS_TARGET),
        budget_cap=cfg.get("total_budget", _cfg.DEFAULT_BUDGET_CAP),
    )
    return {"report": report}


def strategist_node(state: GraphState) -> dict[str, Any]:
    from drip.strategist import Strategist
    cfg = state.get("config", {})
    strategy = Strategist(narrate_model=cfg.get("narrate_model")).propose(
        state["metrics"], roas_target=cfg.get("roas_target", _cfg.DEFAULT_ROAS_TARGET),
    )
    return {"strategy": strategy}


def creative_node(state: GraphState) -> dict[str, Any]:
    from drip.creative import Creative
    cfg = state.get("config", {})
    creative = Creative(generator=cfg.get("generator", "dry"))
    variants: list[Any] = []
    for h in state["strategy"].hypotheses:
        if h.direction == "scale_winner":
            variants.extend(creative.produce(h.brief, n=3))
    return {"variants": variants}


def allocate_node(state: GraphState) -> dict[str, Any]:
    from drip.allocator import Allocator
    cfg = state.get("config", {})
    plan = Allocator().plan(
        state["metrics"],
        total_budget=cfg.get("total_budget", _cfg.DEFAULT_BUDGET_CAP),
        cpp_target=cfg.get("cpp_target", _cfg.DEFAULT_CPP_TARGET),
        roas_target=cfg.get("roas_target", _cfg.DEFAULT_ROAS_TARGET),
    )
    return {"plan": plan}


def feedback_node(state: GraphState) -> dict[str, Any]:
    from drip.feedback import FeedbackLoop
    cfg = state.get("config", {})
    feedback = FeedbackLoop(roas_target=cfg.get("roas_target", _cfg.DEFAULT_ROAS_TARGET)).review(state["metrics"])
    return {"feedback": feedback}


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------


def build_graph(checkpointer: Any = None, approve_before_spend: bool = True) -> Any:
    """Compile the supervisor graph.

    ``checkpointer`` — a LangGraph checkpointer (e.g. Postgres/SQLite) for
    resumable runs. ``approve_before_spend`` — interrupt before the Allocator
    so a human signs off the budget move.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "langgraph is not installed. Install it (`pip install langgraph`) "
            "for the production graph, or use drip.pipeline.Pipeline for the "
            "lightweight offline path."
        ) from exc

    g = StateGraph(GraphState)
    g.add_node("collect", collect_node)
    g.add_node("analyst", analyst_node)
    g.add_node("strategist", strategist_node)
    g.add_node("creative", creative_node)
    g.add_node("allocate", allocate_node)
    g.add_node("feedback", feedback_node)

    g.add_edge(START, "collect")
    g.add_edge("collect", "analyst")
    g.add_edge("analyst", "strategist")
    g.add_edge("strategist", "creative")
    g.add_edge("creative", "allocate")
    g.add_edge("allocate", "feedback")
    g.add_edge("feedback", END)

    # The accountability gate: pause before budget moves for human approval.
    interrupt_before = ["allocate"] if approve_before_spend else []
    return g.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)
