/* Backend integration test — runs the REAL Edge-Function logic (supabase/
 * functions/_shared/meta.ts) against a faithful in-memory fake of the Meta
 * Graph API. Proves the deployed code is correct without needing a Meta app.
 *
 *   node --experimental-strip-types scripts/itest_backend.ts
 *
 * Covers: insights→AdMetrics normalisation (per-day division + action parsing),
 * the money-safety gate (caps / mode / token), the snapshot→update→verify write
 * path (SCALE/PAUSE/idempotent/mismatch→failed), and the OAuth code exchange.
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

// ── fake Meta Graph API (in-memory campaign store) ───────────────────────────
const campaigns: Record<string, { name: string; status: string; daily_budget: string }> = {
  "camp_win": { name: "DTC_US_Prospecting_v3", status: "ACTIVE", daily_budget: "20000" }, // $200.00 (cents)
  "camp_lose": { name: "DTC_US_Broad_v1", status: "ACTIVE", daily_budget: "24000" },       // $240.00
  "camp_paused": { name: "Already_Paused", status: "PAUSED", daily_budget: "10000" },
  "camp_stuck": { name: "Wont_Update", status: "ACTIVE", daily_budget: "15000" },           // ignores writes → failed
};

function send(res: ServerResponse, code: number, body: unknown) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => { let s = ""; req.on("data", (c) => (s += c)); req.on("end", () => resolve(s)); });
}

const server = createServer(async (req, res) => {
  const u = new URL(req.url || "", "http://x");
  const path = u.pathname;

  // insights
  if (path.endsWith("/insights")) {
    // cumulative over an 8-day window (since→until inclusive); ÷8 → per-day below
    return send(res, 200, { data: [
      { campaign_id: "camp_win", campaign_name: "DTC_US_Prospecting_v3",
        spend: "1600", impressions: "800000", clicks: "11200", reach: "56000",
        actions: [{ action_type: "purchase", value: "96" }, { action_type: "link_click", value: "11200" }],
        action_values: [{ action_type: "purchase", value: "6080" }] },
      { campaign_id: "camp_lose", campaign_name: "DTC_US_Broad_v1",
        spend: "1920", impressions: "800000", clicks: "6400", reach: "40000",
        actions: [{ action_type: "offsite_conversion.fb_pixel_purchase", value: "48" }],
        action_values: [{ action_type: "offsite_conversion.fb_pixel_purchase", value: "2688" }] },
    ] });
  }
  // oauth exchange (short + long-lived both hit this)
  if (path.endsWith("/oauth/access_token")) {
    const grant = u.searchParams.get("grant_type");
    return send(res, 200, grant === "fb_exchange_token"
      ? { access_token: "LONG_LIVED_TOKEN", expires_in: 5184000 }
      : { access_token: "SHORT_TOKEN", expires_in: 3600 });
  }
  // me/adaccounts
  if (path.endsWith("/me/adaccounts")) return send(res, 200, { data: [{ account_id: "999888", name: "Test Account" }] });

  // /{id}: GET reads, POST updates
  const id = path.split("/").filter(Boolean).pop() || "";
  const c = campaigns[id];
  if (!c) return send(res, 400, { error: { message: `unknown id ${id}` } });
  if (req.method === "POST") {
    const body = new URLSearchParams(await readBody(req));
    if (id !== "camp_stuck") { // camp_stuck silently ignores → forces a post-write mismatch
      if (body.has("status")) c.status = body.get("status")!;
      if (body.has("daily_budget")) c.daily_budget = body.get("daily_budget")!;
    }
    return send(res, 200, { success: true });
  }
  return send(res, 200, { id, name: c.name, status: c.status, daily_budget: c.daily_budget });
});

// ── test harness ─────────────────────────────────────────────────────────────
let pass = 0, fail = 0;
const fails: string[] = [];
function ok(cond: boolean, msg: string) { if (cond) { pass++; } else { fail++; fails.push(msg); console.error("  ✗ " + msg); } }
function eq(a: unknown, b: unknown, msg: string) { ok(JSON.stringify(a) === JSON.stringify(b), `${msg} (got ${JSON.stringify(a)}, want ${JSON.stringify(b)})`); }

await new Promise<void>((r) => server.listen(0, r));
const port = (server.address() as { port: number }).port;
process.env.META_GRAPH_BASE = `http://127.0.0.1:${port}`;

const M = await import("../supabase/functions/_shared/meta.ts");

try {
  // 1) pull → AdMetrics, 7-day window (cumulative ÷ 7)
  const metrics = await M.pullInsights("TKN", "999888", "2026-05-21", "2026-05-28");
  eq(metrics.length, 2, "pull: 2 campaigns");
  const win = metrics[0];
  eq([win.spend, win.conversions, win.conversion_value, win.clicks, win.impressions, win.reach],
     [200, 12, 760, 1400, 100000, 56000], "pull: winner normalised per-day");
  const lose = metrics[1];
  eq([lose.spend, lose.conversions, lose.conversion_value], [240, 6, 336], "pull: loser per-day (fb_pixel_purchase parsed)");
  eq(win.platform, "meta", "pull: platform tag");

  // 2) money-safety gate (caps / mode / token)
  const caps = { budget_cap: 500, max_change_pct: 0.5 };
  eq(M.gateWrite("SCALE", 200, 220, "autonomous", caps, true).decision, "send", "gate: in-caps autonomous → send");
  eq(M.gateWrite("SCALE", 200, 220, "shadow", caps, true).decision, "shadow", "gate: shadow → shadow");
  eq(M.gateWrite("SCALE", 200, 220, "autonomous", caps, false).decision, "shadow", "gate: no token → shadow");
  eq(M.gateWrite("SCALE", 200, 600, "autonomous", caps, true).decision, "denied", "gate: over budget_cap → denied");
  eq(M.gateWrite("SCALE", 200, 320, "autonomous", caps, true).decision, "denied", "gate: +60% step (>50%) → denied");
  eq(M.gateWrite("PAUSE", 240, 0, "autonomous", caps, true).decision, "send", "gate: PAUSE never capped → send");
  ok(M.guardChange("SCALE", 200, 600, caps)!.includes("budget cap"), "guard: cap message");

  // 3) write path — snapshot → update → verify
  const scale = await M.applyDecision("TKN", "camp_win", "SCALE", { newBudget: 280, label: "win" });
  eq([scale.status, scale.field, scale.new_value], ["applied", "daily_budget", 28000], "apply: SCALE applied ($280→28000c)");
  eq(campaigns["camp_win"].daily_budget, "28000", "apply: store updated");

  const pause = await M.applyDecision("TKN", "camp_lose", "PAUSE", { label: "lose" });
  eq([pause.status, pause.field, pause.new_value], ["applied", "status", "PAUSED"], "apply: PAUSE applied");
  eq(campaigns["camp_lose"].status, "PAUSED", "apply: store paused");

  const idem = await M.applyDecision("TKN", "camp_paused", "PAUSE", {});
  eq(idem.status, "skipped", "apply: already-PAUSED → skipped (idempotent)");

  const stuck = await M.applyDecision("TKN", "camp_stuck", "SCALE", { newBudget: 200 });
  eq(stuck.status, "failed", "apply: post-write mismatch → failed");

  const hold = await M.applyDecision("TKN", "camp_win", "HOLD", {});
  eq(hold.status, "skipped", "apply: HOLD is not a platform write → skipped");

  // 4) OAuth exchange → long-lived token
  const tok = await M.exchangeCode("APPID", "SECRET", "https://x/cb", "CODE");
  eq([tok.token, tok.expiresIn], ["LONG_LIVED_TOKEN", 5184000], "oauth: code → long-lived token");
  const acct = await M.firstAdAccount("LONG_LIVED_TOKEN");
  eq(acct, "999888", "oauth: first ad account discovered");

  // 5) authorize URL shape
  const au = M.authorizeUrl("APPID", "https://fn/meta-oauth", "NONCE");
  ok(au.includes("client_id=APPID") && au.includes("scope=ads_read%2Cads_management") && au.includes("state=NONCE"),
     "oauth: authorize URL has client_id + scopes + state");
} finally {
  server.close();
}

console.log(`\n${fail === 0 ? "✓ ALL PASS" : "✗ FAILURES"}  —  ${pass} passed, ${fail} failed`);
if (fail) { fails.forEach((f) => console.log("   - " + f)); process.exit(1); }
