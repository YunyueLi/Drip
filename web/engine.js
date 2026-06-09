/* Drip decision engine — browser port of the Python deterministic core.
 *
 * Faithful 1:1 translation of src/drip/engine/{signals,rules,intraday}.py,
 * src/drip/allocator.py, src/drip/supervisor.py and the offline sample data in
 * src/drip/collectors.py. The action is decided by these rules (auditable),
 * NOT by the LLM — exactly like the Python engine. The LLM only narrates the
 * "why" afterwards (see llm.js / run.js).
 *
 * Pure, no I/O, no deps. Verified equal to the Python outputs (see selfCheck()).
 * window.DripEngine is the public surface.
 */
(function () {
  "use strict";

  // ── tunable thresholds (signals.py Thresholds) ────────────────────────────
  var T = {
    cpp_yellow_ratio: 1.0, cpp_red_ratio: 1.2,
    roas_yellow_ratio: 1.0, roas_red_ratio: 0.8,
    stability_yellow_drop: 0.05, stability_red_drop: 0.15,
    spend_yellow_ratio: 0.90, spend_red_ratio: 1.0,
    min_sample: 10, sample_green_mult: 1.5,
    freq_cap: 2.5, freq_yellow: 2.0,
    headroom_green: 0.15, headroom_red: 0.05,
  };
  // intraday thresholds (config.py)
  var ID = { EXHAUST_EARLY: 0.85, COST_THROTTLE: 1.5, COST_PAUSE: 2.0, SPIKE: 1.5, THIN_CONV: 5 };
  // default targets (capture_cases.py)
  var TARGETS = { cpp_target: 25.0, roas_target: 3.0, budget: 1400.0 };

  // ── number formatting (mirrors Python f-strings exactly) ──────────────────
  function money(v, dec) {
    return "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }
  function pct(v, dec) { return (v * 100).toFixed(dec) + "%"; }     // {:.Nf%}
  function pct0(v) { return Math.round(v * 100) + "%"; }             // {:.0%}
  function oneX(v) { return v.toFixed(1) + "x"; }

  // ── signals (signals.py) ──────────────────────────────────────────────────
  var SC = { green: "g", yellow: "y", red: "r" };  // short status (capture_cases _STATUS)

  function sig(name, status, value, target, note) {
    return { name: name, status: status, sc: SC[status], value: value, target: target, note: note,
             is_green: status === "green", is_red: status === "red" };
  }

  function stabilityStatus(cur, base) {
    if (base <= 0) return "yellow";
    var drop = (base - cur) / base;
    if (drop >= T.stability_red_drop) return "red";
    if (drop >= T.stability_yellow_drop) return "yellow";
    return "green";
  }

  function evalCpp(m) {
    var ratio = m.cpp_target ? m.cpp / m.cpp_target : 99.0, status;
    if (ratio <= T.cpp_yellow_ratio) status = "green";
    else if (ratio <= T.cpp_red_ratio) status = "yellow";
    else status = "red";
    var p = (1 - ratio) * 100;
    var note = Math.abs(p).toFixed(0) + "% " + (p >= 0 ? "below" : "above") + " target";
    return sig("CPP", status, money(m.cpp, 2), money(m.cpp_target, 2), note);
  }
  function evalRoas(m) {
    var ratio = m.roas_target ? m.roas / m.roas_target : 0.0, status;
    if (ratio >= T.roas_yellow_ratio) status = "green";
    else if (ratio >= T.roas_red_ratio) status = "yellow";
    else status = "red";
    return sig("ROAS", status, oneX(m.roas), oneX(m.roas_target), status === "green" ? "exceeding" : "below target");
  }
  var STAB_NOTE = { green: "3-day stable", yellow: "softening", red: "dropping" };
  function evalCvr(m) {
    var s = stabilityStatus(m.cvr, m.cvr_baseline);
    return sig("Purchase CVR", s, pct(m.cvr, 2), pct(m.cvr_baseline, 2) + " base", STAB_NOTE[s]);
  }
  function evalSpend(m) {
    var ratio = m.budget_cap ? m.daily_spend / m.budget_cap : 99.0, status;
    if (ratio < T.spend_yellow_ratio) status = "green";
    else if (ratio < T.spend_red_ratio) status = "yellow";
    else status = "red";
    return sig("Daily Spend", status, money(m.daily_spend, 0), money(m.budget_cap, 0) + " cap", pct0(ratio) + " of cap");
  }
  function evalPurchases(m) {
    var status;
    if (m.purchases >= T.min_sample * T.sample_green_mult) status = "green";
    else if (m.purchases >= T.min_sample) status = "yellow";
    else status = "red";
    return sig("Purchases", status, String(m.purchases), "min " + T.min_sample,
               status === "green" ? "sufficient sample" : "thin sample");
  }
  function evalCtr(m) {
    var s = stabilityStatus(m.ctr, m.ctr_baseline);
    return sig("CTR", s, pct(m.ctr, 2), pct(m.ctr_baseline, 2) + " base", STAB_NOTE[s]);
  }
  function evalFrequency(m) {
    var status;
    if (m.frequency < T.freq_yellow) status = "green";
    else if (m.frequency <= T.freq_cap) status = "yellow";
    else status = "red";
    return sig("Frequency", status, m.frequency.toFixed(1), "cap " + T.freq_cap.toFixed(1),
               status === "green" ? "room to run" : "near saturation");
  }
  function evalBudgetHeadroom(m) {
    var headroom = m.budget_cap ? (m.budget_cap - m.daily_spend) / m.budget_cap : 0.0, status;
    if (headroom > T.headroom_green) status = "green";
    else if (headroom >= T.headroom_red) status = "yellow";
    else status = "red";
    return sig("Budget", status, pct0(headroom) + " headroom", ">15% to scale",
               status === "green" ? "room to scale" : "tight");
  }
  var EVALUATORS = [evalCpp, evalRoas, evalCvr, evalSpend, evalPurchases, evalCtr, evalFrequency, evalBudgetHeadroom];

  function evaluate(m) {
    var signals = EVALUATORS.map(function (fn) { return fn(m); });
    var green = signals.filter(function (s) { return s.is_green; }).length;
    var red = signals.filter(function (s) { return s.is_red; }).length;
    return {
      signals: signals, green: green, red: red, total: signals.length,
      summary: green + "/" + signals.length + " green",
      by: function (name) { return signals.filter(function (s) { return s.name === name; })[0] || null; },
    };
  }

  // ── rule engine (rules.py) ─────────────────────────────────────────────────
  function reason(id, message) { return { rule_id: id, message: message }; }

  function decide(sv, m) {
    var cpp = sv.by("CPP"), roas = sv.by("ROAS"), freq = sv.by("Frequency"),
        purch = sv.by("Purchases"), headroom = sv.by("Budget");
    var reasons = [], action = "HOLD", delta = 0.0;

    if (cpp && roas && cpp.is_red && roas.is_red) {
      action = "PAUSE"; delta = 0.0;
      reasons.push(reason("econ.both_red", "CPP and ROAS both red — unit economics broken"));
    } else if (roas && roas.is_red) {
      action = "REDUCE"; delta = -0.30;
      reasons.push(reason("econ.roas_red", "ROAS below floor — cut spend to protect efficiency"));
    } else if (cpp && cpp.is_red) {
      action = "REDUCE"; delta = -0.20;
      reasons.push(reason("econ.cpp_red", "CPP over tolerance — trim spend"));
    } else if (freq && freq.is_red) {
      action = "REFRESH_CREATIVE"; delta = 0.0;
      reasons.push(reason("creative.freq_saturated",
        "Frequency past cap — creative is saturating, refresh before adding budget"));
    } else if (sv.green >= 7 && !(headroom && headroom.is_red) && !(purch && purch.is_red)) {
      if (sv.green === 8 && purch && purch.is_green) {
        delta = 0.20;
        reasons.push(reason("scale.full_green", "8/8 signals green with a thick sample — scale at the standard step"));
      } else {
        delta = 0.10;
        reasons.push(reason("scale.cautious",
          sv.green + "/8 green but sample/headroom not fully clear — take the conservative step"));
      }
      action = "SCALE";
    } else {
      action = "HOLD"; delta = 0.0;
      reasons.push(reason("hold.mixed", sv.green + "/8 green, signals mixed — hold for clearer reads before moving budget"));
    }

    var conf;
    if (sv.green === 8 && purch && purch.is_green) conf = "HIGH";
    else if (sv.green >= 6) conf = "MEDIUM";
    else conf = "LOW";
    if (purch && purch.is_red) {
      conf = "LOW";
      reasons.push(reason("conf.thin_sample", "Sample below minimum — confidence capped low"));
    } else if (purch && purch.status === "yellow" && conf === "HIGH") {
      conf = "MEDIUM";
      reasons.push(reason("conf.sample_edge", "Sample near minimum — confidence downgraded"));
    }

    var guardrails = [];
    if (action === "SCALE" || action === "REDUCE") {
      guardrails.push({ condition: "CPP > " + money(m.cpp_target * 0.88, 2) });
      guardrails.push({ condition: "CTR drop > 15% within 24h" });
    }
    var nextCheck = { SCALE: 48, REDUCE: 24, PAUSE: 24, HOLD: 24, REFRESH_CREATIVE: 24 }[action];
    var projected = m.daily_spend * (1 + delta);
    return {
      action: action, delta_pct: delta, confidence: conf, reasons: reasons,
      guardrails: guardrails, next_check_hours: nextCheck,
      current_budget: m.daily_spend, projected_budget: projected,
    };
  }

  // ── allocator (allocator.py) ───────────────────────────────────────────────
  function allocate(metrics, opts) {
    var total = opts.total_budget;
    var verdicts = metrics.map(function (m) {
      var em = toEngine(m, { cpp_target: opts.cpp_target, roas_target: opts.roas_target, budget_cap: total });
      var sv = evaluate(em);
      return { m: m, em: em, sv: sv, decision: decide(sv, em) };
    });
    var desired = verdicts.map(function (v) {
      var a = v.decision.action;
      if (a === "PAUSE") return 0.0;
      if (a === "SCALE" || a === "REDUCE") return v.m.spend * (1 + v.decision.delta_pct);
      return v.m.spend;  // HOLD / REFRESH_CREATIVE keep current
    });
    var values = metrics.map(function (m) { return Math.max(m.roas, 0.1); });  // null value-model = ROAS
    var weights = desired.map(function (d, i) { return d * values[i]; });
    var wsum = weights.reduce(function (a, b) { return a + b; }, 0);
    var allocations = verdicts.map(function (v, i) {
      var nb = wsum > 0 ? total * (weights[i] / wsum) : 0.0;
      return { metrics: v.m, em: v.em, sv: v.sv, decision: v.decision,
               old_budget: v.m.spend, new_budget: Math.round(nb * 100) / 100 };
    });
    return { allocations: allocations, total_budget: total };
  }

  // ── supervisor (supervisor.py) ─────────────────────────────────────────────
  function classify(actions) {
    if (actions.indexOf("PAUSE") >= 0) return "bleeding";
    if (actions.indexOf("SCALE") >= 0) return "scaling";
    if (actions.indexOf("REFRESH_CREATIVE") >= 0) return "fatigued";
    return "steady";
  }
  var ROUTE_STEPS = {
    bleeding: [
      ["stop-loss", "pause units with broken unit economics before anything else"],
      ["reallocate", "move the freed budget to the survivors, within the daily cap"],
      ["hold-rest", "leave mixed/thin reads untouched until they clear"],
    ],
    scaling: [
      ["scale-winners", "raise the winners by the engine's sized step"],
      ["refresh-fatigued", "queue fresh creative for any saturating line"],
      ["allocate", "fund the plan across platforms"],
    ],
    fatigued: [
      ["refresh", "produce new creative for the fatigued winners"],
      ["hold-budget", "don't add budget into a saturating audience"],
    ],
    steady: [
      ["hold", "no budget moves — signals are mixed or thin"],
      ["gather", "wait for clearer reads before the next cycle"],
    ],
  };
  function route(actions) {
    var sit = classify(actions);
    return { situation: sit, steps: ROUTE_STEPS[sit].map(function (s) { return { step: s[0], why: s[1] }; }) };
  }
  function breakerPreApply(nTotal, nPause, maxPauseRatio) {
    maxPauseRatio = maxPauseRatio == null ? 0.6 : maxPauseRatio;
    if (nTotal && nPause / nTotal > maxPauseRatio) {
      return { tripped: true, why: nPause + "/" + nTotal + " campaigns want PAUSE (> " + pct0(maxPauseRatio) +
        ") — likely a data anomaly, halting before any write" };
    }
    return { tripped: false, why: "" };
  }

  // ── intraday (intraday.py) ─────────────────────────────────────────────────
  function evaluateIntraday(m) {
    var frac = Math.max(m.day_fraction, 1e-6);
    var expected = m.daily_budget * frac;
    var pace = expected ? m.spend_so_far / expected : 0.0;
    var cost = m.cpa_target ? m.cpa_recent / m.cpa_target : 0.0;
    var spike = m.cpa_baseline ? m.cpa_recent / m.cpa_baseline : 0.0;
    var rate = m.spend_so_far / frac;
    var exhaust = rate ? Math.min(m.daily_budget / rate, 1.0) : 1.0;
    return { pace_ratio: pace, cost_ratio: cost, spike_ratio: spike, projected_eod: rate, exhaust_at: exhaust,
      summary: "pace " + pace.toFixed(2) + "× · cost " + cost.toFixed(2) + "× target · spike " +
               spike.toFixed(2) + "× · exhausts at " + pct0(exhaust) + " of day" };
  }
  function decideIntraday(s, m) {
    var thin = m.conversions_recent < ID.THIN_CONV;
    var reasons = [], action = "HOLD", delta = 0.0;
    if (s.cost_ratio >= ID.COST_PAUSE && !thin) {
      action = "PAUSE"; delta = 0.0;
      reasons.push(reason("intraday.cost_breach", "recent CPA " + s.cost_ratio.toFixed(1) + "× target — stop the bleed now"));
    } else if (s.cost_ratio >= ID.COST_THROTTLE || (s.spike_ratio >= ID.SPIKE && s.cost_ratio >= 1.0)) {
      action = "THROTTLE"; delta = -0.30;
      reasons.push(reason("intraday.cost_high", "recent CPA " + s.cost_ratio.toFixed(1) + "× target (spike " +
        s.spike_ratio.toFixed(1) + "×) — cut budget to re-pace"));
    } else if (s.exhaust_at < ID.EXHAUST_EARLY && s.cost_ratio > 1.0) {
      action = "THROTTLE"; delta = -0.15;
      reasons.push(reason("intraday.overpace", "budget exhausts at " + pct0(s.exhaust_at) +
        " of day and cost is soft — trim to keep evening coverage"));
    } else if (s.pace_ratio < 0.7 && s.cost_ratio <= 0.9 && !thin) {
      action = "RAISE"; delta = 0.10;
      reasons.push(reason("intraday.underpace_healthy", "only " + pct0(s.pace_ratio) + " of expected spend and CPA " +
        s.cost_ratio.toFixed(1) + "× target — nudge budget up"));
    } else {
      reasons.push(reason("intraday.steady", "pacing and cost within band — hold"));
    }
    if (thin && (action === "PAUSE" || action === "RAISE")) {
      action = "HOLD"; delta = 0.0;
      reasons.push(reason("intraday.thin_sample", "only " + m.conversions_recent + " conversions in window — hold, too noisy"));
    }
    var conf;
    if (thin) conf = "LOW";
    else if (action === "HOLD") conf = "MEDIUM";
    else conf = (s.cost_ratio >= ID.COST_PAUSE || s.cost_ratio <= 0.9) ? "HIGH" : "MEDIUM";
    var projected = (action === "THROTTLE" || action === "RAISE") ? m.daily_budget * (1 + delta)
      : (action === "PAUSE" ? 0.0 : m.daily_budget);
    var headline = (action === "THROTTLE" || action === "RAISE")
      ? (action + " · " + money(m.daily_budget, 0) + " → " + money(projected, 0) + "/day (" +
         (delta >= 0 ? "+" : "") + pct0(delta) + ")")
      : action;
    return { action: action, delta_pct: delta, confidence: conf, reasons: reasons,
             next_check_min: 30, current_budget: m.daily_budget, projected_budget: projected, headline: headline };
  }
  function sampleIntraday(cpaTarget) {
    return [
      { campaign_id: "meta-0001", daily_budget: 200.0, spend_so_far: 100.0, day_fraction: 0.5,
        cpa_recent: 18.0, cpa_baseline: 18.0, cpa_target: cpaTarget, conversions_recent: 9,
        label: "Meta_Prospecting_v3", platform: "meta" },
      { campaign_id: "meta-0002", daily_budget: 240.0, spend_so_far: 150.0, day_fraction: 0.5,
        cpa_recent: 44.0, cpa_baseline: 26.0, cpa_target: cpaTarget, conversions_recent: 7,
        label: "Meta_Broad_v1", platform: "meta" },
      { campaign_id: "meta-0003", daily_budget: 180.0, spend_so_far: 150.0, day_fraction: 0.5,
        cpa_recent: 27.0, cpa_baseline: 26.0, cpa_target: cpaTarget, conversions_recent: 8,
        label: "Meta_Lookalike_v2", platform: "meta" },
      { campaign_id: "meta-0004", daily_budget: 160.0, spend_so_far: 40.0, day_fraction: 0.5,
        cpa_recent: 15.0, cpa_baseline: 16.0, cpa_target: cpaTarget, conversions_recent: 10,
        label: "Meta_Retarget_v4", platform: "meta" },
    ];
  }

  // ── AdMetrics + offline samples (data/metrics.py + collectors.py) ──────────
  function adMetrics(o) {
    var ctr = o.impressions ? o.clicks / o.impressions : 0.0;
    var cpp = o.conversions ? o.spend / o.conversions : 0.0;
    var cvr = o.clicks ? o.conversions / o.clicks : 0.0;
    var roas = o.spend ? o.conversion_value / o.spend : 0.0;
    var frequency = o.reach ? o.impressions / o.reach : 0.0;
    return Object.assign({}, o, { ctr: ctr, cpp: cpp, cvr: cvr, roas: roas, frequency: frequency });
  }
  function toEngine(m, opts) {
    return {
      cpp: m.cpp, cpp_target: opts.cpp_target,
      roas: m.roas, roas_target: opts.roas_target,
      cvr: m.cvr, cvr_baseline: m.cvr,
      daily_spend: m.spend, budget_cap: opts.budget_cap,
      purchases: Math.trunc(m.conversions),
      ctr: m.ctr, ctr_baseline: m.ctr,
      frequency: m.frequency,
      label: m.label || (m.platform + ":" + m.campaign_id),
    };
  }
  function title(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function sampleFor(platform) {
    var H = { spend: 200.0, conversions: 12.0, conversion_value: 760.0, clicks: 1400, impressions: 100000, reach: 56000 };
    var S = { spend: 240.0, conversions: 6.0, conversion_value: 336.0, clicks: 800, impressions: 100000, reach: 40000 };
    return [
      adMetrics(Object.assign({ platform: platform, campaign_id: platform + "-h",
        label: title(platform) + "_Prospecting_v3" }, H)),
      adMetrics(Object.assign({ platform: platform, campaign_id: platform + "-s",
        label: title(platform) + "_Broad_v1" }, S)),
    ];
  }
  // Collector default: Meta + TikTok (both seeds) + Tencent/OceanEngine/Kuaishou ([:1] each) = 7 campaigns.
  function sampleMetrics() {
    return [].concat(
      sampleFor("meta"), sampleFor("tiktok"),
      sampleFor("tencent").slice(0, 1), sampleFor("oceanengine").slice(0, 1), sampleFor("kuaishou").slice(0, 1)
    );
  }

  // ── self-check: assert the port equals the Python reference ────────────────
  function selfCheck() {
    var ms = sampleMetrics(), errs = [];
    var ref = [["Meta_Prospecting_v3", 7, "SCALE", 0.1, "MEDIUM"], ["Meta_Broad_v1", 4, "PAUSE", 0.0, "LOW"],
               ["Tiktok_Prospecting_v3", 7, "SCALE", 0.1, "MEDIUM"], ["Tiktok_Broad_v1", 4, "PAUSE", 0.0, "LOW"],
               ["Tencent_Prospecting_v3", 7, "SCALE", 0.1, "MEDIUM"], ["Oceanengine_Prospecting_v3", 7, "SCALE", 0.1, "MEDIUM"],
               ["Kuaishou_Prospecting_v3", 7, "SCALE", 0.1, "MEDIUM"]];
    ms.forEach(function (m, i) {
      var em = toEngine(m, { cpp_target: TARGETS.cpp_target, roas_target: TARGETS.roas_target, budget_cap: TARGETS.budget });
      var sv = evaluate(em), d = decide(sv, em), r = ref[i];
      if (m.label !== r[0] || sv.green !== r[1] || d.action !== r[2] || d.delta_pct !== r[3] || d.confidence !== r[4])
        errs.push("triage[" + i + "] " + m.label + " got " + [sv.green, d.action, d.delta_pct, d.confidence].join("/"));
    });
    var plan = allocate(ms, { total_budget: TARGETS.budget, cpp_target: TARGETS.cpp_target, roas_target: TARGETS.roas_target });
    plan.allocations.forEach(function (a) {
      var want = a.decision.action === "PAUSE" ? 0.0 : 280.0;
      if (Math.abs(a.new_budget - want) > 0.01) errs.push("alloc " + a.metrics.label + " new=" + a.new_budget + " want " + want);
    });
    var idref = [["HOLD", 0.0], ["THROTTLE", -0.3], ["THROTTLE", -0.15], ["RAISE", 0.1]];
    sampleIntraday(TARGETS.cpp_target).forEach(function (m, i) {
      var s = evaluateIntraday(m), d = decideIntraday(s, m);
      if (d.action !== idref[i][0] || Math.abs(d.delta_pct - idref[i][1]) > 1e-9)
        errs.push("intraday[" + i + "] " + m.label + " got " + d.action + "/" + d.delta_pct);
    });
    return { ok: errs.length === 0, errors: errs };
  }

  window.DripEngine = {
    THRESHOLDS: T, INTRADAY: ID, TARGETS: TARGETS,
    adMetrics: adMetrics, toEngine: toEngine, sampleMetrics: sampleMetrics,
    evaluate: evaluate, decide: decide, allocate: allocate,
    route: route, breakerPreApply: breakerPreApply, classify: classify,
    evaluateIntraday: evaluateIntraday, decideIntraday: decideIntraday, sampleIntraday: sampleIntraday,
    selfCheck: selfCheck,
    fmt: { money: money, pct: pct, pct0: pct0, oneX: oneX },
  };
})();
