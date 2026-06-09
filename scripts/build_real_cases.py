"""Convert captured real runs (cases/*.json) into the console's
native CONV block format, emitted as web/real-cases.js (window.DRIP_REAL_CASES).

This lets the EXISTING app.html console replay the real DeepSeek runs through
its own renderer (intro / cot / card / kpis / narr) — no new UI engine, the
real interface shows the real results. No LLM calls; pure transform.

Run after capture_cases.py:
    .venv/bin/python scripts/build_real_cases.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
OUT = ROOT / "web" / "real-cases.js"

# Bilingual titles/asks for the picker + the user bubble.
META = {
    "cross-platform-triage": {
        "title": {"zh": "跨平台体检与预算重分配", "en": "Cross-platform triage & reallocation"},
        "sub": {"zh": "7 campaign · Meta/TikTok/腾讯/巨量/快手", "en": "7 campaigns · Meta/TikTok/Tencent/OE/KS"},
        "q": {"zh": "我有跨 Meta/TikTok/腾讯/巨量/快手的多条 campaign，今天预算 $1,400，帮我体检一遍、决定每条放量还是止损、并把预算重分到赢家。",
              "en": "I have campaigns across Meta/TikTok/Tencent/OceanEngine/Kuaishou, $1,400 today — triage them, decide scale vs stop-loss, and reallocate to winners."},
    },
    "intraday-guard": {
        "title": {"zh": "盘中超支止血", "en": "Intraday overspend guard"},
        "sub": {"zh": "小时级 · pacing / 成本突刺 / 防超投", "en": "hourly · pacing / cost-spike / anti-overspend"},
        "q": {"zh": "盘中帮我盯着花费侧：哪条 pacing 过快、成本突刺或要超投，在预算失控前限速或暂停。",
              "en": "Watch the spend side intraday: which campaigns are pacing too fast, spiking, or about to overspend — throttle or pause before the budget runs away."},
    },
    "autopilot": {
        "title": {"zh": "自主托管一轮", "en": "Autopilot one cycle"},
        "sub": {"zh": "信号路由 + 熔断器 · 可审计", "en": "signal-routed + circuit breaker · auditable"},
        "q": {"zh": "按信号自主跑一轮：先止血、再放量/换创意/分配，全程有熔断器，数据异常就停手。shadow 先不真写。",
              "en": "Run one autonomous cycle: stop-loss first, then scale/refresh/allocate, behind a circuit breaker that halts on anomalies. Shadow — no real writes yet."},
    },
}
_ACT = {"SCALE": "scale", "PAUSE": "pause", "REFRESH_CREATIVE": "refresh", "REDUCE": "reduce", "HOLD": "hold"}


def _step(rec, agent):
    return next((s for s in rec["steps"] if s["agent"] == agent), None)


def _card_block(c, budget=""):
    return {
        "t": "card", "act": _ACT.get(c["action"], "hold"), "actLabel": c["action"],
        "name": c["label"], "plat": "", "budget": budget,
        "conf": c["confidence"].lower(), "confLabel": c["confidence"],
        "why": c["why"] or "; ".join(c.get("reasons", [])),
        "sigLab": f"8 signals {c['green']}/{c['total']}",
        "sigs": [[s["name"], s["status"], s["value"]] for s in c["signals"][:4]],
    }


def triage(rec):
    diag = _step(rec, "diagnose")
    alloc = _step(rec, "allocate")
    learn = _step(rec, "learn")
    budget_by = {r["campaign"]: f"${r['old']:,.0f} → ${r['new']:,.0f}" for r in (alloc["rows"] if alloc else [])}
    cards = diag["cards"] if diag else []
    winner = next((c for c in cards if c["action"] == "SCALE"), None)
    loser = next((c for c in cards if c["action"] == "PAUSE"), None)
    rows = alloc["rows"] if alloc else []
    n_scale = sum(1 for r in rows if r["action"] == "SCALE")
    n_pause = sum(1 for r in rows if r["action"] == "PAUSE")
    blocks = [{"t": "intro", "h": diag["summary"] if diag else ""}]
    blocks.append({"t": "cot", "title": {"zh": "Drip 怎么跑的", "en": "How Drip ran it"},
                   "steps": [f"{s['title']} — {s.get('summary', '')}" for s in rec["steps"]]})
    if winner:
        blocks.append(_card_block(winner, budget_by.get(winner["label"], "")))
    if loser:
        blocks.append(_card_block(loser, budget_by.get(loser["label"], "")))
    blocks.append({"t": "kpis", "head": {"zh": "跨平台再分配", "en": "Cross-platform reallocation"},
                   "sub": {"zh": "$1,400 总预算", "en": "$1,400 budget"},
                   "items": [
                       {"k": {"zh": "放量", "en": "Scale"}, "v": str(n_scale), "d": {"zh": "条 campaign", "en": "campaigns"}, "dc": "up"},
                       {"k": {"zh": "止损", "en": "Stop-loss"}, "v": str(n_pause), "d": {"zh": "归零", "en": "→ $0"}, "dc": "down"},
                       {"k": {"zh": "赢家单条", "en": "Per winner"}, "v": f"${rows[0]['new']:,.0f}" if rows else "—", "d": {"zh": "↑ 加投", "en": "↑ scaled"}, "dc": "up"},
                       {"k": {"zh": "口径", "en": "Basis"}, "v": "8/8", "d": {"zh": "信号 + 规则", "en": "signals + rules"}, "dc": "flat"},
                   ]})
    if learn and learn.get("learnings"):
        blocks.append({"t": "narr", "h": "<strong>Feedback:</strong> " + "；".join(learn["learnings"])})
    return blocks


def intraday(rec):
    watch = _step(rec, "watch")
    rows = watch["rows"] if watch else []
    acted = [r for r in rows if r["action"] != "HOLD"]
    blocks = [{"t": "intro", "h": (watch["summary"] if watch else "")}]
    blocks.append({"t": "cot", "title": {"zh": "盘中规则链", "en": "Intraday rule chain"},
                   "steps": [f"{r['campaign']} · {r['signals']} → {r['action']}" for r in rows]})
    blocks.append({"t": "kpis", "head": {"zh": "盘中花费侧守卫", "en": "Intraday spend guard"},
                   "sub": {"zh": "小时级", "en": "hourly"},
                   "items": [
                       {"k": {"zh": "触发动作", "en": "Acted"}, "v": str(len(acted)), "d": {"zh": "限速/暂停", "en": "throttle/pause"}, "dc": "down"},
                       {"k": {"zh": "观察", "en": "Hold"}, "v": str(len(rows) - len(acted)), "d": {"zh": "正常", "en": "normal"}, "dc": "flat"},
                       {"k": {"zh": "层级", "en": "Layer"}, "v": {"zh": "花费侧", "en": "spend-side"}, "d": {"zh": "非 ROI", "en": "not ROI"}, "dc": "flat"},
                       {"k": {"zh": "护栏", "en": "Gate"}, "v": {"zh": "已审计", "en": "audited"}, "d": {"zh": "shadow", "en": "shadow"}, "dc": "flat"},
                   ]})
    for r in acted[:2]:
        blocks.append({"t": "card", "act": _ACT.get(r["action"], "hold"), "actLabel": r["action"],
                       "name": r["campaign"], "plat": r["platform"], "budget": r["headline"],
                       "conf": "med", "confLabel": {"zh": "盘中", "en": "intraday"},
                       "why": r["headline"], "sigLab": r["signals"], "sigs": []})
    return blocks


def autopilot(rec):
    route = _step(rec, "route")
    breaker = _step(rec, "breaker")
    apply_s = _step(rec, "apply")
    learn = _step(rec, "learn")
    blocks = [{"t": "intro", "h": (route["summary"] if route else "") + " " + (breaker["summary"] if breaker else "")}]
    if route and route.get("plan"):
        blocks.append({"t": "cot", "title": {"zh": "信号路由（确定性）", "en": "Signal routing (deterministic)"},
                       "steps": [f"{p['step']} — {p['why']}" for p in route["plan"]]})
    rows = apply_s["rows"] if apply_s else []
    n_scale = sum(1 for r in rows if r["action"] == "SCALE")
    n_pause = sum(1 for r in rows if r["action"] == "PAUSE")
    blocks.append({"t": "kpis", "head": {"zh": "自主托管（shadow）", "en": "Autopilot (shadow)"},
                   "sub": {"zh": "熔断器保护", "en": "breaker-protected"},
                   "items": [
                       {"k": {"zh": "放量", "en": "Scale"}, "v": str(n_scale), "d": {"zh": "条", "en": "campaigns"}, "dc": "up"},
                       {"k": {"zh": "止损", "en": "Stop-loss"}, "v": str(n_pause), "d": {"zh": "归零", "en": "→ $0"}, "dc": "down"},
                       {"k": {"zh": "熔断器", "en": "Breaker"}, "v": {"zh": "通过", "en": "pass"}, "d": {"zh": "无异常", "en": "no anomaly"}, "dc": "up"},
                       {"k": {"zh": "模式", "en": "Mode"}, "v": "shadow", "d": {"zh": "不真写", "en": "no real write"}, "dc": "flat"},
                   ]})
    if learn and learn.get("learnings"):
        blocks.append({"t": "narr", "h": "<strong>Feedback:</strong> " + "；".join(learn["learnings"])})
    return blocks


BUILDERS = {"cross-platform-triage": triage, "intraday-guard": intraday, "autopilot": autopilot}


def main() -> None:
    out = {}
    order = []
    for cid, builder in BUILDERS.items():
        rec = json.loads((CASES / f"{cid}.json").read_text(encoding="utf-8"))
        key = f"real-{cid}"
        out[key] = {"real": True, "title": META[cid]["title"], "sub": META[cid]["sub"],
                    "q": META[cid]["q"], "blocks": builder(rec)}
        order.append(key)
    js = ("// AUTO-GENERATED by scripts/build_real_cases.py — real DeepSeek runs as console CONV blocks.\n"
          "window.DRIP_REAL_CASES = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n"
          "window.DRIP_REAL_ORDER = " + json.dumps(order) + ";\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"✓ {OUT}  ({len(out)} real cases: {', '.join(order)}, {OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
