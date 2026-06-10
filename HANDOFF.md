# Drip — Handoff / 待办

> 线上：https://yunyueli.github.io/Drip/app.html　·　仓库：github.com/YunyueLi/Drip（main 即生产）
> 最后更新：2026-06-10。本文件是接力点——冷启动看这一份即可知道「现状 / 唯一阻塞 / 下一步怎么做 / 怎么验收」。

---

## 0. 一句话现状
核心闭环（连账户→拉真实数据→规则决策→你的模型解释→批准写回）**前端 + 后端全部上线并云端验证**（2026-06-10 部署）。
**唯一剩下的：建 Meta App**（dev 模式，见 §3）——只有你能注册；设好 `META_APP_ID/SECRET` 后整个闭环即可对真实账户跑。

| 能力 | 状态 |
|---|---|
| 前端控制台 / 决策引擎(engine.js，与 Python 等价) / 演示3回放 | ✅ 上线 |
| LLM 浏览器直连（BYOK，设置→运行与模型） | ✅ 上线 |
| 账号系统：云端登录(Supabase) + 本机回退 + 配置漫游 | ✅ 上线并验证（邮箱注册可用） |
| 目标值可配置（CPP/ROAS/演示预算，随账号漫游） | ✅ 上线 |
| 后端 Edge Functions（连接/拉数/写回 + 护栏 + 审计） | ✅ **已部署并云端验证**（见 §2） |
| **接 Meta 实盘**（自动连账户改预算） | ⏳ 建 Meta App(dev 模式) + 设 secrets（§3） |
| TikTok / 国内三家 / 其他视图真化 | ⛔ 未做（见 §5） |

---

## 1. 已完成并上线（不用再动）
- **决策引擎** `web/engine.js`：8 信号 + 规则 + 分配 + 熔断 + intraday + 离线样本，**与 Python 逐字节等价**（`scripts/itest_backend.ts` 旁证 + engine.selfCheck）。
- **LLM 直连** `web/llm.js`：`fetch(base + /chat/completions)`，配置在 设置→运行与模型（model/key/base），登录后随账号漫游。
- **真实回放** 演示按钮 → 3 个真实 DeepSeek 运行在控制台原生回放（`web/real-cases.js`）。
- **账号系统 = 右上角登录** `web/auth.js`：已接真实云 Supabase（`web/config.js` 已填）。邮箱注册/登录可用；未登录显示「登录」（无假 Operator）；没配/失败时本机登录兜底。
- **账户自动同步**（2026-06-10 云端验证）：登录后所有配置自动随账户漫游——`user_settings` 表（owner-only RLS，updatedAt 新者胜），保存即推、登录即拉、换设备登录即恢复（LLM key + 目标全量 E2E 验证过）。旧 `user_metadata` 仅作一次性迁移来源。
- **设置信息架构**（按账户拆分）：**广告账户**（真实连接列表：Meta 连接/重新授权/断开，其余平台诚实标「后端未接入」，假示例已删）· **LLM 接口**（独立页：model/key/base，随账户同步）· **运行设置**（模式/预算上限/目标与预算/归因）· **账户**（身份 + 同步状态）。
- **目标值可配置**：运行设置→「目标与预算」改 CPP / ROAS / 演示总预算，留空回默认（$25 / 3.0x / $1,400）。`engine.selfCheck` 钉死默认值跑，不受用户配置影响。
- **无第三方阻塞脚本**：supabase-js 改为按需从国内可达镜像懒加载（修了"中国打不开/点击无反应"）。

## 2. 后端部署 — ✅ 已完成（2026-06-10，token 方式全自动跑通）
`bash scripts/deploy_supabase.sh` 已执行：表（`ad_connections` / `oauth_states` / `drip_audit`，带 RLS）✓、3 函数部署 ✓、APP_URL/META_REDIRECT_URI ✓。

**云端验证结果**：
- `ads-pull` / `ads-apply` 无 JWT → 401 ✓（鉴权拦截）
- 真实 JWT（临时测试用户，已删）调 `ads-pull` → **409 "no meta connection — connect it first"** ✓——证明 JWT 验证、平台注入的 `SUPABASE_SERVICE_ROLE_KEY`、DB 读全链路通，HANDOFF 旧版担心的注入问题不存在。
- `meta-oauth` 现返回 500 "Meta app not configured" —— **预期**：§3 设好 META_APP_ID/SECRET 后即变 401。

重部署（改了函数代码后）：`.supabase-token` 就位 → 重跑同一脚本即可。

**Auth 云端配置**（2026-06-10 经 Management API 设好，换项目需重设）：`site_url=https://yunyueli.github.io/Drip/app.html`；重定向白名单含线上 + `http://localhost:8099/*`；**注册免邮箱确认**（`mailer_autoconfirm=true`，修「确认链接跳 localhost:3000 / otp_expired」）。邮件模板改中文需自定义 SMTP（免费档限制，未做）。

## 3. 接 Meta 实盘（dev 模式，跑你自己账户免审核）
1. developers.facebook.com → 新建 App（Business）→ 加 **Marketing API** + **Facebook Login**。
2. OAuth 跳转 URI 填：`https://xneuizhnnzsvbbjirhdw.supabase.co/functions/v1/meta-oauth`
3. 设密钥：`supabase secrets set META_APP_ID=<id> META_APP_SECRET=<secret>`
4. 把你自己的广告账户加为 App 的测试用户（dev 模式即可读写自己账户，无需 App Review；要给别人用才需 `ads_read`/`ads_management` 审核）。

## 4. 联调验收清单（部署后这样验证端到端）
1. 强刷 app.html → 右上**登录**（邮箱，收确认邮件）。
2. 设置→**运行与模型**：填 DeepSeek key；选模式（默认 **Shadow 只规划**，安全）。
3. 设置→**连接器**→**连接 Meta** → 授权 → 徽标变「● 已连接」。
4. 控制台输入「**诊断我的真实账户并重分预算**」→ 应：拉真实近 7 天 campaign → 引擎判定 → 你的模型写解释 → 底部出现「应用到平台·<模式>」。
5. 切 **Copilot** 模式点应用 → 真实写回 Meta（快照→改→回读校验）→ Supabase `drip_audit` 表有审计行。
6. 护栏自检：Shadow 模式应 0 写入；预算上限调到低于目标 → SCALE 应 `denied`、PAUSE 照常。
（以上 §4.4–4.6 的逻辑已在本地用真实代码 + 假 Meta 跑通：`scripts/itest_backend.ts` 21/21 + 浏览器 E2E。）

## 5. 后续 / 可选（非阻塞，按需做）
- **TikTok 全链路**：照 `_shared/meta.ts` 模式加 `tiktok-oauth` + ads-pull/apply 的 tiktok 分支（collectors/writers Python 里有 TikTok REST 契约可参照）。
- **国内三家**（腾讯/巨量/快手）：Python 里读未实现（仅样本）、快手写未确认；要做得先补真实读。
- **Google/GitHub 登录**：Supabase 项目里还没开 provider（目前仅邮箱）；Supabase → Authentication → Providers 开一下即可，前端已支持。
- **其余视图仍是 mock**：增长策略(项目板)、创意库(gpt-image/Seedance 生成)、归因对账(AppsFlyer)、操作台、Drip-Bench——都是静态脚手架，要真化各需独立后端。
- **Bench 分数偏低**（用户早先提过 #1）：methodology agent + LLM judge，未做。

---

## 附录 A — 关键坐标
- 线上：`https://yunyueli.github.io/Drip/app.html`
- Supabase 项目：ref `xneuizhnnzsvbbjirhdw`，URL `https://xneuizhnnzsvbbjirhdw.supabase.co`
- publishable key（公开安全，已在 `web/config.js`）：`sb_publishable_QjqFx1bgU9nyWzQs2VXjLg_8YTWM7FI`
- 函数 URL：`https://xneuizhnnzsvbbjirhdw.supabase.co/functions/v1/{meta-oauth,ads-pull,ads-apply}`
- Meta 回调/跳转 URI：`https://xneuizhnnzsvbbjirhdw.supabase.co/functions/v1/meta-oauth`
- **永不入库/聊天的秘密**：Supabase access token（`.supabase-token`，gitignored）、DB 密码、`META_APP_SECRET`、service/secret key。

## 附录 B — 文件地图
```
web/engine.js      决策引擎(JS 移植)        web/llm.js     浏览器直连 LLM
web/run.js         控制台跑流程 + 实盘/样本   web/live.js    实盘客户端(连接/拉数/写回)
web/auth.js        账号(云端+本机回退)        web/config.js  Supabase url+anon key(已填)
web/app.{html,css,js}  原控制台 UI
supabase/config.toml                      3 函数 verify_jwt=false
supabase/migrations/20260610120000_drip_live.sql   建表 + RLS
supabase/migrations/20260610190000_user_settings.sql 账户漫游配置表（已部署到云）
supabase/functions/_shared/{cors,auth,meta}.ts     CORS / Supabase 鉴权 / Meta API+护栏(忠实 Python)
supabase/functions/{meta-oauth,ads-pull,ads-apply}/index.ts
scripts/itest_backend.ts   后端逻辑集成测试(21/21，跑真实 meta.ts vs 假 Meta)
scripts/dev_backend.ts     本地 dev 后端(复用 meta.ts，浏览器 E2E 用；配 DRIP_FN_BASE)
scripts/deploy_supabase.sh 一键部署到云
```

## 附录 C — 本地测试 & 部署机制
```bash
node --experimental-strip-types scripts/itest_backend.ts      # 后端逻辑 21/21
node --experimental-strip-types scripts/dev_backend.ts 8787   # 本地后端(浏览器 DRIP_FN_BASE=该地址)
.venv/bin/python -m pytest -q                                  # Python 198 绿
```
- **部署 = push 到 main**：`web/**` 改动触发 `.github/workflows/pages.yml` 发布 `web/`。
- **必须走 SSH** 推送（`origin=git@github.com:YunyueLi/Drip.git`）：本机 gh OAuth token 缺 `workflow` scope，含 `.github/**` 改动时 HTTPS 会被拒。
- 护栏(与 Python 一致)：token gate / mode(shadow·copilot·autonomous) / caps(budget_cap + 单步 ≤50%) / 每笔 `drip_audit` 审计。
