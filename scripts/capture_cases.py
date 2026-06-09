"""Capture REAL Drip runs (with a live LLM) into replayable case recordings.

Each scenario is executed through the actual Drip pipeline/engine — no mock
data — and serialized to cases/<id>.json. build_real_cases.py then turns these
into web/real-cases.js, which app.html replays step-by-step in the console.

Usage:
    .venv/bin/python scripts/capture_cases.py --model deepseek/deepseek-v4-pro
    .venv/bin/python scripts/capture_cases.py --only cross-platform-triage
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from drip.allocator import Allocator
from drip.analyst import Analyst
from drip.collectors import Collector
from drip.creative import Creative
from drip.engine import DecisionEngine
from drip.engine.intraday import decide_intraday, evaluate_intraday, sample_intraday
from drip.engine.rules import Action
from drip.feedback import FeedbackLoop
from drip.strategist import Strategist
from drip.supervisor import CircuitBreaker, route

OUT = Path(__file__).resolve().parents[1] / "cases"
_STATUS = {"green": "g", "yellow": "y", "red": "r"}
CPP_T, ROAS_T, BUDGET = 25.0, 3.0, 1400.0
SINCE, UNTIL = "2026-05-21", "2026-05-28"


def _card(label: str, em, result) -> dict:
    sv, d = result.signals, result.decision
    return {
        "label": label,
        "action": d.action.value,
        "delta": round(d.delta_pct, 2),
        "confidence": d.confidence.value,
        "green": sv.green,
        "total": sv.total,
        "signals": [
            {"name": s.name, "status": _STATUS[s.status.value], "value": s.value_str,
             "target": s.target_str, "note": s.note}
            for s in sv.signals
        ],
        "reasons": [r.message for r in d.reasons],
        "why": result.why,  # real LLM narration
    }


def cross_platform_triage(model: str) -> dict:
    """drip run — full loop: collect → diagnose → strategize → create → allocate → learn."""
    metrics = Collector().collect(since=SINCE, until=UNTIL)
    engine = DecisionEngine(narrate_model=model)
    cards = []
    for m in metrics:
        em = m.to_engine_metrics(cpp_target=CPP_T, roas_target=ROAS_T, budget_cap=BUDGET)
        cards.append(_card(m.label, em, engine.run(em)))

    report = Analyst(narrate_model=model).analyze(
        metrics, cpp_target=CPP_T, roas_target=ROAS_T, budget_cap=BUDGET)
    strategy = Strategist(narrate_model=model).propose(metrics, roas_target=ROAS_T)
    creative = Creative(generator="dry")
    variants = []
    for h in strategy.hypotheses:
        if h.direction == "scale_winner":
            variants.extend(creative.produce(h.brief, n=3))
    plan = Allocator().plan(metrics, total_budget=BUDGET, cpp_target=CPP_T, roas_target=ROAS_T)
    feedback = FeedbackLoop(roas_target=ROAS_T).review(metrics)

    n_scale = sum(1 for c in cards if c["action"] == "SCALE")
    n_pause = sum(1 for c in cards if c["action"] == "PAUSE")
    return {
        "id": "cross-platform-triage",
        "title": "跨平台体检与预算重分配",
        "subtitle": f"{len(metrics)} campaigns · Meta / TikTok / 腾讯 / 巨量 / 快手",
        "model": model,
        "prompt": "我有跨 Meta/TikTok/腾讯/巨量/快手的多条 campaign，今天预算 $1,400，"
                  "帮我体检一遍、决定每条该放量还是止损、并把预算重新分配到赢家。",
        "steps": [
            {"agent": "collect", "title": "采集", "icon": "database",
             "summary": f"从 5 个平台拉取 {len(metrics)} 条 campaign，归一到 AdMetrics。",
             "platforms": sorted({m.platform for m in metrics})},
            {"agent": "diagnose", "title": "诊断", "icon": "stethoscope",
             "summary": report.summary, "cards": cards},
            {"agent": "strategize", "title": "策略", "icon": "target",
             "summary": "排出赢家方向，给出下一个创意测试。",
             "hypotheses": [{"direction": h.direction, "target": h.target, "brief": h.brief}
                            for h in strategy.hypotheses]},
            {"agent": "create", "title": "创意", "icon": "spark",
             "summary": f"为赢家方向产出 {len(variants)} 个变体。",
             "variants": [{"id": v.variant_id, "kind": v.asset_kind, "ref": v.asset_ref} for v in variants]},
            {"agent": "allocate", "title": "分配", "icon": "split",
             "summary": f"在 ${BUDGET:,.0f} 总预算内重分：{n_scale} 放量 / {n_pause} 止损。",
             "rows": [{"platform": a.metrics.platform, "campaign": a.metrics.label,
                       "action": a.result.decision.action.value,
                       "old": round(a.old_budget, 0), "new": round(a.new_budget, 0)}
                      for a in plan.allocations]},
            {"agent": "learn", "title": "反馈", "icon": "refresh",
             "summary": "萃取赢点，回灌下一轮。",
             "learnings": [lr.insight for lr in feedback.learnings]},
        ],
    }


def intraday_guard(model: str) -> dict:
    """drip watch — intraday spend-side guard."""
    rows = []
    verb = {"throttle": "REDUCE", "raise": "SCALE", "pause": "PAUSE", "hold": "HOLD"}
    for m in sample_intraday(CPP_T):
        sig = evaluate_intraday(m)
        d = decide_intraday(sig, m)
        rows.append({"campaign": m.label, "platform": m.platform, "signals": sig.summary,
                     "action": verb.get(d.action.value, d.action.value), "headline": d.headline})
    acted = [r for r in rows if r["action"] != "HOLD"]
    return {
        "id": "intraday-guard",
        "title": "盘中超支止血",
        "subtitle": "小时级 · pacing / 成本突刺 / 防超投",
        "model": model,
        "prompt": "盘中帮我盯着花费侧：哪条 pacing 过快、成本突刺或要超投了，"
                  "在预算失控前限速或暂停。",
        "steps": [
            {"agent": "collect", "title": "拉取盘中数据", "icon": "database",
             "summary": f"拉取 {len(rows)} 条 campaign 的小时级花费/成本序列。"},
            {"agent": "watch", "title": "盘中信号 + 决策", "icon": "gauge",
             "summary": f"{len(acted)} 条触发限速/暂停，其余 HOLD。", "rows": rows},
        ],
    }


def autopilot_run(model: str) -> dict:
    """drip autopilot — signal-routed supervisor + circuit breaker (shadow writes)."""
    metrics = Collector().collect(since=SINCE, until=UNTIL)
    plan = Allocator().plan(metrics, total_budget=BUDGET, cpp_target=CPP_T, roas_target=ROAS_T)
    actions = [a.result.decision.action for a in plan.allocations]
    rr = route(actions)
    breaker = CircuitBreaker()
    n_total = len(actions)
    n_pause = sum(1 for x in actions if x is Action.PAUSE)
    tripped, why = breaker.pre_apply(n_total, n_pause)
    feedback = FeedbackLoop(roas_target=ROAS_T).review(metrics)
    return {
        "id": "autopilot",
        "title": "自主托管一轮",
        "subtitle": "信号路由 + 熔断器 · 确定性可审计",
        "model": model,
        "prompt": "按信号自主跑一轮：先止血、再放量/换创意/分配，"
                  "全程有熔断器，数据异常就停手。shadow 模式先不真写。",
        "steps": [
            {"agent": "route", "title": "局面分类与路由", "icon": "route",
             "summary": f"局面：{rr.situation.value}。",
             "plan": [{"step": s.step, "why": s.why} for s in rr.steps]},
            {"agent": "breaker", "title": "熔断器预检", "icon": "shield",
             "summary": (f"⛔ {why}" if tripped else f"通过：{n_pause}/{n_total} 暂停，未触发异常阈值。"),
             "tripped": tripped},
            {"agent": "apply", "title": "写入（shadow）", "icon": "send",
             "summary": "shadow 模式：规划每笔 scale/pause/预算，落审计，不真写。",
             "rows": [{"platform": a.metrics.platform, "campaign": a.metrics.label,
                       "action": a.result.decision.action.value,
                       "new": round(a.new_budget, 0)} for a in plan.allocations]},
            {"agent": "learn", "title": "反馈", "icon": "refresh",
             "summary": "萃取赢点。", "learnings": [lr.insight for lr in feedback.learnings]},
        ],
    }


SCENARIOS = {
    "cross-platform-triage": cross_platform_triage,
    "intraday-guard": intraday_guard,
    "autopilot": autopilot_run,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--only", default=None, help="capture a single scenario id")
    args = ap.parse_args()
    load_dotenv()
    OUT.mkdir(parents=True, exist_ok=True)

    ids = [args.only] if args.only else list(SCENARIOS)
    index = []
    for cid in ids:
        print(f"▸ capturing {cid} (model={args.model}) …")
        rec = SCENARIOS[cid](args.model)
        (OUT / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"id": rec["id"], "title": rec["title"],
                      "subtitle": rec["subtitle"], "steps": len(rec["steps"])})
        print(f"  ✓ {cid}.json  ({len(rec['steps'])} steps)")

    if not args.only:
        (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ index.json  ({len(index)} cases)")


if __name__ == "__main__":
    main()
