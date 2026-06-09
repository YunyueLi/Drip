/* Local dev backend for end-to-end browser testing WITHOUT a Supabase project
 * or a real Meta app. It serves the same three endpoints the Edge Functions do
 * (ads-pull / ads-apply / meta-oauth) by calling the REAL shared logic in
 * supabase/functions/_shared/meta.ts, against an in-memory fake Meta Graph.
 *
 *   node --experimental-strip-types scripts/dev_backend.ts [port]
 *
 * Point the static app at it:  window.DRIP_FN_BASE = "http://127.0.0.1:8787/functions/v1/"
 * Only Supabase (auth/db) and Meta are stubbed; the function logic is real.
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

const PORT = Number(process.argv[2] || 8787);

// ── fake Meta Graph: 7 campaigns (5 healthy → SCALE, 2 struggling → PAUSE) ───
type Camp = { name: string; status: string; daily_budget: string };
const store: Record<string, Camp> = {};
const insights: Array<Record<string, unknown>> = [];
function addCampaign(id: string, name: string, healthy: boolean) {
  // cumulative over an 8-day window; ÷8 → per-day (200/12/760 vs 240/6/336)
  const v = healthy
    ? { spend: "1600", imps: "800000", clicks: "11200", reach: "56000", purch: "96", val: "6080", budget: "20000" }
    : { spend: "1920", imps: "800000", clicks: "6400", reach: "40000", purch: "48", val: "2688", budget: "24000" };
  store[id] = { name, status: "ACTIVE", daily_budget: v.budget };
  insights.push({
    campaign_id: id, campaign_name: name, spend: v.spend, impressions: v.imps, clicks: v.clicks, reach: v.reach,
    actions: [{ action_type: "purchase", value: v.purch }], action_values: [{ action_type: "purchase", value: v.val }],
  });
}
["Meta_Prospecting_v3", "TikTok_Prospecting_v3", "Tencent_Prospecting", "OE_Prospecting", "KS_Prospecting"]
  .forEach((n, i) => addCampaign(`camp_win_${i}`, n, true));
["Meta_Broad_v1", "TikTok_Broad_v1"].forEach((n, i) => addCampaign(`camp_lose_${i}`, n, false));
const initial: Record<string, Camp> = JSON.parse(JSON.stringify(store)); // snapshot for /reset

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};
function send(res: ServerResponse, code: number, body: unknown) {
  res.writeHead(code, { "content-type": "application/json", ...CORS });
  res.end(JSON.stringify(body));
}
function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((r) => { let s = ""; req.on("data", (c) => (s += c)); req.on("end", () => r(s)); });
}

const audit: unknown[] = [];
const CONN = { token: "DEV_TOKEN", account_id: "999888" }; // pre-seeded "connected" account

const server = createServer(async (req, res) => {
  const u = new URL(req.url || "", `http://127.0.0.1:${PORT}`);
  const path = u.pathname;
  if (req.method === "OPTIONS") { res.writeHead(204, CORS); return res.end(); }

  // ── fake Meta Graph (META_GRAPH_BASE points here) ──────────────────────────
  if (path.startsWith("/graph")) {
    if (path.endsWith("/insights")) return send(res, 200, { data: insights });
    if (path.endsWith("/oauth/access_token")) {
      const grant = u.searchParams.get("grant_type");
      return send(res, 200, grant === "fb_exchange_token"
        ? { access_token: "LONG_LIVED", expires_in: 5184000 } : { access_token: "SHORT", expires_in: 3600 });
    }
    if (path.endsWith("/me/adaccounts")) return send(res, 200, { data: [{ account_id: "999888", name: "Dev Account" }] });
    const id = path.split("/").filter(Boolean).pop() || "";
    const c = store[id];
    if (!c) return send(res, 400, { error: { message: `unknown ${id}` } });
    if (req.method === "POST") {
      const b = new URLSearchParams(await readBody(req));
      if (b.has("status")) c.status = b.get("status")!;
      if (b.has("daily_budget")) c.daily_budget = b.get("daily_budget")!;
      return send(res, 200, { success: true });
    }
    return send(res, 200, { id, name: c.name, status: c.status, daily_budget: c.daily_budget });
  }

  // ── Edge-Function endpoints (real meta.ts logic) ───────────────────────────
  if (path.endsWith("/functions/v1/meta-oauth")) {
    return send(res, 200, { url: M.authorizeUrl("DEV_APP", `http://127.0.0.1:${PORT}/functions/v1/meta-oauth`, "devnonce") });
  }
  if (path.endsWith("/functions/v1/ads-pull")) {
    const body = JSON.parse(await readBody(req) || "{}");
    const until = body.until || new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const since = body.since || new Date(Date.now() - 8 * 86400000).toISOString().slice(0, 10);
    const metrics = await M.pullInsights(CONN.token, CONN.account_id, since, until);
    return send(res, 200, { platform: "meta", account_id: CONN.account_id, since, until, metrics });
  }
  if (path.endsWith("/functions/v1/ads-apply")) {
    const body = JSON.parse(await readBody(req) || "{}");
    const mode = String(body.mode || "shadow");
    const caps = { budget_cap: Number(body.caps?.budget_cap || 0) || 0, max_change_pct: body.caps?.max_change_pct == null ? 0.5 : Number(body.caps.max_change_pct) };
    const results: unknown[] = [];
    for (const c of (body.changes || [])) {
      const action = String(c.action || "").toUpperCase();
      const gate = M.gateWrite(action, Number(c.old_budget || 0), Number(c.new_budget || 0), mode, caps, true);
      let r;
      if (gate.decision === "send") r = await M.applyDecision(CONN.token, String(c.target_id), action, { newBudget: c.new_budget, label: c.label });
      else r = { platform: "meta", target_id: c.target_id, label: c.label, action, field: action === "PAUSE" ? "status" : "daily_budget", old_value: c.old_budget, new_value: action === "PAUSE" ? "PAUSED" : c.new_budget, status: gate.decision, detail: gate.detail };
      results.push(r);
      audit.push({ ts: new Date().toISOString(), mode, ...r });
    }
    return send(res, 200, { results });
  }
  if (path.endsWith("/audit")) return send(res, 200, { audit });
  if (path.endsWith("/reset")) { Object.keys(store).forEach((k) => { store[k] = { ...initial[k] }; }); audit.length = 0; return send(res, 200, { ok: true }); }
  return send(res, 404, { error: "not found" });
});

process.env.META_GRAPH_BASE = `http://127.0.0.1:${PORT}/graph`;
const M = await import("../supabase/functions/_shared/meta.ts");
server.listen(PORT, () => console.log(`dev backend on http://127.0.0.1:${PORT}  (META_GRAPH_BASE=${process.env.META_GRAPH_BASE})`));
