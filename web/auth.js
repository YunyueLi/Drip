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
      var amN = document.querySelector("#acctMenu .am-name"); if (amN) amN.textContent = cu.cloud ? "已登录" : "本机账户";
      var amM = document.querySelector("#acctMenu .am-mail"); if (amM) amM.textContent = cu.email;
      var amD = document.querySelector("#acctMenu .am-dot"); if (amD) amD.classList.toggle("off", !cu.cloud);
      document.querySelectorAll("#avBtn").forEach(function (e) { e.textContent = initials(cu.email); if (e.classList) e.classList.remove("out"); });
      var sid = document.querySelector(".acct-id"); if (sid) sid.textContent = cu.name;
      if (rl) rl.textContent = cu.name;
      if (rh) rh.textContent = cu.cloud ? cu.email : (cu.email + " · 本机账户");
      if (so) so.style.display = "";
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
  function emailOk(v) { return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v || ""); }
  // Supabase errors → plain Chinese with a way forward
  function zhErr(e) {
    var m = String((e && e.message) || e || "");
    if (/invalid login credentials/i.test(m)) return "邮箱或密码不对";
    if (/email not confirmed/i.test(m)) return "邮箱还没验证 —— 先去邮箱点一下确认链接";
    if (/already registered|already been registered|already exists/i.test(m)) return "这个邮箱已经注册过了，直接登录就行";
    if (/at least 6 characters|password.*short/i.test(m)) return "密码至少要 6 位";
    if (/only request this after|rate limit|too many requests/i.test(m)) return "操作太频繁，稍等几秒再试";
    if (/unsupported provider|provider is not enabled/i.test(m)) return "这个登录方式暂未开通，先用邮箱登录吧";
    if (/unable to validate email|invalid format/i.test(m)) return "邮箱格式不对";
    if (/failed to fetch|network|load failed/i.test(m)) return "网络不通，稍后再试";
    return m || "出错了，稍后再试";
  }
  function busyBtn(b, txt) { if (b) { b._label = b.textContent; b.disabled = true; b.textContent = txt; } }
  function freeBtn(b) { if (b) { b.disabled = false; if (b._label) b.textContent = b._label; } }
  function wirePwShow(btnId, inputId) {
    var b = $(btnId); if (!b) return;
    b.onclick = function () {
      var p = $(inputId); if (!p) return;
      var show = p.type === "password";
      p.type = show ? "text" : "password";
      b.textContent = show ? "隐藏" : "显示";
      p.focus();
    };
  }

  function localLogin() {
    var email = (($("locEmail") || {}).value || "").trim();
    if (!emailOk(email)) { var e = $("locErr"); if (e) e.textContent = "邮箱格式不对"; return; }
    setLocalUser({ email: email, name: (($("locName") || {}).value || "").trim() });
    closeModal(); toast("已登录（本机）"); paint();
  }

  function loginModal() {
    if (!configured) {
      modal('<button class="auth-x" id="amX2" aria-label="关闭">✕</button>' +
        '<div class="auth-title">登录</div>' +
        '<div class="auth-sub">还没接云端，先用本机账户 —— 数据只存在这台电脑。</div>' +
        '<label class="auth-f"><span>邮箱</span><input id="locEmail" type="email" placeholder="you@example.com" autocomplete="email" inputmode="email"></label>' +
        '<label class="auth-f"><span>昵称（可选）</span><input id="locName" placeholder="你的名字"></label>' +
        '<div id="locErr" class="auth-err" role="alert"></div>' +
        '<button class="btn primary auth-go" id="locGo">进入 Drip</button>');
      $("amX2").onclick = closeModal;
      $("locGo").onclick = localLogin;
      ["locEmail", "locName"].forEach(function (id) {
        var el = $(id); if (el) el.addEventListener("keydown", function (ev) { if (ev.key === "Enter") localLogin(); });
      });
      var le0 = $("locEmail"); if (le0) le0.focus();
      return;
    }
    var gh = '<svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';
    var mail = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>';
    var m = modal(
      '<button class="auth-x" id="amX" aria-label="关闭">✕</button>' +
      '<div class="auth-title" id="amTitle">登录</div>' +
      '<div class="auth-tabs" id="amTabs"><button data-m="signin">登录</button><button data-m="signup">注册</button></div>' +
      '<div id="amBody">' +
        '<label class="auth-f"><span>邮箱</span><input id="amEmail" type="email" placeholder="you@example.com" autocomplete="email" inputmode="email"></label>' +
        '<label class="auth-f"><span>密码</span><span class="auth-pw"><input id="amPass" type="password" placeholder="••••••••" autocomplete="current-password"><button type="button" class="auth-show" id="amShow">显示</button></span></label>' +
        '<div class="auth-row" id="amForgotRow"><button type="button" class="auth-link" id="amForgot">忘记密码？</button></div>' +
        '<div id="amErr" class="auth-err" role="alert"></div>' +
        '<button class="btn primary auth-go" id="amSubmit">登录</button>' +
        '<div class="auth-div">或</div>' +
        '<div class="auth-alt">' +
          '<button class="auth-btn" id="amMagic">' + mail + "用邮箱发送登录链接</button>" +
          '<button class="auth-btn" data-oauth="google"><span class="auth-gi">G</span>用 Google 继续</button>' +
          '<button class="auth-btn" data-oauth="github">' + gh + "用 GitHub 继续</button>" +
        "</div>" +
        '<div class="auth-note">登录后，你的配置在任何设备自动同步。</div>' +
      "</div>" +
      '<div id="amDone" class="auth-done" style="display:none">' +
        '<div class="adn-ic"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m4.5 12.5 5 5 10-11"/></svg></div>' +
        '<div class="adn-t" id="adnT"></div><div class="adn-d" id="adnD"></div>' +
        '<button class="btn primary auth-go" id="adnOk">好</button>' +
      "</div>"
    );
    // switching tabs updates labels in place — the modal is never rebuilt,
    // so no flicker and typed input survives
    function setMode(next) {
      mode = next;
      $("amTitle").textContent = mode === "signin" ? "登录" : "注册";
      $("amSubmit").textContent = mode === "signin" ? "登录" : "创建账户";
      var p = $("amPass"); if (p) p.setAttribute("autocomplete", mode === "signin" ? "current-password" : "new-password");
      var fr = $("amForgotRow"); if (fr) fr.style.display = mode === "signin" ? "" : "none";
      m.querySelectorAll("#amTabs button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-m") === mode); });
      setErr("");
    }
    function showDone(t, d) {
      ["amTitle", "amTabs", "amBody"].forEach(function (id) { var el = $(id); if (el) el.style.display = "none"; });
      $("amDone").style.display = "";
      $("adnT").textContent = t; $("adnD").textContent = d;
      $("adnOk").onclick = closeModal;
    }
    m._showDone = showDone;
    $("amX").onclick = closeModal;
    m.querySelectorAll("#amTabs button").forEach(function (b) { b.onclick = function () { setMode(b.getAttribute("data-m")); }; });
    wirePwShow("amShow", "amPass");
    $("amSubmit").onclick = submitPw;
    $("amMagic").onclick = magic;
    $("amForgot").onclick = forgot;
    m.querySelectorAll("[data-oauth]").forEach(function (b) {
      b.onclick = function () {
        setErr("");
        sb.auth.signInWithOAuth({ provider: b.getAttribute("data-oauth"), options: { redirectTo: redirectURL() } }).then(function (r) {
          if (r.error) setErr(zhErr(r.error));
        });
      };
    });
    ["amEmail", "amPass"].forEach(function (id) {
      var el = $(id); if (el) el.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submitPw(); });
    });
    setMode(mode);
    var e0 = $("amEmail"); if (e0) e0.focus();
  }
  function setErr(s) { var e = $("amErr"); if (e) e.textContent = s || ""; }
  function redirectURL() { return location.origin + location.pathname; }
  function curDone() { var mm = $("authModal"); return mm && mm._showDone; }

  function submitPw() {
    var email = (($("amEmail") || {}).value || "").trim(), pass = ($("amPass") || {}).value || "";
    setErr("");
    if (!emailOk(email)) return setErr("邮箱格式不对");
    if (!pass) return setErr(mode === "signin" ? "请输入密码" : "给账户设一个密码（至少 6 位）");
    var b = $("amSubmit");
    busyBtn(b, mode === "signin" ? "登录中…" : "创建中…");
    if (mode === "signin") {
      sb.auth.signInWithPassword({ email: email, password: pass }).then(function (r) {
        if (r.error) { freeBtn(b); setErr(zhErr(r.error)); }
        else { closeModal(); toast("已登录"); }
      });
    } else {
      sb.auth.signUp({ email: email, password: pass, options: { emailRedirectTo: redirectURL() } }).then(function (r) {
        freeBtn(b);
        if (r.error) setErr(zhErr(r.error));
        else if (!r.data.session) { var sd = curDone(); if (sd) sd("确认邮件已发送", "已发到 " + email + "。点开邮件里的链接完成注册，然后回来登录。"); }
        else { closeModal(); toast("账户已创建"); }
      });
    }
  }
  function magic() {
    var email = (($("amEmail") || {}).value || "").trim();
    setErr("");
    if (!emailOk(email)) return setErr("先在上面填好邮箱");
    var b = $("amMagic");
    busyBtn(b, "发送中…");
    sb.auth.signInWithOtp({ email: email, options: { emailRedirectTo: redirectURL() } }).then(function (r) {
      freeBtn(b);
      if (r.error) setErr(zhErr(r.error));
      else { var sd = curDone(); if (sd) sd("登录链接已发送", "已发到 " + email + "。在这台设备打开邮件里的链接，就直接登录了。"); }
    });
  }
  function forgot() {
    var email = (($("amEmail") || {}).value || "").trim();
    setErr("");
    if (!emailOk(email)) return setErr("先在上面填好邮箱，再点忘记密码");
    sb.auth.resetPasswordForEmail(email, { redirectTo: redirectURL() }).then(function (r) {
      if (r.error) setErr(zhErr(r.error));
      else { var sd = curDone(); if (sd) sd("重置邮件已发送", "去 " + email + " 收信，点开链接后回到这里设置新密码。"); }
    });
  }
  // arriving from the reset email → Supabase fires PASSWORD_RECOVERY → ask for a new password
  function recoveryModal() {
    modal('<div class="auth-title">设置新密码</div>' +
      '<label class="auth-f"><span>新密码</span><span class="auth-pw"><input id="rcPass" type="password" placeholder="至少 6 位" autocomplete="new-password"><button type="button" class="auth-show" id="rcShow">显示</button></span></label>' +
      '<div id="rcErr" class="auth-err" role="alert"></div>' +
      '<button class="btn primary auth-go" id="rcGo">保存并登录</button>');
    wirePwShow("rcShow", "rcPass");
    $("rcGo").onclick = function () {
      var v = ($("rcPass") || {}).value || "";
      var err = $("rcErr");
      if (v.length < 6) { if (err) err.textContent = "密码至少要 6 位"; return; }
      var b = $("rcGo");
      busyBtn(b, "保存中…");
      sb.auth.updateUser({ password: v }).then(function (r) {
        if (r.error) { freeBtn(b); if (err) err.textContent = zhErr(r.error); }
        else { closeModal(); toast("密码已更新，已登录"); }
      });
    };
    var p0 = $("rcPass"); if (p0) p0.focus();
  }
  function signOut() {
    clearLocalUser();
    if (sb && user) { sb.auth.signOut().then(function () { toast("已退出"); paint(); }); }
    else { toast("已退出"); paint(); }
  }

  // ---- LLM config (BYOK) — Settings → LLM 接口 ----
  // Providers verified CORS-open for browser /models + /chat/completions (2026-06).
  var LLM_PROVIDERS = [
    { id: "deepseek", name: "DeepSeek", base: "https://api.deepseek.com", keyUrl: "https://platform.deepseek.com/api_keys", models: ["deepseek-v4-pro", "deepseek-v4-flash"] },
    { id: "kimi", name: "Kimi", base: "https://api.moonshot.cn/v1", keyUrl: "https://platform.moonshot.cn/console/api-keys", models: ["kimi-k2.6", "kimi-k2.5"] },
    { id: "qwen", name: "通义千问", base: "https://dashscope.aliyuncs.com/compatible-mode/v1", keyUrl: "https://bailian.console.aliyun.com", models: ["qwen3.6-plus", "qwen-max", "qwen-plus"] },
    { id: "glm", name: "智谱 GLM", base: "https://open.bigmodel.cn/api/paas/v4", keyUrl: "https://open.bigmodel.cn/usercenter/apikeys", models: ["glm-5.1", "glm-4.7"] },
    { id: "openrouter", name: "OpenRouter", base: "https://openrouter.ai/api/v1", keyUrl: "https://openrouter.ai/keys", models: ["deepseek/deepseek-v4-pro", "anthropic/claude-sonnet-4.6", "openai/gpt-5.2"] },
    { id: "custom", name: "自定义", base: "", keyUrl: "", models: [] },
  ];
  var llmProvider = "deepseek";
  var llmFetched = {};   // provider id -> model ids pulled live from its /models
  var CUSTOM_OPT = "__custom__";
  function provById(id) {
    for (var i = 0; i < LLM_PROVIDERS.length; i++) if (LLM_PROVIDERS[i].id === id) return LLM_PROVIDERS[i];
    return LLM_PROVIDERS[LLM_PROVIDERS.length - 1];
  }
  function guessProvider(c) {
    if (c && c.provider && provById(c.provider).id === c.provider) return c.provider;
    var b = (c && c.base || "").toLowerCase();
    if (!b || b.indexOf("deepseek") > -1) return "deepseek";
    for (var i = 0; i < LLM_PROVIDERS.length; i++) {
      var pb = LLM_PROVIDERS[i].base.toLowerCase();
      if (pb && b.indexOf(pb.replace(/^https:\/\//, "").split("/")[0]) > -1) return LLM_PROVIDERS[i].id;
    }
    return "custom";
  }
  function llmBaseOf() {
    var v = (($("setLlmBase") || {}).value || "").trim();
    var p = provById(llmProvider);
    var b = v || p.base || "https://api.deepseek.com";
    return b.replace(/\/+$/, "").replace(/\/(v1\/)?chat\/completions$/i, "");
  }
  function llmModelValue() {
    var sel = $("llmModelSel");
    if (sel && sel.value && sel.value !== CUSTOM_OPT) return sel.value;
    return (($("setLlmModel") || {}).value || "").trim();
  }
  function llmEditing() {
    var card = document.querySelector(".llm-card");
    return !!(card && document.activeElement && card.contains(document.activeElement));
  }
  function llmStatus(txt, cls) {
    document.querySelectorAll("[data-llm-status]").forEach(function (e) {
      e.textContent = txt;
      e.className = "llm-status" + (cls ? " " + cls : "");
    });
  }
  function rebuildModelSel(selected) {
    var sel = $("llmModelSel"); if (!sel) return;
    var p = provById(llmProvider);
    var list = llmFetched[p.id] || p.models;
    var html = list.map(function (mid) { return '<option value="' + mid.replace(/"/g, "&quot;") + '">' + mid + "</option>"; }).join("");
    html += '<option value="' + CUSTOM_OPT + '">自定义模型…</option>';
    sel.innerHTML = html;
    var inList = selected && list.indexOf(selected) > -1;
    var custom = $("setLlmModel");
    if (inList) { sel.value = selected; if (custom) custom.style.display = "none"; }
    else if (selected) { sel.value = CUSTOM_OPT; if (custom) { custom.style.display = ""; custom.value = selected; } }
    else if (list.length) { sel.value = list[0]; if (custom) custom.style.display = "none"; }
    else { sel.value = CUSTOM_OPT; if (custom) custom.style.display = ""; }
  }
  function selectLlmProvider(id, keepModel) {
    llmProvider = id;
    var p = provById(id);
    var prov = $("llmProv");
    if (prov) prov.querySelectorAll(".auth-chip").forEach(function (c) { c.classList.toggle("on", c.getAttribute("data-prov") === id); });
    var b = $("setLlmBase");
    if (b) { b.placeholder = p.base || "https://你的网关/v1"; if (!keepModel) b.value = ""; }
    var ku = $("llmKeyUrl");
    if (ku) { if (p.keyUrl) { ku.style.display = ""; ku.href = p.keyUrl; ku.textContent = "去 " + p.name + " 拿 key ↗"; } else ku.style.display = "none"; }
    rebuildModelSel(keepModel || null);
  }
  function fetchLlmModels(silent) {
    var key = (($("setLlmKey") || {}).value || "").trim();
    var p = provById(llmProvider);
    if (!key) { if (!silent) toast("先填 API Key 再拉取"); return; }
    var btn = $("llmFetch");
    if (btn) { btn.disabled = true; btn.textContent = "拉取中…"; }
    var done = function () { if (btn) { btn.disabled = false; btn.textContent = "↻ 拉取列表"; } };
    fetch(llmBaseOf() + "/models", { headers: { "Authorization": "Bearer " + key } }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? "key 无效或无权限" : "返回 " + r.status);
        var ids = ((d && d.data) || []).map(function (x) { return x && x.id; }).filter(Boolean).sort();
        if (!ids.length) throw new Error("没拿到模型列表");
        llmFetched[p.id] = ids;
        var cur = llmModelValue();
        rebuildModelSel(cur || null);
        done();
        if (!silent) toast("已拉取 " + ids.length + " 个模型");
      });
    }).catch(function (e) {
      done();
      if (!silent) toast("拉取失败：" + (e && e.message || "网络不通"));
    });
  }
  function testLlm() {
    var key = (($("setLlmKey") || {}).value || "").trim();
    var model = llmModelValue();
    if (!key) return llmStatus("先填 API Key", "err");
    if (!model) return llmStatus("先选一个模型", "err");
    var btn = $("llmTest");
    if (btn) { btn.disabled = true; btn.textContent = "测试中…"; }
    var t0 = Date.now();
    var done = function () { if (btn) { btn.disabled = false; btn.textContent = "测试连接"; } };
    llmStatus("正在连接 " + model + "…");
    fetch(llmBaseOf() + "/chat/completions", {
      method: "POST",
      headers: { "content-type": "application/json", "Authorization": "Bearer " + key },
      body: JSON.stringify({ model: model, messages: [{ role: "user", content: "ping" }], max_tokens: 1 }),
    }).then(function (r) {
      return r.text().then(function (t) {
        done();
        if (r.ok) return llmStatus("✓ 可用 · " + model + " · " + (Date.now() - t0) + "ms", "ok");
        if (r.status === 401 || r.status === 403) return llmStatus("key 无效或无权限", "err");
        if (r.status === 404 || /model.*not.*(exist|found)|invalid model/i.test(t)) return llmStatus("模型不存在 —— 点「拉取列表」看可用的", "err");
        if (r.status === 402 || /insufficient|balance/i.test(t)) return llmStatus("余额不足 —— 去充值后再试", "err");
        if (r.status === 429) return llmStatus("请求太频繁，稍等再试", "err");
        llmStatus("失败（" + r.status + "）：" + t.slice(0, 80), "err");
      });
    }).catch(function () { done(); llmStatus("连不上 —— 检查 Base URL 或网络", "err"); });
  }
  function syncLlmForm() {
    var c = getLlm();
    if (!llmEditing()) llmStatus(c.key ? (c.model || "deepseek-v4-pro") + " · 已配置" : "未配置 LLM");
    fillLlmForm();
  }
  function fillLlmForm() {
    if (llmEditing()) return;   // don't clobber in-progress edits
    var c = getLlm(), k = $("setLlmKey"), b = $("setLlmBase");
    llmProvider = guessProvider(c);
    selectLlmProvider(llmProvider, c.model || null);
    if (k) k.value = c.key || "";
    if (b) b.value = c.base && c.base !== provById(llmProvider).base ? c.base : "";
  }
  function wireLlmForm() {
    var prov = $("llmProv");
    if (prov && !prov._wired) {
      prov._wired = true;
      prov.innerHTML = LLM_PROVIDERS.map(function (p) {
        return '<button type="button" class="auth-chip" data-prov="' + p.id + '">' + p.name + "</button>";
      }).join("");
      prov.querySelectorAll(".auth-chip").forEach(function (c) {
        c.onclick = function () { selectLlmProvider(c.getAttribute("data-prov")); fetchLlmModels(true); };
      });
    }
    var sel = $("llmModelSel");
    if (sel && !sel._wired) {
      sel._wired = true;
      sel.onchange = function () {
        var custom = $("setLlmModel");
        if (custom) custom.style.display = sel.value === CUSTOM_OPT ? "" : "none";
        if (sel.value === CUSTOM_OPT && custom) custom.focus();
      };
    }
    var fbtn = $("llmFetch");
    if (fbtn && !fbtn._wired) { fbtn._wired = true; fbtn.onclick = function () { fetchLlmModels(false); }; }
    var key = $("setLlmKey");
    if (key && !key._wired) {
      key._wired = true;
      key.addEventListener("blur", function () { if (key.value.trim() && !llmFetched[llmProvider]) fetchLlmModels(true); });
    }
    wirePwShow("llmShow", "setLlmKey");
    var tbtn = $("llmTest");
    if (tbtn && !tbtn._wired) { tbtn._wired = true; tbtn.onclick = testLlm; }
    var save = $("setLlmSave");
    if (save && !save._wired) {
      save._wired = true;
      save.onclick = function () {
        var model = llmModelValue();
        if (!model) { llmStatus("先选一个模型", "err"); return; }
        var p = provById(llmProvider);
        var next = {
          provider: llmProvider,
          model: model,
          key: (($("setLlmKey") || {}).value || "").trim(),
          base: ((($("setLlmBase") || {}).value || "").trim()) || p.base || "https://api.deepseek.com",
          updatedAt: Date.now(),
        };
        var active = document.activeElement; if (active && active.blur) active.blur();
        acctSave(function (pp) { pp.llm = next; });
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

  function closeAcctMenu() { var m = $("acctCtl"); if (m) m.classList.remove("open"); }

  // ---- wire ----
  function wire() {
    wireLlmForm();
    wireTargetsForm();
    acctApply(acctGet());
    var si = $("signIn"); if (si) si.onclick = function () { loginModal(); closeAcctMenu(); };
    var me = $("amMe"); if (me) me.onclick = function () { closeAcctMenu(); if (window.__openSettings) window.__openSettings("account"); };
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
      sb.auth.onAuthStateChange(function (ev, s) { session = s || null; user = (s && s.user) || null; if (user) acctPull(user); paint(); onAuth(); if (ev === "PASSWORD_RECOVERY") recoveryModal(); });
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
    signedOut: function () { return !currentUser(); },
    token: token, user: function () { return user; }, configured: function () { return configured; },
    connections: connections, onAuth: function (fn) { authCbs.push(fn); if (user !== null || !configured) { try { fn(user); } catch (e) {} } },
  };
})();
