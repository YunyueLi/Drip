// Apply decisions back to the platform — the real money-moving write, gated
// exactly like the Python path:
//   1. mode  — "shadow" never sends; "copilot"/"autonomous" send.
//   2. caps  — guardChange() blocks over-cap budgets / over-large single steps.
//   3. audit — every outcome (applied|shadow|skipped|denied|failed) is recorded.
//
// POST {
//   platform?: "meta", mode: "shadow"|"copilot"|"autonomous",
//   caps?: { budget_cap?: number, max_change_pct?: number },
//   changes: [{ target_id, action, new_budget?, old_budget?, label? }]
// } → { results: WriteResult[] }
import { json, preflight } from "../_shared/cors.ts";
import { admin, userFromRequest } from "../_shared/auth.ts";
import { applyDecision, type Caps, guardChange, type WriteResult } from "../_shared/meta.ts";

Deno.serve(async (req) => {
  const pre = preflight(req); if (pre) return pre;
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  const user = await userFromRequest(req);
  if (!user) return json({ error: "unauthorized" }, 401);

  const body = await req.json().catch(() => ({})) as Record<string, unknown>;
  const platform = String(body.platform ?? "meta");
  const mode = String(body.mode ?? "shadow");
  const capsIn = (body.caps ?? {}) as Record<string, unknown>;
  const caps: Caps = {
    budget_cap: Number(capsIn.budget_cap ?? 0) || 0,
    max_change_pct: capsIn.max_change_pct == null ? 0.5 : Number(capsIn.max_change_pct),
  };
  const changes = Array.isArray(body.changes) ? body.changes as Array<Record<string, unknown>> : [];
  if (!changes.length) return json({ error: "no changes" }, 400);

  const sb = admin();
  const { data: conn } = await sb.from("ad_connections")
    .select("access_token").eq("user_id", user.id).eq("platform", platform).maybeSingle();
  if (!conn?.access_token && mode !== "shadow") return json({ error: `no ${platform} connection` }, 409);

  const results: WriteResult[] = [];
  for (const c of changes) {
    const action = String(c.action ?? "").toUpperCase();
    const targetId = String(c.target_id ?? "");
    const label = String(c.label ?? "");
    const newBudget = c.new_budget == null ? null : Number(c.new_budget);
    const oldBudget = Number(c.old_budget ?? 0) || 0;

    // money-safety guard (before any network call)
    const denied = guardChange(action, oldBudget, newBudget ?? 0, caps);
    let res: WriteResult;
    if (denied) {
      res = { platform, target_id: targetId, label, action, field: action === "PAUSE" ? "status" : "daily_budget",
        old_value: oldBudget, new_value: newBudget, status: "denied", detail: denied };
    } else if (mode === "shadow" || !conn?.access_token) {
      res = { platform, target_id: targetId, label, action, field: action === "PAUSE" ? "status" : "daily_budget",
        old_value: oldBudget, new_value: action === "PAUSE" ? "PAUSED" : newBudget,
        status: "shadow", detail: "shadow mode — planned, not sent" };
    } else {
      res = await applyDecision(conn.access_token, targetId, action, { newBudget, label });
    }
    results.push(res);

    await sb.from("drip_audit").insert({
      user_id: user.id, platform, target_id: targetId, label, action,
      field: res.field, old_value: String(res.old_value ?? ""), new_value: String(res.new_value ?? ""),
      status: res.status, mode, detail: res.detail,
    });
  }
  return json({ results });
});
