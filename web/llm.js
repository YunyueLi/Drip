/* Browser-direct LLM client — the telos derive-direct.ts pattern.
 *
 * No backend. The browser calls the provider's OpenAI-compatible
 * /chat/completions endpoint directly, with the user's BYOK config that roams
 * with their account (see auth.js getLlm()). Mirrors the request shape of the
 * Python src/drip/llm/client.py (_chat_openai). Default provider: DeepSeek.
 *
 * window.DripLLM.chat({system, user, ...}) -> Promise<string>
 */
(function () {
  "use strict";

  var DEFAULT_BASE = "https://api.deepseek.com";
  var DEFAULT_MODEL = "deepseek-v4-pro";

  // Read the roaming config (auth.js). Falls back to localStorage / defaults.
  function cfg() {
    var c = {};
    try { if (window.DripAuth && window.DripAuth.getLlm) c = window.DripAuth.getLlm() || {}; } catch (e) {}
    if (!c || !c.key) {
      try { c = JSON.parse(localStorage.getItem("drip-llm") || "{}") || c; } catch (e) {}
    }
    return c || {};
  }

  // Normalise the base URL (telos baseOf): trim, drop trailing slashes, and strip
  // a mistakenly-pasted /chat/completions or /v1 suffix so we always append once.
  function baseOf(c) {
    var b = (c && c.base && String(c.base).trim()) ? String(c.base).trim() : DEFAULT_BASE;
    b = b.replace(/\/+$/, "");
    b = b.replace(/\/(v1\/)?chat\/completions$/i, "");
    return b;
  }

  function hasKey() { var c = cfg(); return !!(c && c.key); }

  // chat({system, user, maxTokens, temperature, model, signal}) -> Promise<string>
  function chat(opts) {
    opts = opts || {};
    var c = cfg();
    var key = c.key ? String(c.key).trim() : "";
    if (!key) return Promise.reject(new DripLLMError("NO_KEY", "未配置模型 key —— 登录后在「✦ LLM 配置」里填入"));
    var model = (opts.model || c.model || DEFAULT_MODEL).trim();
    var url = baseOf(c) + "/chat/completions";
    var messages = [];
    if (opts.system) messages.push({ role: "system", content: opts.system });
    messages.push({ role: "user", content: opts.user || "" });
    var body = {
      model: model,
      messages: messages,
      max_tokens: opts.maxTokens || 2048,   // reasoning headroom (DeepSeek-V4 puts CoT in reasoning_content)
      temperature: opts.temperature == null ? 0.0 : opts.temperature,
    };
    if (opts.jsonMode) body.response_format = { type: "json_object" };

    return fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json", "Authorization": "Bearer " + key },
      body: JSON.stringify(body),
      signal: opts.signal,
    }).then(function (resp) {
      return resp.text().then(function (txt) {
        if (resp.status === 401 || resp.status === 403)
          throw new DripLLMError("NO_KEY", "key 无效或无权限（" + resp.status + "）");
        if (resp.status >= 400)
          throw new DripLLMError("HTTP", model + " 返回 " + resp.status + ": " + txt.slice(0, 300));
        var data;
        try { data = JSON.parse(txt); } catch (e) { throw new DripLLMError("PARSE", "返回非 JSON: " + txt.slice(0, 200)); }
        var content;
        try { content = data.choices[0].message.content || ""; }
        catch (e) { throw new DripLLMError("SHAPE", "返回结构异常: " + txt.slice(0, 200)); }
        return String(content).trim();
      });
    }, function (netErr) {
      // fetch rejects on network/CORS failures (e.g. provider domain blocked).
      throw new DripLLMError("NETWORK", "无法连接 " + url + "（网络/CORS）: " + (netErr && netErr.message || netErr));
    });
  }

  function DripLLMError(code, message) { this.name = "DripLLMError"; this.code = code; this.message = message; }
  DripLLMError.prototype = Object.create(Error.prototype);

  window.DripLLM = { chat: chat, hasKey: hasKey, baseOf: baseOf, Error: DripLLMError,
                     DEFAULT_BASE: DEFAULT_BASE, DEFAULT_MODEL: DEFAULT_MODEL };
})();
