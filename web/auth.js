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
  var sb = null, user = null;

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

  // ---- session → UI ----
  function initials(email) { return (email || "U").trim().charAt(0).toUpperCase(); }
  function paint() {
    var inB = document.querySelector("#acctMenu .am-in");
    var outB = document.querySelector("#acctMenu .am-out");
    if (configured && user) {
      var email = user.email || "";
      var name = (user.user_metadata && (user.user_metadata.name || user.user_metadata.full_name)) || email.split("@")[0] || "User";
      if (inB) inB.style.display = "";
      if (outB) outB.style.display = "none";
      document.querySelectorAll(".am-name").forEach(function (e) { e.textContent = name; });
      document.querySelectorAll(".am-mail").forEach(function (e) { e.textContent = email; });
      document.querySelectorAll(".am-av, #avBtn, .am-head .am-av").forEach(function (e) { e.textContent = initials(email); });
      var sid = document.querySelector(".acct-id"); if (sid) sid.textContent = name;
      // settings account pane
      var rl = document.querySelector('.set-pane[data-spane="account"] .rl'); if (rl) rl.textContent = name;
      var rh = document.querySelector('.set-pane[data-spane="account"] .rh'); if (rh) rh.textContent = email;
    } else if (configured) {
      if (inB) inB.style.display = "none";
      if (outB) outB.style.display = "";
    }
    // else: unconfigured → leave the static mock as-is.
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
  function loginModal() {
    if (!configured) {
      modal('<div class="rp-mhead"><div><div class="rp-mt">登录未配置</div><div class="rp-ms">在 <code>web/config.js</code> 填入你的 Supabase URL 与 anon key（仪表盘 → Project Settings → API）后即可启用邮箱 / Google / GitHub 登录。</div></div><button class="rp-x" onclick="this.closest(\'.rp-back\').remove()">✕</button></div>');
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
  function signOut() { if (sb) sb.auth.signOut().then(function () { toast("已退出"); }); }

  // ---- LLM config modal ----
  function llmModal() {
    var c = getLlm();
    var head = '<div class="rp-mhead"><div><div class="rp-mt">LLM 配置</div><div class="rp-ms">' + (configured && user ? "保存到账号，跨设备漫游。" : "保存在本机。登录后随账号漫游。") + ' 默认 DeepSeek。</div></div><button class="rp-x" id="lmX">✕</button></div>';
    var body = '<label class="auth-f"><span>模型</span><input id="lmModel" placeholder="deepseek-v4-pro" value="' + (c.model || "") + '"></label>' +
      '<div class="auth-chips"><button class="auth-chip" data-mdl="deepseek-v4-pro">deepseek-v4-pro</button><button class="auth-chip" data-mdl="deepseek-v4-flash">deepseek-v4-flash</button></div>' +
      '<label class="auth-f"><span>API Key</span><input id="lmKey" type="password" placeholder="sk-..." value="' + (c.key || "") + '"></label>' +
      '<label class="auth-f"><span>Base URL</span><input id="lmBase" placeholder="https://api.deepseek.com" value="' + (c.base || "") + '"></label>' +
      '<button class="btn primary auth-go" id="lmSave">保存</button>' +
      '<div class="auth-note">🔒 仅存于浏览器' + (configured && user ? " + 你的账号" : "") + '，按请求发往引擎，不落盘。</div>';
    var m = modal(head + body);
    $("lmX").onclick = closeModal;
    m.querySelectorAll("[data-mdl]").forEach(function (b) { b.onclick = function () { $("lmModel").value = b.getAttribute("data-mdl"); }; });
    $("lmSave").onclick = function () {
      var next = { provider: "deepseek", model: ($("lmModel").value || "deepseek-v4-pro").trim(), key: ($("lmKey").value || "").trim(), base: ($("lmBase").value || "https://api.deepseek.com").trim(), updatedAt: Date.now() };
      setLlm(next); pushLlm(next); closeModal(); toast("LLM 配置已保存"); syncLlmForm();
    };
  }
  function syncLlmForm() {
    var c = getLlm();
    document.querySelectorAll("[data-llm-status]").forEach(function (e) {
      e.textContent = c.key ? (c.model || "deepseek-v4-pro") + " 已连接" : "未配置 LLM";
    });
  }

  // ---- inject an "LLM 配置" item into the account menu ----
  function injectMenuItem() {
    var anchor = $("signOut");
    if (anchor && !$("llmCfgItem")) {
      var b = document.createElement("button");
      b.className = "am-item"; b.id = "llmCfgItem";
      b.innerHTML = '<span class="ai">✦</span>LLM 配置 <span class="am-stat" data-llm-status></span>';
      b.onclick = function () { llmModal(); closeAcctMenu(); };
      anchor.parentNode.insertBefore(b, anchor);
    }
  }
  function closeAcctMenu() { var m = $("acctMenu"); if (m) m.classList.remove("open"); }

  // ---- wire ----
  function wire() {
    injectMenuItem();
    var si = $("signIn"); if (si) si.onclick = function () { loginModal(); closeAcctMenu(); };
    var so = $("signOut"); if (so) so.onclick = function () { signOut(); closeAcctMenu(); };
    var sso = $("setSignOut"); if (sso) sso.onclick = signOut;
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
    syncLlmForm();
  }

  function boot() {
    wire();
    if (!configured) { paint(); return; }
    if (!window.supabase || !window.supabase.createClient) { console.warn("[drip] supabase-js not loaded"); return; }
    sb = window.supabase.createClient(cfg.url, cfg.anonKey, {
      auth: { flowType: "pkce", detectSessionInUrl: true, persistSession: true, autoRefreshToken: true, storageKey: "drip-auth" },
    });
    sb.auth.getSession().then(function (r) { user = (r.data.session && r.data.session.user) || null; if (user) pullLlm(user); paint(); });
    sb.auth.onAuthStateChange(function (_e, s) { user = (s && s.user) || null; if (user) pullLlm(user); paint(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  // expose for console/debug
  window.DripAuth = { login: loginModal, llm: llmModal, signOut: signOut, getLlm: getLlm };
})();
