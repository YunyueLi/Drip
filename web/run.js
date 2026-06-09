/* Live product run — the console actually runs the real engine in the browser.
 *
 * When you type in the composer, this:
 *   1. runs the deterministic decision engine (engine.js) on your data — the
 *      8-signal + rules + allocator core, byte-equivalent to the Python engine;
 *   2. narrates each decision with YOUR model via browser-direct LLM (llm.js),
 *      exactly the telos pattern — no backend, no FastAPI;
 *   3. renders it through the existing console renderer (intro/cot/card/kpis/narr).
 *
 * Rules decide (auditable), the LLM only explains — same contract as Python.
 * No API key? It degrades to the deterministic template narration, like the
 * Python narrate() fallback.
 */
(function () {
  "use strict";
  var E = window.DripEngine;
  if (!E) return;

  var TG = E.TARGETS;
  var zh = function () { return !(typeof curLang !== "undefined" && curLang && curLang.indexOf("zh") !== 0); };
  var t = function (z, e) { return zh() ? z : e; };

  // ── narration (mirrors engine.py narrate / _template_why) ──────────────────
  var NARRATE_SYSTEM =
    "You are a senior user-acquisition operator. You are given a campaign's " +
    "8-signal snapshot and the decision a deterministic rule engine has already " +
    "made. Write 2-3 sentences explaining WHY this is the right call, referencing " +
    "the specific signals and numbers. Do not second-guess or change the action — " +
    "explain it. No preamble, no bullet points.";

  function sys(extra) {
    var s = extra;
    if (zh()) s += " 用简体中文回答。"; else s += " Respond in English.";
    return s;
  }
  function templateWhy(sv, d) {
    var head = (d.reasons[0] && d.reasons[0].message) || d.action;
    return head + ". Signals: " + sv.summary + ".";
  }
  // narrate(): live LLM if a key roams with the account, else the template.
  function narrate(system, user, fallback) {
    if (!window.DripLLM || !window.DripLLM.hasKey()) return Promise.resolve(fallback);
    return window.DripLLM.chat({ system: system, user: user, maxTokens: 2048, temperature: 0.0 })
      .then(function (txt) { return txt || fallback; })
      .catch(function () { return fallback; });
  }
  function decisionHeadline(d) {
    if (d.action === "SCALE" || d.action === "REDUCE") {
      var sign = d.delta_pct >= 0 ? "+" : "";
      return d.action + " · " + E.fmt.money(d.current_budget, 0) + " → " + E.fmt.money(d.projected_budget, 0) +
        "/day (" + sign + E.fmt.pct0(d.delta_pct) + ")";
    }
    return d.action;
  }
  function narrateCard(v) {
    var sv = v.sv, d = v.d, m = v.em;
    var lines = sv.signals.map(function (s) {
      var status = (s.status.toUpperCase() + "      ").slice(0, 6);
      return "  " + status + " " + s.name + ": " + s.value + " (target " + s.target + ") — " + s.note;
    });
    var ruleLines = d.reasons.map(function (r) { return "  - " + r.message; }).join("\n");
    var user = "CAMPAIGN: " + m.label + "\n\nSIGNALS (" + sv.summary + "):\n" + lines.join("\n") +
      "\n\nRULE-ENGINE DECISION: " + decisionHeadline(d) + "\nconfidence: " + d.confidence +
      "\nrule chain:\n" + ruleLines + "\n\nExplain why this decision is correct.";
    return narrate(sys(NARRATE_SYSTEM), user, templateWhy(sv, d));
  }

  // ── block helpers (mirror build_real_cases.py) ─────────────────────────────
  var ACT = { SCALE: "scale", PAUSE: "pause", REFRESH_CREATIVE: "refresh", REDUCE: "reduce", HOLD: "hold",
              THROTTLE: "reduce", RAISE: "scale" };
  function cardBlock(v, budget, why) {
    var sv = v.sv, d = v.d, m = v.m;
    return { t: "card", act: ACT[d.action] || "hold", actLabel: d.action, name: m.label, plat: m.platform,
      budget: budget || "", conf: d.confidence.toLowerCase(), confLabel: d.confidence, why: why,
      sigLab: "8 signals " + sv.green + "/8",
      sigs: sv.signals.slice(0, 4).map(function (s) { return [s.name, s.sc, s.value]; }) };
  }

  // ── flow: cross-platform triage (drip run) ─────────────────────────────────
  // src.metrics (live AdMetrics) overrides the offline sample; src.total sets the
  // reallocation pool (sum of real spends when live). src.live stashes the
  // platform change-set so the console can offer "apply to platform".
  var liveCtx = null;
  function buildTriage(prompt, src) {
    src = src || {};
    var metrics = src.metrics || E.sampleMetrics();
    var total = src.total || TG.budget;
    var opts = { cpp_target: TG.cpp_target, roas_target: TG.roas_target, budget_cap: total };
    var verdicts = metrics.map(function (m) {
      var em = E.toEngine(m, opts), sv = E.evaluate(em);
      return { m: m, em: em, sv: sv, d: E.decide(sv, em) };
    });
    var plan = E.allocate(metrics, { total_budget: total, cpp_target: TG.cpp_target, roas_target: TG.roas_target });
    if (src.live) {
      liveCtx = { changes: plan.allocations
        .filter(function (a) { return a.decision.action === "SCALE" || a.decision.action === "PAUSE"; })
        .map(function (a) { return { target_id: a.metrics.campaign_id, action: a.decision.action,
          new_budget: a.new_budget, old_budget: a.old_budget, label: a.metrics.label }; }) };
    } else { liveCtx = null; }
    var budgetBy = {};
    plan.allocations.forEach(function (a) {
      budgetBy[a.metrics.label] = E.fmt.money(a.old_budget, 0) + " → " + E.fmt.money(a.new_budget, 0);
    });
    var winner = verdicts.filter(function (v) { return v.d.action === "SCALE"; })[0];
    var loser = verdicts.filter(function (v) { return v.d.action === "PAUSE"; })[0];
    var nScale = verdicts.filter(function (v) { return v.d.action === "SCALE"; }).length;
    var nPause = verdicts.filter(function (v) { return v.d.action === "PAUSE"; }).length;
    var perWinner = plan.allocations.filter(function (a) { return a.decision.action === "SCALE"; })[0];

    var overviewUser = "Diagnosed " + metrics.length + " campaigns across Meta/TikTok/Tencent/OceanEngine/Kuaishou. " +
      "The rule engine decided: " + nScale + " SCALE, " + nPause + " PAUSE, rest hold. Summarize the diagnosis in 2 sentences.";
    var feedbackUser = "After triaging " + metrics.length + " campaigns (" + nScale + " scaled, " + nPause +
      " stopped), give one or two sentences of feedback/learnings to carry into the next cycle.";

    return Promise.all([
      narrate(sys("You are a senior UA operator. Summarize a cross-platform diagnosis briefly."), overviewUser,
        t("扫描 " + metrics.length + " 条 campaign：规则给出 " + nScale + " 条放量、" + nPause + " 条止损，其余保持。",
          "Scanned " + metrics.length + " campaigns: rules say " + nScale + " scale, " + nPause + " stop-loss, rest hold.")),
      winner ? narrateCard(winner) : Promise.resolve(""),
      loser ? narrateCard(loser) : Promise.resolve(""),
      narrate(sys("You are a senior UA operator giving concise post-run feedback."), feedbackUser,
        t("赢家集中在健康单元经济的 Prospecting 线；止损腾出的预算已按 ROAS 权重回流。",
          "Winners cluster in the healthy-economics Prospecting lines; freed budget flowed back weighted by ROAS.")),
    ]).then(function (r) {
      var intro = r[0], winWhy = r[1], loseWhy = r[2], feedback = r[3];
      var blocks = [{ t: "intro", h: intro }];
      blocks.push({ t: "cot", title: t("Drip 怎么跑的", "How Drip ran it"), steps: [
        t("采集 5 个平台共 " + metrics.length + " 条 campaign，归一到 AdMetrics",
          "Collected " + metrics.length + " campaigns from 5 platforms, normalised to AdMetrics"),
        t("对每条跑 8 信号（CPP/ROAS/CVR/花费/成交/CTR/频次/余量）",
          "Scored each on 8 signals (CPP/ROAS/CVR/spend/purchases/CTR/freq/headroom)"),
        t("规则引擎 → " + nScale + " SCALE / " + nPause + " PAUSE，确定性可审计",
          "Rule engine → " + nScale + " SCALE / " + nPause + " PAUSE, deterministic & auditable"),
        t("Allocator 在 " + E.fmt.money(total, 0) + " 内按 ROAS 权重重分，止损预算回流赢家",
          "Allocator reallocated within " + E.fmt.money(total, 0) + " by ROAS weight; freed budget to winners"),
      ] });
      if (winner) blocks.push(cardBlock(winner, budgetBy[winner.m.label], winWhy));
      if (loser) blocks.push(cardBlock(loser, budgetBy[loser.m.label], loseWhy));
      blocks.push({ t: "kpis", head: t("跨平台再分配", "Cross-platform reallocation"), sub: E.fmt.money(total, 0) + t(" 总预算", " budget"),
        items: [
          { k: t("放量", "Scale"), v: String(nScale), d: t("条 campaign", "campaigns"), dc: "up" },
          { k: t("止损", "Stop-loss"), v: String(nPause), d: t("归零", "→ $0"), dc: "down" },
          { k: t("赢家单条", "Per winner"), v: perWinner ? E.fmt.money(perWinner.new_budget, 0) : "—", d: t("↑ 加投", "↑ scaled"), dc: "up" },
          { k: t("口径", "Basis"), v: "8/8", d: t("信号 + 规则", "signals + rules"), dc: "flat" },
        ] });
      if (feedback) blocks.push({ t: "narr", h: "<strong>" + t("反馈", "Feedback") + "：</strong>" + feedback });
      return blocks;
    });
  }

  // ── flow: intraday spend-side guard (drip watch) ───────────────────────────
  function buildIntraday(prompt) {
    var rows = E.sampleIntraday(TG.cpp_target).map(function (m) {
      var s = E.evaluateIntraday(m); return { m: m, s: s, d: E.decideIntraday(s, m) };
    });
    var acted = rows.filter(function (r) { return r.d.action !== "HOLD"; });
    var introUser = "Intraday spend-side check on " + rows.length + " campaigns: " + acted.length +
      " triggered throttle/pause, the rest hold. Summarize in 2 sentences (spend-side only, not ROI).";
    return narrate(sys("You are a senior UA operator watching intraday pacing/cost."), introUser,
      t(acted.length + " 条触发限速/暂停，其余 pacing 与成本在区间内，保持。",
        acted.length + " throttled/paused; the rest are within the pacing/cost band — hold.")
    ).then(function (intro) {
      var blocks = [{ t: "intro", h: intro }];
      blocks.push({ t: "cot", title: t("盘中规则链", "Intraday rule chain"),
        steps: rows.map(function (r) { return r.m.label + " · " + r.s.summary + " → " + r.d.action; }) });
      blocks.push({ t: "kpis", head: t("盘中花费侧守卫", "Intraday spend guard"), sub: t("小时级", "hourly"),
        items: [
          { k: t("触发动作", "Acted"), v: String(acted.length), d: t("限速/暂停", "throttle/pause"), dc: "down" },
          { k: t("观察", "Hold"), v: String(rows.length - acted.length), d: t("正常", "normal"), dc: "flat" },
          { k: t("层级", "Layer"), v: t("花费侧", "spend-side"), d: t("非 ROI", "not ROI"), dc: "flat" },
          { k: t("护栏", "Gate"), v: t("已审计", "audited"), d: "shadow", dc: "flat" },
        ] });
      acted.slice(0, 2).forEach(function (r) {
        blocks.push({ t: "card", act: ACT[r.d.action] || "hold", actLabel: r.d.action, name: r.m.label,
          plat: r.m.platform, budget: r.d.headline, conf: "med", confLabel: t("盘中", "intraday"),
          why: r.d.reasons[0] ? r.d.reasons[0].message : r.d.headline, sigLab: r.s.summary, sigs: [] });
      });
      return blocks;
    });
  }

  // ── flow: autopilot one cycle (drip autopilot, shadow) ─────────────────────
  function buildAutopilot(prompt) {
    var metrics = E.sampleMetrics();
    var plan = E.allocate(metrics, { total_budget: TG.budget, cpp_target: TG.cpp_target, roas_target: TG.roas_target });
    var actions = plan.allocations.map(function (a) { return a.decision.action; });
    var rr = E.route(actions);
    var nTotal = actions.length;
    var nPause = actions.filter(function (a) { return a === "PAUSE"; }).length;
    var nScale = actions.filter(function (a) { return a === "SCALE"; }).length;
    var brk = E.breakerPreApply(nTotal, nPause);
    var introUser = "Autopilot one cycle. Situation: " + rr.situation + ". " + nPause + "/" + nTotal +
      " want PAUSE, circuit breaker " + (brk.tripped ? "TRIPPED" : "passed") + ". Summarize the plan in 2 sentences (shadow mode, no real writes).";
    return narrate(sys("You are a senior UA operator running an autonomous cycle behind a circuit breaker."), introUser,
      t("局面：" + rr.situation + "。先止血再放量/分配，全程熔断器保护；shadow 模式不真写。",
        "Situation: " + rr.situation + ". Stop-loss first, then scale/allocate behind a circuit breaker; shadow — no real writes.")
    ).then(function (intro) {
      var blocks = [{ t: "intro", h: intro }];
      blocks.push({ t: "cot", title: t("信号路由（确定性）", "Signal routing (deterministic)"),
        steps: rr.steps.map(function (s) { return s.step + " — " + s.why; }) });
      blocks.push({ t: "kpis", head: t("自主托管（shadow）", "Autopilot (shadow)"), sub: t("熔断器保护", "breaker-protected"),
        items: [
          { k: t("放量", "Scale"), v: String(nScale), d: t("条", "campaigns"), dc: "up" },
          { k: t("止损", "Stop-loss"), v: String(nPause), d: t("归零", "→ $0"), dc: "down" },
          { k: t("熔断器", "Breaker"), v: brk.tripped ? t("触发", "tripped") : t("通过", "pass"), d: t("无异常", "no anomaly"), dc: brk.tripped ? "down" : "up" },
          { k: t("模式", "Mode"), v: "shadow", d: t("不真写", "no real write"), dc: "flat" },
        ] });
      return blocks;
    });
  }

  // ── intent detection ───────────────────────────────────────────────────────
  function detect(prompt) {
    var p = (prompt || "").toLowerCase();
    if (/盘中|超支|突刺|限速|过快|spike|intraday|hourly|pacing|overspend/.test(p)) return buildIntraday;
    if (/自动|托管|自主|全自动|autopilot|autonomous|熔断/.test(p)) return buildAutopilot;
    return buildTriage;  // diagnose / reallocate / triage default
  }

  // ── progressive reveal (same feel as the replay) ───────────────────────────
  var reduce = function () { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; };
  function reveal(done) {
    var host = document.getElementById("convHost");
    var content = host && host.querySelector(".msg.bot .content");
    if (!content || reduce()) { if (done) done(); return; }
    var blocks = [].slice.call(content.children);
    blocks.forEach(function (el) { el.classList.add("rp-hide"); });
    var i = 0;
    (function step() {
      if (i < blocks.length) {
        var el = blocks[i++]; el.classList.remove("rp-hide"); el.classList.add("rp-in");
        var sc = document.querySelector(".thread"); if (sc) sc.scrollTop = sc.scrollHeight;
        setTimeout(step, 560);
      } else if (done) { done(); }
    })();
  }

  function note(host, msg) {
    if (!host || document.getElementById("rpBar")) return;
    var b = document.createElement("div"); b.id = "rpBar"; b.className = "rp-bar";
    b.innerHTML = '<span class="rp-st"><span class="rp-ok">✓</span>' + msg + '</span>';
    host.appendChild(b);
    b.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "end" });
  }

  // ── live: pull the connected account's real campaigns, decide on real data ──
  function runLive(prompt) {
    return window.DripLive.pull({ platform: "meta" }).then(function (d) {
      var metrics = (d.metrics || []).map(E.adMetrics);
      if (!metrics.length) throw new window.DripLive.Error(t("账户近 7 天没有可诊断的 campaign", "no campaigns to diagnose in the last 7 days"));
      var total = metrics.reduce(function (s, m) { return s + m.spend; }, 0) || TG.budget;
      return buildTriage(prompt, { metrics: metrics, total: total, live: true });
    });
  }

  // read the run mode + caps from Settings → 运行与模型 (radios in shadow/copilot/auto order)
  function getMode() {
    var radios = document.querySelectorAll('.set-pane[data-spane="run"] input[name="mode"]');
    var names = ["shadow", "copilot", "autonomous"];
    for (var i = 0; i < radios.length; i++) if (radios[i].checked) return names[i] || "shadow";
    return "shadow";
  }
  function getCaps() {
    var inp = document.querySelector('.set-pane[data-spane="run"] .fcard input.inp');
    var cap = inp ? Number(String(inp.value).replace(/[^0-9.]/g, "")) || 0 : 0;
    return { budget_cap: cap, max_change_pct: 0.5 };
  }

  // apply bar shown after a live run — writes the change-set back, gated by mode
  function applyBar(host, changes) {
    if (!host || document.getElementById("rpBar") || !changes || !changes.length) return;
    var mode = getMode();
    var b = document.createElement("div"); b.id = "rpBar"; b.className = "rp-bar";
    var nScale = changes.filter(function (c) { return c.action === "SCALE"; }).length;
    var nPause = changes.filter(function (c) { return c.action === "PAUSE"; }).length;
    var verb = mode === "shadow" ? t("预演写回(shadow)", "Preview (shadow)") : t("应用到平台", "Apply to platform");
    b.innerHTML = '<span class="rp-st"><span class="rp-ok">✓</span>' +
      t("真实账户 · " + nScale + " 放量 / " + nPause + " 止损", "Live · " + nScale + " scale / " + nPause + " stop-loss") +
      '</span><span class="rp-acts"><button class="rp-btn ink" id="rpApply">' + verb + ' · ' + mode + '</button></span>';
    host.appendChild(b);
    b.querySelector("#rpApply").onclick = function () {
      var btn = this; btn.disabled = true; btn.textContent = t("写回中…", "applying…");
      window.DripLive.apply(changes, mode, getCaps()).then(function (r) {
        var res = r.results || [];
        var applied = res.filter(function (x) { return x.status === "applied"; }).length;
        var shadow = res.filter(function (x) { return x.status === "shadow"; }).length;
        var denied = res.filter(function (x) { return x.status === "denied" || x.status === "failed"; }).length;
        (window.showToast || alert)(t("写回完成：", "done: ") + applied + " applied · " + shadow + " shadow" + (denied ? (" · " + denied + " denied/failed") : ""));
        btn.textContent = t("已处理 ", "processed ") + res.length;
      }).catch(function (e) {
        (window.showToast || alert)(t("写回失败：", "apply failed: ") + (e.message || e)); btn.disabled = false; btn.textContent = verb + " · " + mode;
      });
    };
    b.scrollIntoView({ behavior: reduce() ? "auto" : "smooth", block: "end" });
  }

  var running = false;
  function run(prompt) {
    if (running) return;
    prompt = (prompt || "").trim(); if (!prompt) return;
    running = true;
    if (typeof setView === "function") setView("console");
    var build = detect(prompt);
    var hasKey = window.DripLLM && window.DripLLM.hasKey();
    var live = build === buildTriage && window.DripLive && window.DripLive.ready();

    var pending = live
      ? t("⚙️ 正在拉取你的真实账户数据…", "⚙️ Pulling your live account data…")
      : (hasKey
        ? t("⚙️ 规则引擎已出决策，正在用你的模型生成解释…", "⚙️ Rules decided. Generating the explanation with your model…")
        : t("⚙️ 规则引擎已出决策（解释为模板；登录并配置模型后由你的 LLM 实时生成）。",
            "⚙️ Rules decided (template explanation; configure your model to narrate live)."));
    if (window.__setConv) window.__setConv("__live", { q: prompt, blocks: [{ t: "intro", h: pending }] });
    if (window.__showConv) window.__showConv("__live");

    // live triage, falling back to the offline sample if no account is connected
    var built = live
      ? runLive(prompt).catch(function (e) {
          if (e && e.status === 409) { return buildTriage(prompt).then(function (bl) {
            bl.unshift({ t: "intro", h: t("（未连接真实账户，下面用样本演示。去 设置→连接器 连接 Meta。）",
              "(No live account connected — sample demo below. Connect Meta in Settings → Connectors.)") }); return bl; }); }
          throw e;
        })
      : build(prompt);

    built.then(function (blocks) {
      var isLive = live && liveCtx && liveCtx.changes;
      if (window.__setConv) window.__setConv("__live", { q: prompt, blocks: blocks });
      if (window.__showConv) window.__showConv("__live");
      reveal(function () {
        var host = document.getElementById("convHost");
        if (isLive) applyBar(host, liveCtx.changes);
        else note(host, hasKey
          ? t("运行完成 · 规则决策，你的模型解释", "Run complete · rules decided, your model explained")
          : t("运行完成 · 配置模型后解释由你的 LLM 实时生成", "Run complete · configure your model for live narration"));
      });
    }).catch(function (err) {
      if (window.__setConv) window.__setConv("__live", { q: prompt, blocks: [{ t: "intro",
        h: t("运行出错：", "Run error: ") + (err && err.message || err) }] });
      if (window.__showConv) window.__showConv("__live");
    }).then(function () { running = false; });
  }

  window.DripRun = { run: run, runLive: runLive, detect: detect, buildTriage: buildTriage, buildIntraday: buildIntraday, buildAutopilot: buildAutopilot };
})();
