// Pull the signed-in user's REAL campaign insights from a connected platform,
// normalised to AdMetrics. The browser then runs the decision engine (engine.js)
// on this real data. The access token stays server-side.
//
// POST { platform?: "meta", since?: "YYYY-MM-DD", until?: "YYYY-MM-DD" }
//   → { platform, account_id, since, until, metrics: AdMetrics[] }
import { json, preflight } from "../_shared/cors.ts";
import { admin, userFromRequest } from "../_shared/auth.ts";
import { pullInsights } from "../_shared/meta.ts";

function isoDaysAgo(n: number): string {
  return new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
}

Deno.serve(async (req) => {
  const pre = preflight(req); if (pre) return pre;
  const user = await userFromRequest(req);
  if (!user) return json({ error: "unauthorized" }, 401);

  let body: Record<string, unknown> = {};
  try { body = req.method === "POST" ? await req.json() : {}; } catch { /* empty body ok */ }
  const platform = String(body.platform ?? "meta");
  const until = String(body.until ?? isoDaysAgo(1));   // yesterday — today's data is partial
  const since = String(body.since ?? isoDaysAgo(7));

  const sb = admin();
  const { data: conn } = await sb.from("ad_connections")
    .select("access_token, account_id").eq("user_id", user.id).eq("platform", platform).maybeSingle();
  if (!conn?.access_token) return json({ error: `no ${platform} connection — connect it first` }, 409);

  try {
    if (platform !== "meta") return json({ error: `pull not implemented for ${platform} yet` }, 501);
    const metrics = await pullInsights(conn.access_token, conn.account_id, since, until);
    return json({ platform, account_id: conn.account_id, since, until, metrics });
  } catch (e) {
    return json({ error: `${(e as Error).message ?? e}` }, 502);
  }
});
