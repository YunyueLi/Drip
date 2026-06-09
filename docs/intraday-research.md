# Drip 调研档案 — 能力现状 · 平台“分钟级”能力 · 盘中层方案

> Drip 的研究/规划文档,三块:① 开源版**当前能力的诚实自审**(什么是真逻辑、什么还是 stub/roadmap);② 五大投放平台(Meta / 腾讯 / 巨量 / 快手 / TikTok)**“分钟级”实时监控与自动调控的真实能力边界**;③ 据此设计的**盘中(intraday)层方案**。
>
> 秉持 Drip 一贯的“可读、可审计、不吹”——把现状和限制摊开写,而不是 trust-us。
>
> **数据时点**:2026-06。**方法**:仓库全量代码审计 + 两轮多源调研(海外/国内,均含 3 票对抗验真) + 官方文档/SDK 一手核验 + JS SPA 渲染抓取。
> **置信标注**:✅ 官方一手 · 🟡 机制确认/高质量二手 · ❌ stub/空白/未实现。
> Living doc:拿到新一手数据(如巨量后台 QPS/学习期、快手完整能力面)请回填 Part 2.4 与 Part 5。

---

## 目录
- [Part 1 — 开源版能力全盘审计](#part-1)
- [Part 2 — “分钟级监控”可行性（平台能力调研）](#part-2)
- [Part 3 — Drip 盘中层实现方案](#part-3)
- [Part 4 — 关键决策与修正记录](#part-4)
- [Part 5 — 待办空白 (Open Questions)](#part-5)
- [附录 — 完整引用来源](#附录)

---

<a name="part-1"></a>
## Part 1 — 开源版能力全盘审计

> **2026-06 重构更新**：本 Part 已据重构后的代码同步。该次重构**删除了与主链路并行、从未被真实执行的「孤儿栈」**——`orchestrator.py` / `workers/` / `graph.py`（LangGraph 脚手架）/ `adapters/bidding.py` / `adapters/simulation.py`（OASIS）及 `drip launch`/`demo` 命令；并把 `creative` 接到真实的 gpt-image/Seedance 生成（无 key 回退 dry），`adapters/ads.py` 现为真实 `MetaWriter`（非旧的假 id stub）。Part 2–5 的平台调研未受影响。

**起点问题**：用户使用 Drip 的全流程是什么？开源技术版本是否支持所有这些操作？

**一句话结论**：开源版是一个诚实的「**决策大脑 + 评测基准**」参考实现——会**想**（8 信号规则引擎）、会**说**（LLM 叙述）、能**自证**（Drip-Bench），离线全跑得通、可审计；但「**手脚**」（真实拉数 + 真实投放执行）要么未验证、要么是 stub。它**还不能真正自己动钱**，且 README/roadmap 对此是诚实的。

### 1.1 用户使用全流程（产品宣称的理想闭环）

| # | 用户动作 | 界面入口 | CLI | 代码模块 |
|---|---|---|---|---|
| 0 | 接入广告账户 + LLM key | 设置/连接器 | `.env` | `.env.example` |
| 1 | **采集** 跨平台 campaign 数据，归一 schema | 操作台 | `drip run` | `collectors.py` |
| 2 | **诊断** 8 信号→红黄绿→SCALE/PAUSE/HOLD/REDUCE/REFRESH 决策卡（规则链+置信度） | 操作台·决策队列 | `drip doctor` | `engine/` |
| 3 | **归因校正** 平台口径 ROAS vs MMP 真值对账 | 操作台 | — | `attribution.py` |
| 4 | **策略** 排赢家/输家、提下一个创意测试 | 增长策略 | `drip run` | `strategist.py` |
| 5 | **创意** 为赢家方向产出变体 | 创意库 | `--generator` | `creative.py` + `adapters/{image,video}` |
| 6 | **分配** 跨平台再分预算、封日预算上限 | 操作台·分配 | `drip run` | `allocator.py` |
| 7 | **审批** 动钱前人工签字 | 操作台 | copilot 模式 | cli `_execute_write` + `safety.py` |
| 8 | **执行** 把 scale/pause 落到 Meta/腾讯/巨量 | 操作台 | `drip apply` | `adapters/ads.py`(MetaWriter) + `writers.py` |
| 9 | **学习** 萃取赢点回灌下一轮 | 操作台 | `drip run` | `feedback.py` |
| 10 | **评测** 给 agent 决策打分 | Drip-Bench | `drip bench run` | `eval/` |

资金安全阶梯（`DRIP_MODE`）：`shadow`（默认，只规划）→ `copilot`（每步人工批准）→ `autonomous`（封顶内自动写）。

> ⚠️ **网页控制台 `web/app.html` 是前端 demo**：12 段对话、决策卡、分配动画都是写死的演示内容（`CONV` 对象），**没接后端**。线上看到的是“完整产品”，开源 Python 包实现的是大脑、不是这套 UI 的真实联动。

### 1.2 逐环支持度判断（对照代码真相）

| 环节 | 评级 | 代码真相（证据） |
|---|---|---|
| 8 信号决策引擎 | ✅ | `engine/rules.py` 确定性决策树（单位经济→创意衰退→放量→观望）+ 置信度推导 + 薄样本封顶 + 自动护栏 + 下次检查节奏（SCALE 48h / 其余 24h）。**最硬的一块**，有测试。 |
| 诊断/分配/归因/策略/反馈 | ✅ | 纯算法、纯函数、离线可跑可测。`allocator.plan()` 逐 campaign 过引擎→ROAS 价值加权→归一总预算；`attribution.reconcile()` 真逻辑。 |
| LLM 叙述层（12 provider） | ✅ | `llm/client.py` 真 httpx 调 Anthropic Messages + OpenAI 兼容协议，无需各家 SDK；无 key 回退模板。 |
| Drip-Bench 评测 | ✅ | `eval/` + 10 个 YAML 案例 + 评分 + 可复现 bundle。 |
| 审批门（花钱前批准） | ✅ | `copilot` 模式下 `cli._execute_write` 每笔写入前 `click.confirm` 等人工 y/N；`safety.guard_change` 先过预算上限 + 单步变更上限，再落审计。`autopilot` 另有熔断器。 |
| 数据采集（读） | 🟡 | `collectors.py` 的 `_fetch_live` 用官方 SDK（facebook_business / TikTok httpx）写了真调用，但 ① 缺 creds 回退确定性样本 ② 全标 `pragma: no cover`（**无测试、无真账户验证**）。 |
| 创意图片/视频生成 | 🟡 | `creative.produce` 现真接 `adapters/image.py`(gpt-image) 与 `adapters/video.py`(Seedance)：有 key 即同步驱动 async 生成、落地真实文件；**无 key 回退 `dry` 占位**（离线仍可跑）。真生成路径需 SDK+网络，`pragma: no cover`，未跑真账户。ComfyUI 未实现（归入回退）。 |
| 竞价执行 | ❌(by design) | 不自建拍卖竞价——平台围墙花园（GEM/AXON/Smart+）赢这局，留作平台 auto 槽。旧的 `adapters/bidding.py` 占位栈已在 2026-06 删除。 |
| **真实投放写入** | 🟡 | `adapters/ads.py::MetaWriter` 真调 Meta Marketing API（快照→写→回读核验、幂等、token 门）；`adapters/writers.py` 腾讯/巨量真 REST POST（未验证），快手端点未确认（`raise`）。全部 `pragma: no cover`，**真账户 live 写仍未验证**（roadmap 明确未勾选）。 |
| MMP 真值拉取 | ❌ | BYO 接口，Drip 自己不拉 AppsFlyer/Adjust；无真值时打文档化 haircut（Meta 18% / TikTok 12% / Google 10%）。 |
| LTV 模型 | ❌(by design) | `adapters/prediction.py` 不训练，null / heuristic / BYO。 |
| Agentic 自主编排 | 🟡 | `supervisor.py`：按信号把局面分类（出血/放量/疲劳/平稳）并路由，配熔断器（数据异常或写失败即停）。**确定性规则路由，非 LLM 编排**——可审计但不"智能"。`drip autopilot` 已接入。 |

测试：14 文件、164 个 test 函数（`pytest -q` 全绿）；ruff + mypy(strict) 全过。核心（engine/allocator/safety/writers/supervisor/pipeline）有数值级行为锁定测试；`eval/`、`attribution.py`、`llm/` 仍缺单测。

### 1.3 三大缺口

1. **真金白银最后一公里「已铺路、未验证」**——写投放路径（`MetaWriter` + 腾讯/巨量 REST）真实存在、过资金安全门（预算/单步上限）、落审计，但全 `pragma: no cover`、从未在真账户跑通；快手端点未确认（`raise`）。
2. **读/写路径不对称（上线前必修）**——Meta/TikTok 有真 live 拉数代码（未验证）；但腾讯/巨量/快手的采集**无论是否配 token 都只返回样本**，写却是真 REST → 中国平台存在「**假读真写**」风险，必须先补真实读路径或对样本来源平台禁写。
3. **真实数据链路从未被验证**——采集/写入 live 代码全 `pragma: no cover`，roadmap “First live Meta write verified on a real account” 明确**未勾选**。

### 1.4 定位

作为「可审计 UA 决策引擎 + 开放评测基准」= 真货、能跑、能复现、能 fork。作为「端到端自动投放 agent」= 带离线兜底的骨架，大脑装好、手脚在 v0.2 的 TODO 里。难得的是 README 没吹（明说 “Runs offline on samples”、roadmap 未勾选 live run）。

---

<a name="part-2"></a>
## Part 2 — “分钟级监控”可行性（平台能力调研）

**起点问题**（UA 同学）：“国内做得好的是**分钟级**监控，规则直接写进决策树、不用问直接调。Drip 是什么时间维度？”
**用户决策**：分钟级盘中监控 + 自动执行，**国内外都要支持**。

### 2.1 两个核心判断（结论先行）

**(a) 现实可达的“数据轮询节奏”：没有一家支持分钟级。**
- 五大平台（Meta / 腾讯 / 巨量 / 快手 / TikTok）**报表最细全是小时级（hourly）**，无 15 分钟/亚小时/真实时报表粒度。
- 原生自动规则引擎**全在 30 分钟–1 小时**：Meta 30min、腾讯每小时（官方“无法实现实时调控”）、巨量空白。
- Meta 数据本身 15 分钟才刷新一次；巨量 5–10 分钟更新但稳定有滞后。
- → **“分钟级”在数据供给侧 + 平台原生规则侧都不成立，是营销话术。**

**(b) “分钟级 ROI 优化”是话术；必须把两侧分开：**
- **花费侧（pacing/控成本/防超投）**：确有近实时能力——消耗回传快，原生规则支持 PAUSE/改预算/改出价，可在 30min–1h 内关停/压预算；腾讯另有 `realtime_cost` 当日实时消耗快照。
- **转化侧 ROI**：受归因窗口拖累——Meta ROAS 点击后 ~7 天才稳、历史 28 天才冻结、广告结束后仍更新数天；TikTok 同样事后回溯。**任何分钟时间点上的 ROI 都是高度不完整的部分值，据此分钟级优化统计上无意义。**

### 2.2 终极五平台对照表（验证版）

| 平台 | 报表最细粒度 | 数据延迟/回溯 | 原生自动规则最小频率 | mutate API（自己调） | 限流 | 证据 |
|---|---|---|---|---|---|---|
| **Meta** | 小时级 | 15min 刷新；28 天冻结、结束后仍更新数天；ROAS ~7 天稳 | **30 分钟**（SEMI_HOURLY；无连续/分钟级） | 受 BUC 约束，可较快 | BUC 滚动 1h 窗 + 活跃广告数 | ✅一手 |
| **腾讯广告** | **小时级** + `realtime_cost/get` 当日实时消耗快照 | **30 天回溯期**（期间数据会变） | **每小时**（官方“无法实现实时调控”） | `campaigns/update`（日预算/总预算/起停/投放速度）+ 批量异步 | **qpm**·开发者维度按消耗分级（示例 1000qpm，无统一公开数字） | ✅一手 |
| **巨量引擎** | 小时级（SDK 枚举 DAILY/HOURLY/WEEK/MONTH/TOTAL） | **5–10min 更新**；峰值 3h 才稳；**历史基本不回溯**（除非校对） | **空白**（二手矛盾、关键 claim 被否） | **8 个 POST 端点**（改预算/出价/深度出价/ROI目标 + 千川） | 开发者级 + 接口级 QPS 双重频控，**后台按开发者分配**，无公开数字 | ✅粒度/延迟/写端点；🟡限流机制 |
| **快手磁力** | 小时级（分时近 7 天、历史 6 个月异步） | 空白 | 空白 | 空白 | 空白 | 🟡二手（镜像疑似 2020） |
| **TikTok** | 小时级（stat_time_hour/day + lifetime） | 报表事后回溯（归因窗默认 3 天，范围 0–364） | 仅知学习期 | — | — | 🟡二手交叉 |

### 2.3 海外明细（Meta，官方一手）

- **报表粒度**：`hourly_stats_aggregated_by_advertiser_time_zone` 为最细时间型 breakdown；`time_increment` 最小 1 天。
- **数据延迟**：Insights “refresh every 15 minutes and do not change after 28 days of being reported”；“metrics may continue to update for a couple of days after an ad has completed”。ROAS ~7 天稳（示例 Day1 1.80x→Day7 3.06x，blog，方向稳固、具体曲线中等可信）。
- **限流（BUC）**：滚动 1 小时窗，跟踪 call_count/total_cputime/total_time（占配额百分比，达 100 限流）。Ads Management 每小时配额 = 基数(300/100000) + 40×活跃广告数；Ads Insights = 基数(600/190000) + 400×活跃广告数。dev tier 默认极低（300/600），max score 60、衰减 300s、达上限封 300 秒；官方建议错峰 + back-off + 监控 `x-fb-ads-insights-throttle`。
- **原生自动规则**：`schedule_type` ∈ {DAILY, HOURLY, SEMI_HOURLY, CUSTOM}，最小 30 分钟（SEMI_HOURLY），'Continuously'≈每 30 分钟。动作 `execution_type` 含 PAUSE / REBALANCE_BUDGET / CHANGE_BUDGET / CHANGE_BID / UNPAUSE / CHANGE_CAMPAIGN_BUDGET。
- **学习期重置**：重大编辑（改预算/出价/优化事件）会重置；TikTok 官方 $100→$300 重学、$100→$110 不会，需 ~50 转化通过。Meta 精确阈值不确定（“≤20% 不踢出”被 0-3 否决）。

### 2.4 国内明细（巨量 + 腾讯，多为一手）

**巨量引擎**
- 写操作端点（官方 Go SDK v1.1.88 源码，8/8 POST）：`promotion/bid/update`、`promotion/budget/update`、`project/cpa_bid/update`、`project/budget/update`、`promotion/deepbid/update`、`project/roigoal/update`、`qianchuan/ad/bid/update`、`qianchuan/ad/budget/update`。
- 数据延迟（官方文档，Jina 渲染）：“数据 5～10 分钟更新一次”，“8～9 点数据 10 点可稳定，晚高峰可能 3 小时”，“次日 9 点拿前一天稳定消耗”，“**历史数据一般不变，除非校对**”。
- OAuth（官方，Jina）：access_token 24h / refresh_token 30 天 / auth_code 10 分钟一次性；token 端点 `https://ad.oceanengine.com/open_api/oauth2/access_token/`。
- 限流：开发者级 + 接口级双重 QPS 频控（机制确认，CSDN + 官方“频控限流器开发”实践页），**具体配额按开发者分配、登录后台可见，无统一公开数字**。

**腾讯广告**
- 报表：`hourly_reports/get`（group_by `hour`）、`daily_reports/get`（天）、`tracking_reports/get`（`time_granularity` ∈ {DAILY, HOURLY}）；小时报表**广告上线 30 分钟后**生成、实时刷新；**30 天回溯期**。
- `realtime_cost/get`：当日实时消耗快照（单位分，只支持今天），官方“统计周期不同、**不推荐对账**，用途是**校验是否符合日预算修改限制**”。
- 写操作：`campaigns/update`（daily_budget / total_budget / configured_status ∈ {AD_STATUS_NORMAL, AD_STATUS_SUSPEND} / speed_mode）+ `batch_async_requests`（批量改状态/出价/日限额/投放时间）。
- 频控：2024-10 起从“每应用独立频控”升级为“**开发者维度 + 按消耗分级的 qpm 频控**”（示例 adgroups/get 1000qpm，月度刷新，后台查看），无统一公开 QPS。
- 原生自动规则（官方帮助中心）：“仅支持**每小时及指定时间**扫描，**无法实现实时调控**”；动作 = 暂停/启用/改日限额/改出价。

**快手磁力**：Marketing API（报表/账户/创建/修改/人群/建站）；报表 `time_granularity` ∈ DAILY/HOURLY（默认 DAILY）；实时/分时报表近 7 天、历史 6 个月异步。QPS/mutate/自动规则**空白**，且“分时近 7 天/历史 6 个月”镜像可追溯到约 2020 年、2026 未重新确认。

**TikTok**：`report/integrated` 支持 stat_time_hour/day + lifetime；报表事后回溯（Airbyte 默认归因窗 3 天、范围 0–364）。

### 2.5 最关键洞察：两条速度完全不同的“调控通道”

| 通道 | 速度 | 现状 |
|---|---|---|
| **平台原生自动规则**（后台 UI 配置） | 慢 | Meta 30min、腾讯每小时、巨量空白 |
| **开放平台 mutate API**（你自己调） | 快 | 巨量 8 端点、腾讯 campaigns/update + 批量；**API 本身可分钟级反复直调，无可证实的次数上限**（仅受频控约束） |

**含义**：第三方工具（如 Drip 的 daemon）走 **mutate API，不受原生规则 30min/1h 的限制，写侧可分钟级**。但——
> **真正的天花板在“读侧”，不在“写侧”**：报表全平台最细只到小时级。你能分钟级“动手”，只能小时级“看见”。平台自己的原生规则之所以只做到 30min/1h，正是数据粒度 + 学习期权衡后的“有用下限”。

### 2.6 数据回溯对比（影响盘中存储设计）

| 平台 | spend 历史回溯 | 工程含义 |
|---|---|---|
| Meta | 28 天才冻结，结束后仍更新数天 | 按回溯期 `upsert` 不 `append` |
| 腾讯 | **30 天回溯期**，期间会变 | 同上 |
| **巨量** | **基本不变**（除非校对） | 历史最干净，盘中不易被“数据变脸”坑 |
| TikTok | 事后回溯（归因窗 3 天） | 回拉窗口处理 |

### 2.7 被对抗验证否决的 claim（诚实记录，勿引用）

- 腾讯 `campaigns/update` 每计划每天 ≤1000 次 — **0-3 否**
- 腾讯 账户日预算每天 5→10 次上限 — **0-3 否**
- 腾讯 频控“每 5 分钟 1 次”异步任务 — **0-3 否**
- 巨量 自动规则最小 30 分钟 — **0-3 否**（我 hands-on 误信的二手，被推翻）
- 巨量 自动规则每计划每天出价 ≤1 次 — **0-3 否**
- 巨量 自动规则含“实时反馈/分钟级” — **0-3 否**
- TikTok 报表 11 小时延迟 — **0-3 否**（措辞过度）
- Meta 预算改动 ≤20% 不重置学习期 — **0-3 否**
- Meta 数据 15-20min floor / 转化 72h / 逐行 restate — **1-2 弱否**（windsor/seresa 单源）

### 2.8 证据强度分层

- **腾讯** = 最扎实，粒度/realtime_cost/mutate/频控/自动规则频率全官方一手。
- **巨量** = 粒度 + 数据延迟 + 写端点 + OAuth 一手（SDK 源码 + Jina 渲染官方文档）；限流数字、学习期重置仍空白。
- **快手 / TikTok** = 高质量二手为主。

---

<a name="part-3"></a>
## Part 3 — Drip 盘中层实现方案

### 3.1 两层架构（最大收获，研究证实）

| 层 | 节奏 | 管什么 | 用谁 |
|---|---|---|---|
| **战略层** | 日级 24–48h | ROI / 跨平台分配 / scale-pause | Drip 现有引擎（研究证明 ROI ~7 天才稳，日级才合理） |
| **盘中层** | **小时级**（读侧上限；花费侧可借实时消耗接口更快触发） | **只管花费侧**：pacing / 控成本 / 防超投 | 新建 `engine/intraday.py` |

**盘中层绝不碰 ROI 决策**（分钟/小时尺度 ROI 是部分值）。腾讯 `realtime_cost` 官方亲口“只配花费侧、不配对账”，完美印证此分工。

### 3.2 盘中安全模型（≠ 日级 copilot）

日级可“每次写人工批准”；**盘中节奏快，人没法每次批**。所以可问责性换挂法：
> 人审批的是**规则集 + 闸值**（一次），不是每次操作；之后 daemon 在闸内 `autonomous` 自动调，**每次操作留审计可回放 + 异常自动熔断 + 人可随时接管**。
> 盘中模式阶梯：`shadow（观察校准）→ autonomous（带硬闸+熔断，灰度放量）`，中间没有 copilot。

这正是与国内黑盒工具的差异点——**可审计、可回放、可问责**，别丢。

### 3.3 分期路线（先解前置阻塞）

| 期 | 做什么 | 验证目标 |
|---|---|---|
| **P0** | 打通 `ads.py` 真写入（先 Meta + 巨量两条线、copilot/灰度） | 能**安全地“调”**一次 |
| **P1** | 常驻 daemon + 盘中采集（单平台，先 shadow） | 盘中信号**准不准** |
| **P2** | 盘中规则集 + autonomous + 熔断/硬闸（单账户灰度） | 无人直调**敢不敢放** |
| **P3** | 扩平台（腾讯/快手），平台抽象层 | 多平台对接 |

**P0 起点（国内外都要 → 故意挑最不一样的两条线压测抽象）**：先 Meta（摩擦最低、验证架构最快）→ 紧接巨量（海外 vs 国内、purchase vs 双出价、token vs OAuth）→ 抽象扛住再扩。

### 3.4 落到代码（graft 到现有 `src/drip/`）

| 模块 | 新/改 | 干什么 |
|---|---|---|
| `adapters/ads.py` | 改 | 实现 `apply_decision(campaign_id, action, new_budget)`，替掉假 id |
| `adapters/writers/` | 新 | `PlatformWriter` 抽象 + meta/巨量/腾讯 各 writer（对称于 `InsightsSource`） |
| `daemon/scheduler.py` | 新 | APScheduler 定时循环，每 N 分钟触发一轮（规模化再上 Celery/Arq+Redis） |
| `daemon/runner.py` | 新 | 一轮盘中周期：拉数→盘中信号→盘中规则→(shadow 落库 / autonomous 写) |
| `collectors.py` | 改 | 加 `IntradayCollector`：hourly/增量拉取 + `upsert`（spend 回溯修正） |
| `engine/intraday.py` | 新 | 盘中规则集（独立于 `engine/rules.py` 日级树） |
| `engine/signals.py` | 改 | 加盘中信号：pacing / 成本突刺 / 预算耗尽预测 / 时段 |
| `safety/gates.py` | 新 | 多层硬闸（单次幅度/单 campaign 频次/账户日 cap/全局日 cap） |
| `safety/breaker.py` | 新 | 熔断器：异常→暂停所有自动写 + 告警 |
| `safety/audit.py` | 新 | 写操作审计 + 回滚（写前快照） |
| `store/` | 新 | SQLite/PG：时序 + 决策 + 审计落库 |

**数据模型（4 张表）**
- `metrics_ts`：`(campaign_id, ts_bucket, spend, conv, …)` — **upsert** on `(campaign_id, ts_bucket)`，扛回溯。
- `decisions`：`(id, campaign_id, ts, action, signals_json, rule_chain_json, confidence, source: daily|intraday)`。
- `writes`（审计）：`(decision_id, campaign_id, old_value, new_value, status, result, mode, ts)` — 支持回滚 + 回放。
- `runs`：daemon 运行/checkpoint 日志，断点续跑。

### 3.5 盘中信号 + 规则集

| 信号 | 公式/逻辑 | 触发 |
|---|---|---|
| pacing | 当前累计 spend vs 预期曲线（日预算×时段权重） | 超速→限速/降预算 |
| 成本突刺 | 短窗 CPP/CPA vs 滚动基线偏离（>Nσ 或 >X%） | 突破→止血（降/停） |
| 预算耗尽预测 | 按当前 pacing 外推几点烧完 | 将耗尽且 ROI 好→加预算 |
| 时段 | dayparting 各时段表现 | 差时段→降/停 |

规则集复用 `engine` 范式（Signal→红黄绿→Action+护栏+置信度+规则链），独立 ruleset，先 shadow 校阈值再 autonomous。

### 3.6 步长策略：避免重置学习期

mutate API 技术上可分钟级，但**频繁写伤学习期**：
- 防超投/限速：优先用 campaign 日预算上限(CBO cap)/软限速，少动 adset。
- 止血：优先**降预算/降出价**（控幅度），少用**暂停**（停再开重学）。
- 加预算：**少次、单次幅度更大**，避开学习期内。
- 让 P2 的“单次幅度硬闸”天然卡在不触发重学的档（阈值需上线灰度实测——见 Part 5）。

### 3.7 per-platform 配置（填入验证数字）

| 平台 | 盘中读节奏 | 写通道 | 限流处理 | 特记 |
|---|---|---|---|---|
| Meta | 15min（数据刷新下限） | Marketing API budget/status，对齐 BUC | advanced access + 增量 + 错峰 + back-off + 监控 throttle 头 | 回溯 28 天 |
| 腾讯 | 小时报表 + `realtime_cost` 当日快照（防超投更快） | `campaigns/update` + 批量异步 | qpm 后台分配，自适应退避 | 回溯 30 天 |
| 巨量 | 5–10min 更新（按小时拉桶） | 8 个 POST 端点 | dev+接口 QPS 后台分配，自适应退避 | 历史基本不回溯（最干净） |
| 快手 | 小时（分时近 7 天） | 待补 | 待补 | 镜像旧、需复核 |

> 轮询节奏 + 限流并发**按平台单独配 + 自适应退避**，不能一个全局值。

---

<a name="part-4"></a>
## Part 4 — 关键决策与修正记录

### 4.1 用户决策
- **国内外都要支持** → 核心必须平台中立。逼进核心设计 4 件事：
  1. 真正的平台抽象层（`PlatformWriter`/`PlatformCollector`）+ per-platform 配置。
  2. **AdMetrics schema 张力**：国内双出价/深浅层转化/付费 ROI 口径/人民币 ≠ 海外 purchase/ROAS → 需扩展或平台特定字段（不对会让盘中信号算错）。
  3. **鉴权分层**：Meta System User token vs 巨量/腾讯 OAuth（可能需企业资质审核）。
  4. **数据合规 / residency**：国内数据大概率要留境内 → 存储/部署**分区**，接口/存储层现在就留分区的位。

### 4.2 hands-on vs 对抗验证的修正（方法论价值）
- hands-on 快但带二手噪声：我手挖的“巨量自动规则 30 分钟”“腾讯有日预算修改次数限制(具体数字)”“巨量数据 5-10 分钟更新(当时无官方源)”——前两条被工作流**对抗验真 0-3 否决**；第三条后来用 Jina 抓到官方文档**反而坐实**。
- 教训:**二手要交叉验真**;一手(官方文档/SDK 源码)才作硬结论。

### 4.3 工具能力边界（攻国内 SPA 的复盘）
- `WebFetch`：有外网，但**无 JS** → 巨量 SPA 文档只拿到标题壳；`web.archive.org` 被 WebFetch 封。
- `Claude Preview` 无头 Chromium：**有外网**（`fetch` 能打到巨量），但 **URL 被钉死在 localhost + 跨域 CORS** → 读不了外部页。
- `Claude in Chrome`：**无已连接浏览器**，不可用。
- **`Jina Reader`（`https://r.jina.ai/<url>`）**：服务端渲染 JS，**攻破巨量 SPA** → 拿到数据延迟/OAuth/页面结构。**国内 SPA 文档的破法就是它。**

---

<a name="part-5"></a>
## Part 5 — 待办空白 (Open Questions)

1. **巨量具体 QPS 配额 + 学习期重置阈值**：QPS 按开发者分配、登录【开发者后台→接口频控】可见；改预算/出价是否重置学习期，公开文档无 → 需官方投放/学习期文档或实测。最快：用户自己的巨量后台。
2. **快手完整能力面**：mutate 写端点、原生自动规则（动作+频率）、QPS/并发——基本空白；“分时近 7 天/历史 6 个月”窗口 2026 是否仍有效需复核。
3. **三大国内平台“改预算/出价是否重置学习期/冷启动 + 调整后多久稳定”**——全空白，且这是盘中步长策略最关键的一项；**本就该上线灰度实测**（任何平台的学习期阈值都得用真账户测，不能靠文档）。
4. **腾讯/巨量 spend 回溯行为的精确量级**——腾讯确认 30 天回溯、巨量确认基本不回溯，但转化回传延迟典型值未量化。

---

<a name="附录"></a>
## 附录 — 完整引用来源

### A. 开源版审计（Drip 仓库，已读文件）
`src/drip/`：`cli.py`、`orchestrator.py`、`pipeline.py`、`graph.py`、`engine/engine.py`、`engine/rules.py`、`collectors.py`、`allocator.py`、`attribution.py`、`creative.py`、`llm/client.py`、`adapters/{ads,bidding,image,prediction,simulation}.py`；`README.md`、`pyproject.toml`、`benchmarks/`、`tests/`。

### B. 海外平台（调研轮次 1，官方一手为主）
- Meta Insights breakdowns：https://developers.facebook.com/docs/marketing-api/insights/breakdowns/
- Meta Insights best-practices（15min 刷新 / 28 天冻结）：https://developers.facebook.com/docs/marketing-api/insights/best-practices/
- Meta Graph API rate-limiting（BUC 滚动 1h）：https://developers.facebook.com/docs/graph-api/overview/rate-limiting/
- Meta Marketing API rate-limiting（dev tier 300/600）：https://developers.facebook.com/docs/marketing-api/overview/rate-limiting/
- Meta Ad Rule / Schedule Spec（SEMI_HOURLY 30min）：https://developers.facebook.com/docs/marketing-api/reference/ad-rule/ · https://developers.facebook.com/docs/marketing-api/reference/ad-rule-schedule-spec
- Meta 自动规则帮助：https://www.facebook.com/business/help/222640851458826
- Meta Rebalance Budget 指南：https://developers.facebook.com/docs/marketing-api/ad-rules/guides/rebalance-budget
- Meta 归因/数据保留变更：https://ppc.land/meta-restricts-attribution-windows-and-data-retention-in-ads-insights-api/
- ROAS ~7 天稳（blog，中等可信）：https://seresa.io/blog/attribution-measurement/your-meta-roas-catches-up-three-days-later
- TikTok 学习期：https://ads.tiktok.com/help/article/learning-phase

### C. 国内平台（调研轮次 2 + hands-on + Jina）
- 巨量官方 Go SDK（端点/枚举一手）：https://github.com/oceanengine/ad_open_sdk_go
- 巨量报表模型（pkg.go.dev 镜像）：https://pkg.go.dev/github.com/bububa/oceanengine/marketing-api/model/local/report
- 巨量数据报表文档（数据延迟/回溯，经 Jina 渲染）：https://open.oceanengine.com/labels/7/docs/1696710549068815
- 巨量入门指南（OAuth/频控机制，经 Jina）：https://open.oceanengine.com/labels/34
- 巨量 Marketing API 对接（CSDN 二手，频控机制）：https://blog.csdn.net/mengfeichuan2013/article/details/144426129
- 腾讯 hourly_reports/get：https://developers.e.qq.com/docs/api/insights/ad_insights/hourly_reports_get
- 腾讯 daily_reports/get：https://developers.e.qq.com/v3.0/docs/api/daily_reports/get
- 腾讯 tracking_reports/get（time_granularity {DAILY,HOURLY}）：https://developers.e.qq.com/docs/api/insights/tracking_reports/tracking_reports_get
- 腾讯 realtime_cost/get：https://developers.e.qq.com/docs/api/tools/realtime_cost/realtime_cost_get
- 腾讯 campaigns/update（写操作字段）：https://developers.e.qq.com/docs/api/adsmanagement/campaigns/campaigns_update
- 腾讯频控升级预告（qpm/开发者分级）：https://developers.e.qq.com/v3.0/pages/news/info/20241025
- 腾讯自动规则 FAQ（每小时/无法实时）：https://tencentads.com/Faqlist/Detail/677
- 腾讯 changelog：https://developers.e.qq.com/docs/start/changelog/api
- 腾讯报表 FAQ（30 分钟生成/30 天回溯）：https://developers.e.qq.com/tools/faq/insights
- 快手磁力开放平台：https://developers.e.kuaishou.com/ · 报表粒度二手：https://www.juxuan.net/18033.html · ThinkingData 快手集成：https://docs.thinkingdata.cn/ta-manual/latest/user_guide/data/thirdparty/thirdparty_kuaishou/thirdparty_kuaishou_account_report.html
- TikTok（Airbyte 连接器行为 / 官方归因）：https://docs.airbyte.com/integrations/sources/tiktok-marketing · https://ads.tiktok.com/help/article/about-the-attribution-window

### D. 调研统计
- 轮次 1（海外）：6 角度 / 25 源 / 59 claim → 19 确认、6 否决；108 agent。
- 轮次 2（国内）：6 角度 / 28 源 / 70 claim → 18 确认、7 否决；111 agent。
- hands-on：~15 次 WebSearch/WebFetch + Jina Reader 渲染巨量 SPA。

---

*生成于 2026-06，由 Claude 综合本轮全部调研与代码审计。后续若拿到巨量后台 QPS/学习期一手数据，或快手完整能力面，请回填 Part 2.4 与 Part 5。*
