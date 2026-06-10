// Real account system for app.html — Supabase auth (email · magic link · Google
// · GitHub) + BYOK LLM config that roams with the account (user_metadata).
// Vanilla, static-page friendly (PKCE), so it works on GitHub Pages. Wires into
// the existing account menu (#acctMenu) and Settings. Graceful when unconfigured.
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var cfg = window.DRIP_SUPABASE || {};
  var configured = !!(cfg.url && cfg.anonKey);
  var LLM_KEY = "drip-llm";
  var sb = null, user = null, session = null;

  // ---- derived local keys (what llm.js / engine wiring read) ----
  function getLlm() { try { return JSON.parse(localStorage.getItem(LLM_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function setLlm(c) { try { localStorage.setItem(LLM_KEY, JSON.stringify(c)); } catch (e) {} }
  var TG_KEY = "drip-targets";
  function getTargets() { try { return JSON.parse(localStorage.getItem(TG_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function setTargetsStore(c) { try { localStorage.setItem(TG_KEY, JSON.stringify(c)); } catch (e) {} }
  function applyTargets(c) {
    try { if (window.DripEngine && window.DripEngine.setTargets) window.DripEngine.setTargets(c || {}); } catch (e) {}
  }

  // ---- the Drip account store — one payload, auto-synced with the signed-in
  // account (user_settings table, owner-only RLS). Local cache works offline;
  // newer updatedAt wins on login. Legacy user_metadata is a migration source.
  var ACCT_KEY = "drip-account";
  var lastSync = 0;
  function acctGet() {
    try { var p = JSON.parse(localStorage.getItem(ACCT_KEY) || "null"); if (p && p.v === 1) return p; } catch (e) {}
    var llm = getLlm(), tg = getTargets();  // seed from pre-account local keys
    return { v: 1, updatedAt: Math.max(llm.updatedAt || 0, tg.updatedAt || 0), llm: llm, targets: tg };
  }
  function acctApply(p) {
    try { localStorage.setItem(ACCT_KEY, JSON.stringify(p)); } catch (e) {}
    setLlm(p.llm || {});
    setTargetsStore(p.targets || {});
    applyTargets(p.targets || {});
    syncLlmForm(); syncTargetsForm(); renderAcctHub();
  }
  function acctSave(mutate) {
    var p = acctGet(); mutate(p); p.updatedAt = Date.now();
    acctApply(p); acctPush(p);
  }
  function acctPush(p) {
    if (!sb || !user) return;
    sb.from("user_settings").upsert({ user_id: user.id, data: p, updated_at: new Date().toISOString() })
      .then(function (r) {
        if (r && r.error) { console.warn("[drip] settings sync failed:", r.error.message); toast("云端同步失败 · 已存本机"); }
        else { lastSync = Date.now(); renderAcctHub(); }
      });
  }
  function acctPull(u) {
    sb.from("user_settings").select("data").maybeSingle().then(function (r) {
      var remote = r && r.data && r.data.data;
      var local = acctGet();
      if (!remote) {
        // first login on this account: fold in legacy user_metadata config if any
        var md = (u && u.user_metadata) || {};
        if (!(local.llm && local.llm.key) && md.drip_llm) local.llm = md.drip_llm;
        if (!(local.targets && Object.keys(local.targets).length) && md.drip_targets) local.targets = md.drip_targets;
        acctApply(local); acctPush(local); return;
      }
      if ((remote.updatedAt || 0) >= (local.updatedAt || 0)) { acctApply(remote); lastSync = Date.now(); renderAcctHub(); }
      else { acctApply(local); acctPush(local); }
    });
  }

  // ---- local identity: usable without Supabase; upgrades to cloud when configured ----
  var LOCAL_KEY = "drip-local-user";
  function getLocalUser() { try { var v = JSON.parse(localStorage.getItem(LOCAL_KEY) || "null"); return (v && v.email) ? v : null; } catch (e) { return null; } }
  function setLocalUser(u) { try { localStorage.setItem(LOCAL_KEY, JSON.stringify(u)); } catch (e) {} }
  function clearLocalUser() { try { localStorage.removeItem(LOCAL_KEY); } catch (e) {} }
  function currentUser() {
    if (user) return { email: user.email || "", name: (user.user_metadata && (user.user_metadata.name || user.user_metadata.full_name)) || (user.email || "").split("@")[0] || "User", cloud: true };
    var l = getLocalUser();
    return l ? { email: l.email, name: l.name || l.email.split("@")[0], cloud: false } : null;
  }

  // ---- session → UI (honest: real cloud user, else local user, else logged out) ----
  function initials(email) { return (email || "U").trim().charAt(0).toUpperCase(); }
  function paint() {
    var inB = document.querySelector("#acctMenu .am-in");
    var outB = document.querySelector("#acctMenu .am-out");
    var rl = document.querySelector('.set-pane[data-spane="account"] .rl');
    var rh = document.querySelector('.set-pane[data-spane="account"] .rh');
    var so = $("setSignOut");
    var plan = document.querySelector("#acctMenu .am-plan");
    var sa = document.querySelector(".set-acct");
    var cu = currentUser();
    if (sa) {
      var saAv = sa.querySelector(".av"), saNm = sa.querySelector(".nm"), saPl = sa.querySelector(".pl");
      if (saAv) saAv.textContent = cu ? initials(cu.email) : "?";
      if (saNm) saNm.textContent = cu ? cu.name : "未登录";
      if (saPl) saPl.textContent = cu ? (cu.cloud ? "云端账户 · 配置漫游" : "本机账户") : "个人 · 自托管";
    }
    if (cu) {
      if (inB) inB.style.display = "";
      if (outB) outB.style.display = "none";
      document.querySelectorAll(".am-name").forEach(function (e) { e.textContent = cu.name; });
      document.querySelectorAll(".am-mail").forEach(function (e) { e.textContent = cu.email; });
      document.querySelectorAll(".am-av, #avBtn, .am-head .am-av").forEach(function (e) { e.textContent = initials(cu.email); if (e.classList) e.classList.remove("out"); });
      var sid = document.querySelector(".acct-id"); if (sid) sid.textContent = cu.name;
      if (rl) rl.textContent = cu.name;
      if (rh) rh.textContent = cu.cloud ? cu.email : (cu.email + " · 本机账户");
      if (so) so.style.display = "";
      if (plan) plan.textContent = cu.cloud ? "● 云端账户 · 配置随账号漫游" : "● 本机账户 · 接 Supabase 升级漫游";
    } else {
      if (inB) inB.style.display = "none";
      if (outB) outB.style.display = "";
      document.querySelectorAll("#avBtn").forEach(function (e) { e.textContent = "?"; if (e.classList) e.classList.add("out"); });
      var sid2 = document.querySelector(".acct-id"); if (sid2) sid2.textContent = "登录";
      if (rl) rl.textContent = "未登录";
      if (rh) rh.textContent = configured ? "点右上角账号 → 登录" : "点右上角账号 → 登录（本机即可用）";
      if (so) so.style.display = "none";
    }
    syncLlmForm();
    syncTargetsForm();
    renderAcctHub();
  }

  // ---- toast ----
  function toast(msg) {
    var t = document.createElement("div"); t.className = "auth-toast"; t.textContent = msg;
    document.body.appendChild(t); setTimeout(function () { t.remove(); }, 2600);
  }

  // ---- modal scaffold (reuses .rp-back / .rp-modal) ----
  function modal(html) {
    closeModal();
    var o = document.createElement("div"); o.id = "authModal"; o.className = "rp-back";
    o.innerHTML = '<div class="rp-modal auth-modal">' + html + "</div>";
    document.body.appendChild(o);
    o.addEventListener("click", function (e) { if (e.target === o) closeModal(); });
    return o;
  }
  function closeModal() { var m = $("authModal"); if (m) m.remove(); }

  // ---- login / register ----
  var mode = "signin";
  function localLogin() {
    var email = (($("locEmail") || {}).value || "").trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { var e = $("locErr"); if (e) e.textContent = "填一个有效邮箱"; return; }
    setLocalUser({ email: email, name: (($("locName") || {}).value || "").trim() });
    closeModal(); toast("已登录（本机）"); paint();
  }
  function loginModal() {
    if (!configured) {
      var body = '<div class="rp-mhead"><div><div class="rp-mt">登录 Drip</div><div class="rp-ms">本机登录即可用（存于浏览器）。接 Supabase 后升级为云端漫游 + 可连广告账户。</div></div><button class="rp-x" id="amX2">✕</button></div>' +
        '<label class="auth-f"><span>邮箱</span><input id="locEmail" type="email" placeholder="you@example.com" autocomplete="email"></label>' +
        '<label class="auth-f"><span>昵称（可选）</span><input id="locName" placeholder="你的名字"></label>' +
        '<div id="locErr" class="auth-err"></div>' +
        '<button class="btn primary auth-go" id="locGo">本机登录</button>' +
        '<div class="auth-note">想要云端漫游 + 连接广告账户：创建免费 Supabase 项目，把 URL 与 anon key 填进 <code>web/config.js</code>（见 SETUP-LIVE.md），刷新即变云端登录。</div>';
      modal(body);
      $("amX2").onclick = closeModal;
      $("locGo").onclick = localLogin;
      var le = $("locEmail"); if (le) le.addEventListener("keydown", function (ev) { if (ev.key === "Enter") localLogin(); });
      return;
    }
    var head = '<div class="rp-mhead"><div><div class="rp-mt">' + (mode === "signin" ? "登录 Drip" : "注册 Drip") + '</div><div class="rp-ms">邮箱、魔法链接、Google 或 GitHub。配置随账号漫游。</div></div><button class="rp-x" id="amX">✕</button></div>';
    var tabs = '<div class="auth-tabs"><button data-m="signin" class="' + (mode === "signin" ? "on" : "") + '">登录</button><button data-m="signup" class="' + (mode === "signup" ? "on" : "") + '">注册</button></div>';
    var oauth = '<div class="auth-oauth"><button class="auth-btn" data-oauth="google">G&nbsp; Google</button><button class="auth-btn" data-oauth="github">⌥&nbsp; GitHub</button></div>';
    var div = '<div class="auth-div">或用邮箱</div>';
    var fields = '<label class="auth-f"><span>邮箱</span><input id="amEmail" type="email" placeholder="you@example.com" autocomplete="email"></label>' +
      '<label class="auth-f"><span>密码</span><input id="amPass" type="password" placeholder="••••••••"></label>' +
      '<div id="amErr" class="auth-err"></div>' +
      '<button class="btn primary auth-go" id="amSubmit">' + (mode === "signin" ? "登录" : "创建账号") + '</button>' +
      '<button class="auth-btn" id="amMagic">发送魔法链接</button>';
    var m = modal(head + tabs + oauth + div + fields);
    $("amX").onclick = closeModal;
    m.querySelectorAll(".auth-tabs button").forEach(function (b) { b.onclick = function () { mode = b.getAttribute("data-m"); loginModal(); }; });
    m.querySelectorAll("[data-oauth]").forEach(function (b) { b.onclick = function () { oauthLogin(b.getAttribute("data-oauth")); }; });
    $("amSubmit").onclick = submitPw;
    $("amMagic").onclick = magic;
  }
  function setErr(s) { var e = $("amErr"); if (e) e.textContent = s || ""; }
  function redirectURL() { return location.origin + location.pathname; }

  function submitPw() {
    var email = ($("amEmail") || {}).value, pass = ($("amPass") || {}).value;
    setErr("");
    if (mode === "signin") {
      sb.auth.signInWithPassword({ email: (email || "").trim(), password: pass }).then(function (r) {
        if (r.error) setErr(r.error.message); else { closeModal(); toast("已登录"); }
      });
    } else {
      sb.auth.signUp({ email: (email || "").trim(), password: pass, options: { emailRedirectTo: redirectURL() } }).then(function (r) {
        if (r.error) setErr(r.error.message);
        else if (!r.data.session) { setErr(""); toast("确认邮件已发送，请查收后登录"); closeModal(); }
        else { closeModal(); toast("账号已创建"); }
      });
    }
  }
  function magic() {
    var email = (($("amEmail") || {}).value || "").trim(); setErr("");
    if (!email) return setErr("先填邮箱");
    sb.auth.signInWithOtp({ email: email, options: { emailRedirectTo: redirectURL() } }).then(function (r) {
      r.error ? setErr(r.error.message) : (toast("魔法链接已发送"), closeModal());
    });
  }
  function oauthLogin(provider) {
    sb.auth.signInWithOAuth({ provider: provider, options: { redirectTo: redirectURL() } }).then(function (r) {
      if (r.error) setErr(r.error.message);
    });
  }
  function signOut() {
    clearLocalUser();
    if (sb && user) { sb.auth.signOut().then(function () { toast("已退出"); paint(); }); }
    else { toast("已退出"); paint(); }
  }

  // ---- LLM config (BYOK) — single entry, lives in Settings → 运行与模型 ----
  function syncLlmForm() {
    var c = getLlm();
    document.querySelectorAll("[data-llm-status]").forEach(function (e) {
      e.textContent = c.key ? (c.model || "deepseek-v4-pro") + " 已连接" : "未配置 LLM";
    });
    fillLlmForm();
  }
  function fillLlmForm() {
    var c = getLlm(), m = $("setLlmModel"), k = $("setLlmKey"), b = $("setLlmBase");
    if (m && document.activeElement !== m) m.value = c.model || "";
    if (k && document.activeElement !== k) k.value = c.key || "";
    if (b && document.activeElement !== b) b.value = c.base || "";
  }
  function wireLlmForm() {
    var save = $("setLlmSave");
    if (save && !save._wired) {
      save._wired = true;
      save.onclick = function () {
        var next = {
          provider: "deepseek",
          model: ((($("setLlmModel") || {}).value) || "deepseek-v4-pro").trim(),
          key: ((($("setLlmKey") || {}).value) || "").trim(),
          base: ((($("setLlmBase") || {}).value) || "https://api.deepseek.com").trim(),
          updatedAt: Date.now(),
        };
        acctSave(function (p) { p.llm = next; });
        toast(user ? "LLM 配置已保存 · 已同步到账户" : "LLM 配置已保存（本机）");
      };
    }
    fillLlmForm();
  }

  // ---- targets form — Settings → 运行与模型 → 目标与预算 ----
  function targetsStatus() {
    var c = getTargets(), D = (window.DripEngine && window.DripEngine.DEFAULT_TARGETS) || { cpp_target: 25, roas_target: 3, budget: 1400 };
    var custom = ["cpp_target", "roas_target", "budget"].some(function (k) { var v = Number(c[k]); return isFinite(v) && v > 0 && v !== D[k]; });
    return custom ? "自定义目标生效中" : "使用默认目标";
  }
  function syncTargetsForm() {
    document.querySelectorAll("[data-targets-status]").forEach(function (e) { e.textContent = targetsStatus(); });
    fillTargetsForm();
  }
  function fillTargetsForm() {
    var c = getTargets();
    [["setTgCpp", "cpp_target"], ["setTgRoas", "roas_target"], ["setTgBudget", "budget"]].forEach(function (p) {
      var el = $(p[0]); if (!el || document.activeElement === el) return;
      var v = Number(c[p[1]]);
      el.value = (isFinite(v) && v > 0) ? String(v) : "";
    });
  }
  function wireTargetsForm() {
    var save = $("setTgSave");
    if (save && !save._wired) {
      save._wired = true;
      save.onclick = function () {
        var num = function (id) { var v = Number((($(id) || {}).value || "").trim()); return (isFinite(v) && v > 0) ? v : null; };
        var next = { updatedAt: Date.now() };
        var cpp = num("setTgCpp"), roas = num("setTgRoas"), budget = num("setTgBudget");
        if (cpp) next.cpp_target = cpp;
        if (roas) next.roas_target = roas;
        if (budget) next.budget = budget;
        acctSave(function (p) { p.targets = next; });
        toast(user ? "目标已保存 · 已同步到账户" : "目标已保存（本机）· 留空项用默认");
      };
    }
    fillTargetsForm();
  }
  // ---- account hub — sync status (账户页) + real ad-account list (广告账户页) ----
  function renderAcctHub() {
    var sy = document.querySelector("[data-sync-status]");
    if (sy) {
      if (user) {
        var t = lastSync ? new Date(lastSync).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "";
        sy.innerHTML = '<span style="color:var(--green,#1a7f37)">●</span> 云端自动同步' + (t ? " · 上次 " + t : "");
      } else {
        sy.textContent = "○ 仅本机 — 登录后自动同步";
      }
    }
    renderAcctConns();
  }
  var PLATFORMS = [
    { k: "meta", n: "Meta Ads", ico: "#lg-meta", live: true },
    { k: "tiktok", n: "TikTok Ads", ico: "#lg-tt" },
    { k: "tencent", n: "腾讯广告", ico: "#lg-tencent" },
    { k: "oceanengine", n: "巨量引擎", ico: "#lg-ocean" },
    { k: "kuaishou", n: "快手磁力", ico: "#lg-ks" },
  ];
  function renderAcctConns() {
    var host = $("realConns"); if (!host) return;
    var paintRows = function (by) {
      host.innerHTML = PLATFORMS.map(function (p) {
        var c = by[p.k];
        var badge = c ? '<span class="acct-badge ok">● 已连接</span>' : '<span class="acct-badge off">○ 未连接</span>';
        var tags;
        if (c) tags = '<span class="atag">' + (c.account_id || "已授权") + '</span><span class="atag mut">随账户同步 · 任何设备可用</span>';
        else if (p.live) tags = '<span class="atag mut">' + (user ? "OAuth 授权，拉真实 campaign" : "登录后即可连接") + "</span>";
        else tags = '<span class="atag mut">后端未接入</span>';
        var act;
        if (c) act = '<span style="display:flex;gap:8px"><button class="btn sm" data-conn="' + p.k + '">重新授权</button><button class="btn sm" data-disc="' + p.k + '">断开</button></span>';
        else if (p.live) act = '<button class="btn primary sm" data-conn="' + p.k + '">连接</button>';
        else act = "";
        return '<div class="acct-row"><span class="plogo-tile"><svg class="plogo"><use href="' + p.ico + '"/></svg></span><div class="acct-info"><div class="acct-nm">' + p.n + " " + badge + '</div><div class="acct-tags">' + tags + "</div></div>" + act + "</div>";
      }).join("");
      host.querySelectorAll("[data-conn]").forEach(function (b) {
        b.onclick = function () {
          if (!user) { toast(configured ? "请先登录云端账号" : "需先配置 Supabase（见 SETUP-LIVE.md）"); if (configured) loginModal(); return; }
          var k = b.getAttribute("data-conn");
          if (window.DripLive) window.DripLive.connect(k).catch(function (e) { toast("连接失败：" + (e.message || e)); });
        };
      });
      host.querySelectorAll("[data-disc]").forEach(function (b) {
        b.onclick = function () {
          var k = b.getAttribute("data-disc"), nm = (PLATFORMS.filter(function (p) { return p.k === k; })[0] || {}).n || k;
          if (!confirm("断开 " + nm + "？云端保存的授权将被删除。")) return;
          sb.from("ad_connections").delete().eq("platform", k).then(function (r) {
            toast(r && r.error ? "断开失败：" + r.error.message : "已断开"); renderAcctConns();
          });
        };
      });
    };
    if (!user) { paintRows({}); return; }
    connections().then(function (rows) {
      var by = {}; (rows || []).forEach(function (r) { by[r.platform] = r; });
      paintRows(by);
    });
  }

  function closeAcctMenu() { var m = $("acctMenu"); if (m) m.classList.remove("open"); }

  // ---- wire ----
  function wire() {
    wireLlmForm();
    wireTargetsForm();
    acctApply(acctGet());
    var si = $("signIn"); if (si) si.onclick = function () { loginModal(); closeAcctMenu(); };
    var so = $("signOut"); if (so) so.onclick = function () { signOut(); closeAcctMenu(); };
    var sso = $("setSignOut"); if (sso) sso.onclick = signOut;
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
    syncLlmForm();
    syncTargetsForm();
  }

  // Load supabase-js only when needed (config filled), never blocking the app.
  // Tries China-reachable mirrors first, falls back to jsdelivr.
  function loadScript(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement("script"); s.src = src; s.async = true;
      s.onload = res; s.onerror = function () { rej(new Error(src)); };
      document.head.appendChild(s);
    });
  }
  function ensureSupabase() {
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    var cdns = [
      "https://fastly.jsdelivr.net/npm/@supabase/supabase-js@2",
      "https://gcore.jsdelivr.net/npm/@supabase/supabase-js@2",
      "https://unpkg.com/@supabase/supabase-js@2",
      "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2",
    ];
    return cdns.reduce(function (p, url) { return p.catch(function () { return loadScript(url); }); }, Promise.reject(new Error("init")));
  }

  function boot() {
    wire();
    if (!configured) { paint(); return; }
    ensureSupabase().then(function () {
      if (!window.supabase || !window.supabase.createClient) { console.warn("[drip] supabase-js failed to load"); paint(); return; }
      sb = window.supabase.createClient(cfg.url, cfg.anonKey, {
        auth: { flowType: "pkce", detectSessionInUrl: true, persistSession: true, autoRefreshToken: true, storageKey: "drip-auth" },
      });
      sb.auth.getSession().then(function (r) { session = (r.data && r.data.session) || null; user = (session && session.user) || null; if (user) acctPull(user); paint(); onAuth(); });
      sb.auth.onAuthStateChange(function (_e, s) { session = s || null; user = (s && s.user) || null; if (user) acctPull(user); paint(); onAuth(); });
    }, function () { console.warn("[drip] supabase-js CDN unreachable; staying local"); paint(); });
  }

  // ---- live backend access (Edge Functions) ----
  var authCbs = [];
  function onAuth() { authCbs.forEach(function (fn) { try { fn(user); } catch (e) {} }); }
  function token() { return (session && session.access_token) || null; }
  function connections() {
    if (!sb || !user) return Promise.resolve([]);
    return sb.from("ad_connections").select("platform,account_id,updated_at")
      .then(function (r) { return (r && r.data) || []; }, function () { return []; });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  // expose for console/debug
  window.DripAuth = {
    login: loginModal, signOut: signOut, getLlm: getLlm, setLlm: setLlm,
    getTargets: getTargets, account: acctGet,
    token: token, user: function () { return user; }, configured: function () { return configured; },
    connections: connections, onAuth: function (fn) { authCbs.push(fn); if (user !== null || !configured) { try { fn(user); } catch (e) {} } },
  };
})();
