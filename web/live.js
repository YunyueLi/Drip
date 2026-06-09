/* Live backend client — talks to the Supabase Edge Functions so the static app
 * can connect real ad accounts, pull real insights, and write budgets back.
 *
 *   DripLive.connect("meta")         → OAuth redirect to the platform
 *   DripLive.connections()           → [{platform, account_id, updated_at}]
 *   DripLive.pull({platform,since,until}) → { metrics: AdMetrics[] }
 *   DripLive.apply(changes, mode, caps)   → { results: WriteResult[] }
 *
 * Tokens never touch the browser — the functions hold them. Requires a
 * configured Supabase project (web/config.js) and a signed-in user.
 */
(function () {
  "use strict";
  var cfg = window.DRIP_SUPABASE || {};
  // DRIP_FN_BASE overrides the function endpoint (self-host proxy, or local dev).
  function base() { return window.DRIP_FN_BASE || ((cfg.url || "").replace(/\/+$/, "") + "/functions/v1/"); }
  function ready() {
    var tok = window.DripAuth && window.DripAuth.token && window.DripAuth.token();
    return !!((window.DRIP_FN_BASE || (cfg.url && cfg.anonKey)) && tok);
  }

  function headers() {
    var tok = window.DripAuth && window.DripAuth.token && window.DripAuth.token();
    return { "content-type": "application/json", "apikey": cfg.anonKey || "", "Authorization": "Bearer " + (tok || "") };
  }
  function call(name, body, method) {
    return fetch(base() + name, { method: method || "POST", headers: headers(), body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.text().then(function (t) {
        var d; try { d = JSON.parse(t); } catch (e) { d = { error: t.slice(0, 300) }; }
        if (!r.ok) throw new DripLiveError(d && d.error || (name + " " + r.status), r.status);
        return d;
      }); });
  }
  function DripLiveError(msg, status) { this.name = "DripLiveError"; this.message = msg; this.status = status; }
  DripLiveError.prototype = Object.create(Error.prototype);

  // start OAuth: ask the function for the authorize URL, then redirect there
  function connect(platform) {
    if (!ready()) return Promise.reject(new DripLiveError("先登录并配置 Supabase", 401));
    return call((platform || "meta") + "-oauth", { action: "start" }).then(function (d) {
      if (d && d.url) location.href = d.url; else throw new DripLiveError("无法发起授权", 500);
    });
  }
  function connections() { return window.DripAuth ? window.DripAuth.connections() : Promise.resolve([]); }
  function pull(opts) { return call("ads-pull", opts || { platform: "meta" }); }
  function apply(changes, mode, caps) { return call("ads-apply", { platform: "meta", mode: mode || "shadow", caps: caps || {}, changes: changes || [] }); }

  // surface the OAuth round-trip result (meta-oauth redirects back with these)
  function consumeReturn() {
    try {
      var p = new URLSearchParams(location.search);
      var ok = p.get("connected"), err = p.get("connect_error");
      if (ok || err) {
        var t = window.showToast || function (m) { console.info("[drip]", m); };
        t(ok ? (ok + " 账户已连接") : (err + " 连接失败"));
        p.delete("connected"); p.delete("connect_error");
        history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash);
        return ok || ("error:" + err);
      }
    } catch (e) {}
    return null;
  }

  // ---- wire the 连接器 pane (Meta connect button + connected badge) ----
  function refreshConnUI() {
    var badge = document.getElementById("metaBadge"), acct = document.getElementById("metaAcct"),
        btn = document.getElementById("metaConnect");
    if (!badge) return;
    var authed = window.DripAuth && window.DripAuth.token && window.DripAuth.token();
    if (!authed) { badge.textContent = "○ 未连接"; badge.className = "acct-badge off"; if (btn) btn.textContent = "连接"; return; }
    connections().then(function (rows) {
      var meta = (rows || []).filter(function (r) { return r.platform === "meta"; })[0];
      if (meta) {
        badge.textContent = "● 已连接"; badge.className = "acct-badge ok";
        if (acct) acct.textContent = meta.account_id ? ("act_" + String(meta.account_id).replace(/^act_/, "")) : "已授权";
        if (btn) btn.textContent = "重新授权";
      } else {
        badge.textContent = "○ 未连接"; badge.className = "acct-badge off";
        if (btn) btn.textContent = "连接";
      }
    });
  }
  function wireConnUI() {
    var btn = document.getElementById("metaConnect");
    if (btn && !btn._wired) {
      btn._wired = true;
      btn.onclick = function () {
        if (!window.DripAuth || !window.DripAuth.token || !window.DripAuth.token()) {
          (window.showToast || alert)("请先登录"); if (window.DripAuth) window.DripAuth.login(); return;
        }
        connect("meta").catch(function (e) { (window.showToast || alert)("连接失败：" + (e.message || e)); });
      };
    }
    refreshConnUI();
  }

  window.DripLive = {
    ready: ready, connect: connect, connections: connections, pull: pull, apply: apply,
    consumeReturn: consumeReturn, refreshConnUI: refreshConnUI, Error: DripLiveError,
  };
  function init() { consumeReturn(); wireConnUI(); if (window.DripAuth && window.DripAuth.onAuth) window.DripAuth.onAuth(refreshConnUI); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
