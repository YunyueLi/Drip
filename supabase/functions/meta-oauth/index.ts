// Meta OAuth connect. Two entry points on the same URL:
//
//   start    — POST/GET ?action=start with the user's Supabase JWT.
//              Mints a CSRF nonce, returns the Meta authorize URL.
//   callback — Meta redirects back here with ?code&state. We exchange the code
//              for a long-lived token SERVER-SIDE (App Secret never leaves here),
//              store it per-user, and bounce the browser back to the app.
//
// Register META_REDIRECT_URI (this function's URL) in the Meta app's OAuth
// settings. Secrets: META_APP_ID, META_APP_SECRET, META_REDIRECT_URI, APP_URL.
import { cors, json, preflight } from "../_shared/cors.ts";
import { admin, userFromRequest } from "../_shared/auth.ts";
import { authorizeUrl, exchangeCode, firstAdAccount } from "../_shared/meta.ts";

const APP_ID = Deno.env.get("META_APP_ID") || "";
const APP_SECRET = Deno.env.get("META_APP_SECRET") || "";
const REDIRECT = Deno.env.get("META_REDIRECT_URI") || "";
const APP_URL = Deno.env.get("APP_URL") || "";

function rnd(): string {
  return [...crypto.getRandomValues(new Uint8Array(18))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  const pre = preflight(req); if (pre) return pre;
  if (!APP_ID || !APP_SECRET || !REDIRECT) return json({ error: "Meta app not configured (set META_APP_ID/SECRET/REDIRECT_URI)" }, 500);

  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const sb = admin();

  // ── callback: Meta → here (no auth header; identify the user via the nonce) ──
  if (code) {
    const state = url.searchParams.get("state") || "";
    const { data: st } = await sb.from("oauth_states").select("user_id").eq("state", state).maybeSingle();
    if (!st) return json({ error: "invalid or expired OAuth state" }, 400);
    try {
      const { token, expiresIn } = await exchangeCode(APP_ID, APP_SECRET, REDIRECT, code);
      const accountId = await firstAdAccount(token);
      await sb.from("ad_connections").upsert({
        user_id: st.user_id, platform: "meta", account_id: accountId, access_token: token,
        scopes: "ads_read,ads_management",
        expires_at: expiresIn ? new Date(Date.now() + expiresIn * 1000).toISOString() : null,
        updated_at: new Date().toISOString(),
      }, { onConflict: "user_id,platform" });
      await sb.from("oauth_states").delete().eq("state", state);
      const back = APP_URL ? `${APP_URL}${APP_URL.includes("?") ? "&" : "?"}connected=meta` : null;
      if (back) return new Response(null, { status: 302, headers: { ...cors, Location: back } });
      return json({ ok: true, platform: "meta", account_id: accountId });
    } catch (e) {
      const back = APP_URL ? `${APP_URL}${APP_URL.includes("?") ? "&" : "?"}connect_error=meta` : null;
      if (back) return new Response(null, { status: 302, headers: { ...cors, Location: back } });
      return json({ error: `${(e as Error).message ?? e}` }, 502);
    }
  }

  // ── start: app → here (needs the user JWT) → returns the authorize URL ──────
  const user = await userFromRequest(req);
  if (!user) return json({ error: "unauthorized" }, 401);
  const state = rnd();
  await sb.from("oauth_states").insert({ state, user_id: user.id, platform: "meta" });
  return json({ url: authorizeUrl(APP_ID, REDIRECT, state) });
});
