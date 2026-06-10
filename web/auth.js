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

  // ---- LLM config (BYOK) — local + account roaming ----
  function getLlm() { try { return JSON.parse(localStorage.getItem(LLM_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function setLlm(c) { try { localStorage.setItem(LLM_KEY, JSON.stringify(c)); } catch (e) {} }
  function pushLlm(c) { if (sb && user) sb.auth.updateUser({ data: { drip_llm: c } }).then(function (r) { console.info("[drip] LLM config →account", r && r.error ? r.error.message : "ok"); }); }
  function pullLlm(u) {
    var remote = (u && u.user_metadata && u.user_metadata.drip_llm) || null;
    var local = getLlm();
    if (remote && (remote.updatedAt || 0) >= (local.updatedAt || 0)) { setLlm(remote); return remote; }
    return local;
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
    var cu = currentUser();
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
        setLlm(next); pushLlm(next); toast("LLM 配置已保存"); syncLlmForm();
      };
    }
    fillLlmForm();
  }
  function closeAcctMenu() { var m = $("acctMenu"); if (m) m.classList.remove("open"); }

  // ---- wire ----
  function wire() {
    wireLlmForm();
    var si = $("signIn"); if (si) si.onclick = function () { loginModal(); closeAcctMenu(); };
    var so = $("signOut"); if (so) so.onclick = function () { signOut(); closeAcctMenu(); };
    var sso = $("setSignOut"); if (sso) sso.onclick = signOut;
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
    syncLlmForm();
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
      sb.auth.getSession().then(function (r) { session = (r.data && r.data.session) || null; user = (session && session.user) || null; if (user) pullLlm(user); paint(); onAuth(); });
      sb.auth.onAuthStateChange(function (_e, s) { session = s || null; user = (s && s.user) || null; if (user) pullLlm(user); paint(); onAuth(); });
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
    token: token, user: function () { return user; }, configured: function () { return configured; },
    connections: connections, onAuth: function (fn) { authCbs.push(fn); if (user !== null || !configured) { try { fn(user); } catch (e) {} } },
  };
})();
