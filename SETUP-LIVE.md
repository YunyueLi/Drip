# Drip 实盘接入（Path B：连真实账户 → 拉数 → 决策 → 写回）

线上 app.html 是纯静态页。真实"连账户 + 拉数 + 改预算"这段**必须有服务端**（平台 OAuth 的 App Secret、token 存储、写回都不能放浏览器）。这里用 **Supabase Edge Functions**——就在你已有的 Supabase 项目里，不另起服务器。

```
app.html (GitHub Pages, 静态)
   │  登录(Supabase) · LLM 直连(BYOK)
   ▼
Supabase Edge Functions (Deno)         ← token 只在这里
   meta-oauth  连接授权（换长期 token，存 ad_connections）
   ads-pull    拉真实 campaign insights → AdMetrics
   ads-apply   写回预算/暂停（shadow→copilot→autonomous + 上限 + 审计）
   ▼
Meta Marketing API
```

决策引擎(8 信号+规则+分配)在浏览器 `engine.js` 跑，与 Python 逐字节等价；写回逻辑在 `ads-apply` 里，与 `src/drip/adapters/ads.py` + `safety.py` 一致。

---

## 一次性配置

### 1) Supabase 项目
- 建项目（或用现有的）。`Project Settings → API` 拿 **Project URL** 和 **anon key**。
- 建表 + RLS：
  ```bash
  supabase link --project-ref <你的 ref>
  supabase db push                      # 应用 supabase/migrations/0001_drip_live.sql
  ```
  （或把该 SQL 贴进 Dashboard → SQL Editor 执行。）
- 填 `web/config.js`：
  ```js
  window.DRIP_SUPABASE = { url: "https://xxxx.supabase.co", anonKey: "eyJ..." };
  ```
  anon key 可公开（RLS 兜底）；**service_role 千万别进前端**——它由 Edge Functions 自动注入。

### 2) Meta 开发者应用（长周期，先开始）
- developers.facebook.com → 建 App（类型 Business）→ 加 **Marketing API**。
- 拿 **App ID** 和 **App Secret**。
- OAuth 跳转地址（`Facebook 登录 → 设置 → 有效 OAuth 跳转 URI`）填**函数地址**：
  `https://<ref>.functions.supabase.co/meta-oauth`
- 申请权限 **`ads_read` + `ads_management`** —— 这两个需要 **App Review + 商业验证**，是整条链路最慢的一步（可能数天～数周），**越早提交越好**。审核期间可先用 App 的测试用户/自有账户跑通。

### 3) 部署 Edge Functions + 设密钥
```bash
supabase functions deploy meta-oauth ads-pull ads-apply

supabase secrets set \
  META_APP_ID=<App ID> \
  META_APP_SECRET=<App Secret> \
  META_REDIRECT_URI=https://<ref>.functions.supabase.co/meta-oauth \
  APP_URL=https://yunyueli.github.io/Drip/app.html
```
（`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` 由平台自动注入，无需手动设。）

---

## 用起来
1. 打开 app.html → 右上账号 → **登录**（邮箱/Google/GitHub）。
2. **设置 → 连接器 → Meta Ads → 连接** → 跳 Meta 授权 → 跳回，徽标变「● 已连接」。
3. **设置 → 运行与模型**：填你的 LLM key；选**运行模式**：
   - `Shadow 只规划`（默认，**永不写**，只预演）
   - `Copilot 逐条批准`（你点「应用」才写）
   - `Autonomous 上限内`（在预算上限内自动写）
   设**预算上限**（单条日预算硬顶）。
4. 控制台输入框输入「**诊断我的真实账户并重分预算**」→
   拉真实近 7 天 campaign → 引擎决策 → 你的模型解释 → 底部出现「**应用到平台 · <模式>**」。
5. 点应用：每笔先过 `guard_change`（超上限/单步>50% 直接拒），按模式写回 Meta，结果落 `drip_audit`（可在 Supabase 查全部 who/when/old→new/result）。

## 安全护栏（与 Python 一致）
- **token gate**：没连接 → 一律 shadow，绝不动钱。
- **mode gate**：shadow 不发；copilot 要你点；autonomous 才自动。
- **caps**：`budget_cap`（日预算硬顶）+ 单步变更 ≤ 50%（防重置平台学习期）。
- **audit**：每笔写入 `drip_audit`，含 shadow/denied/applied/failed。

## 本地联调 / 测试（无需 Supabase 或 Meta App）
后端逻辑（拉数归一、上限/模式/token 门、快照→写→回读、OAuth 换 token）已用真实代码对一个忠实的 Meta 模拟做过端到端验证：

```bash
# 1) 后端逻辑集成测试（跑真实 supabase/functions/_shared/meta.ts，21 断言）
node --experimental-strip-types scripts/itest_backend.ts

# 2) 本地 dev 后端（复用同一份 meta.ts + 假 Meta + 内存审计），给浏览器端到端联调用
node --experimental-strip-types scripts/dev_backend.ts 8787
#   然后在 app.html 控制台执行（或临时写进 config.js 调试）：
#   window.DRIP_FN_BASE = "http://127.0.0.1:8787/functions/v1/"
#   登录后输入「诊断我的真实账户」→ 拉数→决策→批准→写回（假 Meta）→ GET /audit 看审计
```

已验证（浏览器内，真实前端 + 真实后端逻辑 + 假 Meta）：拉 7 条 campaign → 引擎 5 放量/2 止损 → copilot 写回 7 笔全部 applied + 7 条审计；shadow 模式 0 写入；预算上限不足时 SCALE 全 denied、PAUSE 照常。`DRIP_FN_BASE` 也可用于自托管代理。

## 现状与边界
- 已实现：**Meta** 全链路（连接/拉数/写回）。
- 待加：TikTok（同 `_shared` 模式，加 `tiktok-oauth` + pull/apply 分支即可）；国内三家（腾讯/巨量真实读未实现，快手写未确认——见 `docs/intraday-research.md`）。
- 目标值（CPP $25 / ROAS 3.0）暂为默认；后续接到「运行与模型」做成可配置（随账号漫游）。
- 想先不接平台、直接对真实数据跑：用 Python CLI（`drip run` / `drip apply`，配 `.env`）。
