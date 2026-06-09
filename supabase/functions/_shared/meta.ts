// Meta Marketing API — server-side port of the Python read/write paths, so the
// browser never touches the access token or the App Secret.
//
//   pull   ← src/drip/collectors.py  MetaInsights._fetch_live
//   apply  ← src/drip/adapters/ads.py  MetaWriter._apply_live
//   guard  ← src/drip/safety.py  guard_change
//
// Graph API v21.0, plain REST (no SDK).

// Graph base is overridable via META_GRAPH_BASE (self-host proxy, or a test
// double). Works under Deno (prod) and Node (tests) — defaults to live Graph.
function graphBase(): string {
  try { const d = (globalThis as { Deno?: { env: { get(k: string): string | undefined } } }).Deno; if (d?.env) return d.env.get("META_GRAPH_BASE") || "https://graph.facebook.com/v21.0"; } catch { /* not deno */ }
  try { const p = (globalThis as { process?: { env: Record<string, string | undefined> } }).process; if (p?.env) return p.env.META_GRAPH_BASE || "https://graph.facebook.com/v21.0"; } catch { /* not node */ }
  return "https://graph.facebook.com/v21.0";
}

export interface AdMetrics {
  platform: string; campaign_id: string; date_start: string; date_end: string;
  spend: number; impressions: number; clicks: number; conversions: number;
  conversion_value: number; reach: number; label: string;
}

function windowDays(since: string, until: string): number {
  const a = Date.parse(since), b = Date.parse(until);
  if (isNaN(a) || isNaN(b)) return 1;
  return Math.max(Math.round((b - a) / 86400000) + 1, 1);
}

// Pull a value out of Meta's actions[]/action_values[] (mirrors _parse_action).
function parseAction(actions: unknown, type: string): number {
  if (!Array.isArray(actions)) return 0;
  let total = 0;
  for (const a of actions as Array<Record<string, unknown>>) {
    const at = String(a.action_type ?? "");
    if (at === type || at.endsWith(`.${type}`) || at === "offsite_conversion.fb_pixel_purchase") {
      total += Number(a.value ?? 0) || 0;
    }
  }
  return total;
}

// Campaign-level insights → per-day AdMetrics (cumulative window ÷ days).
export async function pullInsights(
  token: string, accountId: string, since: string, until: string,
): Promise<AdMetrics[]> {
  const acct = accountId.startsWith("act_") ? accountId : `act_${accountId}`;
  const params = new URLSearchParams({
    level: "campaign",
    time_range: JSON.stringify({ since, until }),
    action_attribution_windows: JSON.stringify(["1d_view", "7d_click"]),
    fields: "campaign_id,campaign_name,spend,impressions,clicks,reach,actions,action_values",
    limit: "200",
    access_token: token,
  });
  const resp = await fetch(`${graphBase()}/${acct}/insights?${params}`);
  const data = await resp.json();
  if (!resp.ok) throw new Error(`meta insights ${resp.status}: ${JSON.stringify(data?.error ?? data).slice(0, 300)}`);
  const days = windowDays(since, until);
  const rows: AdMetrics[] = [];
  for (const r of (data.data ?? []) as Array<Record<string, unknown>>) {
    const conv = parseAction(r.actions, "purchase");
    const convVal = parseAction(r.action_values, "purchase");
    rows.push({
      platform: "meta",
      campaign_id: String(r.campaign_id ?? ""),
      date_start: since, date_end: until,
      spend: (Number(r.spend ?? 0) || 0) / days,
      impressions: Math.round((Number(r.impressions ?? 0) || 0) / days),
      clicks: Math.round((Number(r.clicks ?? 0) || 0) / days),
      conversions: conv / days,
      conversion_value: convVal / days,
      reach: Number(r.reach ?? 0) || 0,
      label: String(r.campaign_name ?? r.campaign_id ?? ""),
    });
  }
  return rows;
}

// ── money-safety guard (port of safety.guard_change) ─────────────────────────
const BUDGET_ACTIONS = new Set(["SCALE", "REDUCE"]);
export interface Caps { budget_cap: number; max_change_pct: number; }

export function guardChange(action: string, oldBudget: number, newBudget: number, caps: Caps): string | null {
  if (!BUDGET_ACTIONS.has(action.toUpperCase())) return null;
  if (caps.budget_cap && newBudget > caps.budget_cap) {
    return `new daily budget $${newBudget.toFixed(2)} exceeds budget cap $${caps.budget_cap.toFixed(2)}`;
  }
  if (oldBudget > 0 && caps.max_change_pct) {
    const change = Math.abs(newBudget - oldBudget) / oldBudget;
    if (change > caps.max_change_pct + 1e-9) {
      return `single-step change ${Math.round(change * 100)}% exceeds max ${Math.round(caps.max_change_pct * 100)}% ` +
        `— a jump this large resets the platform learning phase; split it into smaller steps`;
    }
  }
  return null;
}

// Decide one change BEFORE any network call (pure → unit-testable):
//   denied → a money-safety cap blocked it
//   shadow → shadow mode (or no token): plan only, never send
//   send   → write it
export function gateWrite(
  action: string, oldBudget: number, newBudget: number, mode: string, caps: Caps, hasToken: boolean,
): { decision: "denied" | "shadow" | "send"; detail: string } {
  const denied = guardChange(action, oldBudget, newBudget, caps);
  if (denied) return { decision: "denied", detail: denied };
  if (mode === "shadow" || !hasToken) return { decision: "shadow", detail: "shadow mode — planned, not sent" };
  return { decision: "send", detail: "" };
}

const cents = (a: number | null | undefined) => (a == null ? null : Math.round(Number(a) * 100));

export interface WriteResult {
  platform: string; target_id: string; label: string; action: string;
  field: string; old_value: unknown; new_value: unknown;
  status: string; detail: string;
}

// Push one decision to Meta (port of MetaWriter.apply_decision/_apply_live).
// Snapshots → updates → re-reads to confirm. Never throws (errors → failed).
export async function applyDecision(
  token: string, targetId: string, action: string,
  opts: { newBudget?: number | null; label?: string; level?: string } = {},
): Promise<WriteResult> {
  action = action.toUpperCase();
  const level = opts.level ?? "campaign"; // reserved; both campaign/adset hit /{id}
  const res: WriteResult = {
    platform: "meta", target_id: targetId, label: opts.label ?? "", action,
    field: "", old_value: null, new_value: null, status: "shadow", detail: "",
  };
  const isPause = action === "PAUSE";
  const isBudget = action === "SCALE" || action === "REDUCE";
  if (!isPause && !isBudget) { res.status = "skipped"; res.detail = `${action} is not a platform write`; return res; }
  res.field = isPause ? "status" : "daily_budget";
  res.new_value = isPause ? "PAUSED" : cents(opts.newBudget ?? null);

  try {
    const snap = await fetch(`${graphBase()}/${targetId}?fields=name,status,daily_budget&access_token=${token}`).then((r) => r.json());
    if (snap.error) throw new Error(JSON.stringify(snap.error).slice(0, 300));
    res.old_value = isPause ? snap.status : snap.daily_budget;
    if (isPause && String(res.old_value) === "PAUSED") {
      res.status = "skipped"; res.detail = "already PAUSED (idempotent)"; return res;
    }
    const body = new URLSearchParams(
      isPause ? { status: "PAUSED", access_token: token }
              : { daily_budget: String(res.new_value), access_token: token },
    );
    const upd = await fetch(`${graphBase()}/${targetId}`, { method: "POST", body }).then((r) => r.json());
    if (upd.error) throw new Error(JSON.stringify(upd.error).slice(0, 300));
    const after = await fetch(`${graphBase()}/${targetId}?fields=status,daily_budget&access_token=${token}`).then((r) => r.json());
    const got = isPause ? after.status : after.daily_budget;
    if (String(got) === String(res.new_value)) { res.status = "applied"; }
    else { res.status = "failed"; res.detail = `post-write ${got} != intended ${res.new_value}`; }
  } catch (exc) {
    res.status = "failed"; res.detail = `${(exc as Error).message ?? exc}`;
  }
  return res;
}

// ── OAuth (Meta) ─────────────────────────────────────────────────────────────
export function authorizeUrl(appId: string, redirect: string, state: string): string {
  const p = new URLSearchParams({
    client_id: appId, redirect_uri: redirect, state,
    scope: "ads_read,ads_management", response_type: "code",
  });
  return `https://www.facebook.com/v21.0/dialog/oauth?${p}`;
}

export async function exchangeCode(
  appId: string, secret: string, redirect: string, code: string,
): Promise<{ token: string; expiresIn: number }> {
  const short = await fetch(`${graphBase()}/oauth/access_token?` + new URLSearchParams({
    client_id: appId, client_secret: secret, redirect_uri: redirect, code,
  })).then((r) => r.json());
  if (short.error || !short.access_token) throw new Error(JSON.stringify(short.error ?? short).slice(0, 300));
  // upgrade to a long-lived (~60d) token
  const long = await fetch(`${graphBase()}/oauth/access_token?` + new URLSearchParams({
    grant_type: "fb_exchange_token", client_id: appId, client_secret: secret, fb_exchange_token: short.access_token,
  })).then((r) => r.json());
  const token = long.access_token || short.access_token;
  const expiresIn = Number(long.expires_in ?? short.expires_in ?? 0);
  return { token, expiresIn };
}

// Pick the first ad account the token can see (so the user needn't paste an ID).
export async function firstAdAccount(token: string): Promise<string> {
  const r = await fetch(`${graphBase()}/me/adaccounts?fields=account_id,name&limit=1&access_token=${token}`).then((x) => x.json());
  const acct = r?.data?.[0];
  return acct ? String(acct.account_id ?? acct.id ?? "") : "";
}
