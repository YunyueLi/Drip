<div align="center">

<img src="https://img.shields.io/badge/Drip-UA_Agents-0052d9?style=for-the-badge&labelColor=0a0a0a" alt="Drip" />

# Drip

### 开源的买量(UA)增长团队。

**一条命令跑完整条闭环** —— 采集 → 诊断 → 策略 → 创意 → 分配 → 学习。每个决策都**基于规则、可审计**;方向盘始终在你手里。任意 LLM、任意广告平台、可完全自托管。

<br/>

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Release](https://img.shields.io/badge/release-v0.0.7-0052d9.svg?style=flat-square)](https://github.com/YunyueLi/Drip/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/YunyueLi/Drip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/YunyueLi/Drip/actions)
[![Tests](https://img.shields.io/badge/tests-passing-22c55e.svg?style=flat-square)](tests/)
[![Stars](https://img.shields.io/github/stars/YunyueLi/Drip?style=flat-square&color=fbbf24)](https://github.com/YunyueLi/Drip/stargazers)

[**▶ 在线控制台**](https://yunyueli.github.io/Drip/app.html) · [**快速开始**](#-快速开始) · [**运作原理**](#-运作原理) · [**Drip-Bench**](#-drip-bench) · [**开源 vs 闭源**](#-开源-vs-闭源) · [**路线图**](#%EF%B8%8F-路线图)

[English](README.md) · **简体中文**

</div>

<div align="center">

<a href="https://yunyueli.github.io/Drip/app.html"><img src="assets/decision-card.svg" alt="Drip 决策卡 —— 8 信号向量、规则链、置信度与动作" width="720" /></a>

<sub>每条 campaign 用 **8 个信号**打分 → 规则给出决策 → 一张带**「为什么」**的可审计决策卡。动钱之前你拍板。**[▶ 打开在线控制台 →](https://yunyueli.github.io/Drip/app.html)** · 10 种语言</sub>

</div>

---

> 投放团队现在有一波 AI agent —— Sett、Kohort、GrowthGPT、Meta GEM。它们做的事大同小异,也都有同一个毛病:**它们不告诉你「为什么」。** 价格不透明、LLM 藏着、规则藏着、prompt 藏着、你的数据在它们服务器上,还有「CPA 降 70%」却拿不出可验证案例的说辞。
>
> **Drip 是开源的那个答案** —— 把整条买量闭环做成一队你能**读、能跑、能 fork、能自托管**的 agent。决策内核是**确定性、可审计**的;LLM 只负责把「为什么」讲给人听。信它,是因为你能**核查**它。

```console
$ drip run --budget 1000

  one-stop run · 2026-05-21 → 2026-05-28 · budget $1,000

  ▸ diagnosis   Scanned 4 campaigns, $880 spend. Decisions: 2 SCALE, 2 PAUSE.
  ▸ strategy    [scale] Meta_Prospecting_v3 — 3 variants on the winning hook
                [cut]   TikTok_Broad_v1     — test a fresh angle
  ▸ creative    3 variants produced
  ▸ allocation  meta   Meta_Prospecting_v3    SCALE  →  $500
                tiktok TikTok_Prospecting_v3  SCALE  →  $500
                meta   Meta_Broad_v1          PAUSE  →  $0
  ▸ feedback    winner CTR 1.40% is the bar for the next creatives
```

<div align="center"><sub>开箱即用,离线跑样本数据。插上凭据 + LLM 即可上线 —— 决策引擎本身一行都不用改。</sub></div>

---

## ✨ Drip 能做什么

一支完整的增长团队,六个角色、一条闭环、一条命令:

| 步骤 | Agent | 做什么 | 由谁驱动 |
|---|---|---|---|
| 1 · **采集** | `collectors` | 拉取跨平台数据,归一到同一套 schema | Meta / TikTok SDK · 离线样本 |
| 2 · **诊断** | `analyst` | 给每条 campaign 打分、扫异常、写报告 | 决策引擎 + LLM |
| 3 · **策略** | `strategist` | 排赢家/输家,提下一个创意测试 | LLM |
| 4 · **创意** | `creative` | 为赢家方向产出广告变体 | gpt-image / Seedance / ComfyUI |
| 5 · **分配** | `allocator` | 跨平台再分预算 —— 喂赢家、饿输家 | 决策引擎 |
| 6 · **学习** | `feedback` | 萃取赢点,回灌下一轮 | —— |

外加 **`attribution`** (平台口径 vs MMP 真值对账),以及每一次 scale/pause 都要走的 **8 信号决策引擎**。

> **关键:** 动作由**规则在 8 个信号上**算出 —— 确定性、可解释、可回放。LLM 只写给人看的「为什么」。这才是你敢把真金白银交给它的原因。

---

## 🖥️ 控制台

一个聊天驱动的控制室,管完整条闭环 —— 诊断、决策、分配、创意,并自证。它不是黑盒:每个决策都能在侧栏展开它的 **8 信号向量 + 规则链 + 回放**,动手批准之前你看得清「为什么」。

- **决策队列** —— scale / refresh / pause,每条展开 **8 信号向量 + 规则链 + 置信度**,一键批准。
- **预算分配** —— 从输家释放的预算,在日预算上限内、跨平台流向赢家。
- **增长策略** —— 咨询级增长方案:人群画像、竞争矩阵、预算切分,每项都带理由。
- **Drip-Bench** —— 买量 agent 决策的开放、可复现排行榜。

截图会过时,在线控制台不会 —— 直接上手看真的:

<div align="center"><b><a href="https://yunyueli.github.io/Drip/app.html">▶ 打开在线控制台,免安装 →</a></b></div>

---

## 🧠 运作原理

```
                         drip run  /  LangGraph daemon
                                    │
   ┌──────────────────────── the one-stop loop ───────────────────────┐
   │                                                                   │
   ▼                                                                   │
 Collect ─▶ Diagnose ─▶ Strategize ─▶ Create ─▶ Allocate ─▶ Learn ─────┘
   │           │                                    │          (feeds next cycle)
   │           ▼                                    ▼
   │   ┌─────────────────────┐            human approval gate
   │   │  Decision Engine    │            (before any spend)
   │   │  8 signals → rules  │
   │   │  → card + "why"     │   ◀── deterministic core; LLM only narrates
   │   └─────────────────────┘
   ▼
 AdMetrics  ◀── one cross-platform data contract every agent speaks
   │
   └─▶ Slots (swap any):  LLM ·  bidding ·  LTV ·  creative gen ·  ads write
```

一条 campaign 的指标命中 **8 个信号**(CPP、ROAS、CVR、CTR、频次、花费、转化数、预算余量)→ 每个判红/黄/绿 → **规则**产出 `SCALE / PAUSE / HOLD / REDUCE / REFRESH` 决策,带置信度、护栏和可审计的规则链。样本薄?它就保守放量并把置信度封顶 —— 和资深买手一样的判断。

完整设计见:[`docs/architecture.md`](docs/architecture.md) · [`docs/vision.md`](docs/vision.md) · 平台能力调研与实时控制设计见 [`docs/intraday-research.md`](docs/intraday-research.md)。

---

## ⚙️ 它还会执行 —— 而且安全

闭环不止于一个方案。三条命令把它推到平台,且都走同一套资金安全阶梯:

- **`drip apply`** —— 把 scale / pause / 预算决策写到 **Meta · 腾讯 · 巨量 · 快手**(按平台自动路由)。每次写都先快照旧值、写后回读校验,并落入审计留痕。
- **`drip watch`** —— 盘中**花费侧**守卫:小时级 pacing / 成本突刺 / 防超投 —— 在预算失控前限速或暂停。
- **`drip autopilot`** —— 整条闭环,**按信号路由**(止血优先 → 再放量 / 换创意 / 分配),背后有**熔断器**,遇数据异常或写入失败即停。

每次写入都遵守 `DRIP_BUDGET_CAP` + `DRIP_MAX_CHANGE_PCT`(不做会重置学习期的大跳)和 `DRIP_MODE` —— **shadow**(只规划)→ **copilot**(逐条批准)→ **autonomous**(闸内自动)。没有平台 token 就保持 shadow,所以放哪跑都安全。

---

## ⚡ 快速开始

**需要** Python **3.11**(推荐 [`uv`](https://docs.astral.sh/uv/))。

```bash
git clone https://github.com/YunyueLi/Drip.git && cd Drip
uv venv -p 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"

drip run                       # 整条闭环,端到端(离线样本)
drip doctor                    # 诊断一个账户 → 决策卡
drip apply                     # 采集 → 决策 → 写到 Meta/腾讯/巨量/快手(默认 shadow)
drip watch --once              # 盘中花费侧守卫:pacing / 成本突刺 / 防超投
drip autopilot                 # 整条闭环,信号路由 + 熔断(默认 shadow)
drip bench run --agent claude  # 在 10 个买量决策上给任意 agent 打分
drip llm                       # 12 个模型 provider,用 provider/model 寻址
```

上线:设置 `ANTHROPIC_API_KEY` + 一个 Meta System User token,`uv pip install -e ".[all]"`,然后 `drip apply --mode copilot` —— Drip 拉真实数据、把每条 scale/pause 连同「为什么」摆给你看,只写你批准的(受 `DRIP_BUDGET_CAP` + `DRIP_MAX_CHANGE_PCT` 约束、每笔审计)。在你选 `copilot`/`autonomous` 之前,花费始终停在 **shadow**。完整路径见 [`docs/deploy.md`](docs/deploy.md)。

---

## 🧩 这些 agent

每个都是一个小而框架无关、能一口气读完的模块:

```
src/drip/
  collectors.py    拉数据 —— Meta · TikTok · 腾讯 · 巨量 · 快手(+ 离线样本)
  analyst.py       诊断 + 异常扫描 + 报告
  strategist.py    从表现里提下一个创意测试
  creative.py      产出变体(编排外部生成器)
  allocator.py     跨平台预算分配
  attribution.py   平台口径 vs MMP 真值对账
  feedback.py      学习 → 下一轮
  engine/          决策内核:signals → rules → cards · 盘中花费侧
  adapters/        广告写入(Meta + 腾讯/巨量/快手) · 创意生成 · 竞价 · LTV
  safety.py        预算 + 学习期护栏 · append-only 审计留痕
  supervisor.py    信号驱动的自主编排(路由 + 熔断器)
  pipeline.py      一站式闭环      graph.py  LangGraph 生产 daemon
  llm/             12 provider LLM 层  eval/     Drip-Bench
```

---

## 🔌 一切皆可自带

Drip 负责编排、判断和评测。每一个「打不赢 / 没数据」的硬骨头都是一个**可替换插槽**,带离线兜底 —— 没有任何锁定。

| 插槽 | 可插入 | 默认(离线) |
|---|---|---|
| **LLM** | Claude · GPT · Gemini · Qwen · DeepSeek · Grok · 本地…(12 个 + OpenRouter 兜底) | 模板(无 key) |
| **创意生成** | gpt-image · Seedance · ComfyUI · Arcads | dry 占位 |
| **广告平台写入** | Meta Marketing API · 腾讯 / 巨量 / 快手 REST | copilot/autonomous 之前为 shadow |
| **LTV / 价值** | Kohort · Voyantis · 你的模型 | 启发式 |
| **归因真值** | AppsFlyer · Adjust | 文档化 haircut |

---

## 📊 Drip-Bench

第一个**开放、可复现**的买量 agent 决策基准。10 个精选案例(放量、暂停、再分配、创意衰退、异常诊断、cohort、人群扩展、出价策略、市场进入、危机应对),三段式评分(动作 40 / 方向 20 / 推理 40),以及一个可插拔的 agent 接口。

```bash
drip bench run --agent drip:openai/gpt-4o   # 任意 provider/model
drip bench run --agent claude               # 对比裸 Claude
```

每次运行都产出可复现的 bundle。做了个买量 agent?拿它跑 Drip-Bench 然后 PR 结果上来 —— 赢输都行。我们也公开自己的。见 [`benchmarks/`](benchmarks/)。

---

## 🆚 开源 vs 闭源

| | Sett · Kohort · GrowthGPT | **Drip** |
|---|---|---|
| 代码 | 闭源 | **Apache-2.0** |
| 决策逻辑 | 黑盒 | **在 `src/drip/` 里读** |
| 决策为何发生 | 「信我就好」 | **信号向量 + 规则链 + 回放** |
| LLM | 绑定厂商 | **12 个任选 + 本地** |
| 跨平台 | 各自为政 | **中立,跨平台优化** |
| 数据 | 在它们服务器 | **在你这** |
| 评测 | 营销话术 | **Drip-Bench,可复现** |
| 价格 | $99–$999+/月 | **免费 · 自托管** |

我们不声称 Drip 今天在纯效果上赢过它们。我们声称:它是唯一一个你能**审计、fork、并在自己环境里运行**的 —— 也是唯一一个评测可复现的。

---

## 🛟 默认安全

资金安全是阶梯,不是开关(`DRIP_MODE`):

- **`shadow`**(默认)—— 只规划,绝不写平台
- **`copilot`** —— 每次写都等人工批准
- **`autonomous`** —— 在 `DRIP_BUDGET_CAP` 内自动写,启动前先校验

LangGraph daemon 还加了一道**花钱前 interrupt** 闸 —— 由人签字确认预算动作,再从断点恢复运行。问责始终落在一个人身上;执行则朝「无人值守」逐步放开。

---

## 🗺️ 路线图

路线图**由 bench 驱动** —— 每次发版都公布它的 Drip-Bench 分。

- [x] 8 信号决策引擎 · 12 provider LLM 层 · 竞价/价值插槽
- [x] **7 个 agent + 端到端一站式管线** · `drip run`
- [x] Drip-Bench v0(10 案例)· LangGraph 生产图
- [x] **聊天驱动控制台**(10 语种)+ 平台能力调研([`docs/intraday-research.md`](docs/intraday-research.md))
- [x] **Meta 写入路径** —— `drip apply` 把 scale/pause 写到活的 campaign(copilot 批准 · 预算 + 学习期护栏 · 审计)
- [ ] **首次真账户 live 写入验证**(插上你的 token,`drip apply --mode copilot`)
- [x] **盘中花费侧层** —— `drip watch`:小时级 pacing / 成本突刺 / 防超投(带闸 + 审计)
- [ ] 公开 Drip-Bench 排行榜 + baseline 跑分
- [x] **自主编排** —— `drip autopilot`:信号驱动的 supervisor(路由 + 熔断器),确定性且可审计
- [x] **国内平台写入** —— 腾讯 / 巨量 / 快手,由 `drip apply` + `drip watch` 路由(带闸 + 审计;live 验证待凭据)
- [ ] Knowledge Packs —— 垂类信号/prompt 覆盖(二次元、DTC、工具 app…)

构建日志:[@drip_agent](https://x.com/drip_agent) · [CHANGELOG](CHANGELOG.md)。

---

## 🤝 参与贡献

当下杠杆最高的贡献:

1. **跑 Drip-Bench** —— 对任意 agent(你的、我们的、对手的),把 bundle PR 上来。
2. **加一个 benchmark 案例**([`benchmarks/SCHEMA.md`](benchmarks/SCHEMA.md))—— 需 ≥3 位 reviewer 签字,且必须有区分度。
3. **Knowledge Packs** —— 纯 YAML 的垂类基线/prompt,不用写 Python。
4. **Provider adapter** —— Apple Search Ads、巨量引擎、腾讯广告、快手。约 150 行的 PR。

环境见 [CONTRIBUTING.md](CONTRIBUTING.md)。PR 需通过 `ruff check .`、`mypy src`、`pytest`。

---

## 🙏 致谢

基于 [Anthropic Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)、[LangGraph](https://github.com/langchain-ai/langgraph)、[CAMEL-AI OASIS](https://github.com/camel-ai/oasis)、[PyMC-Marketing](https://github.com/pymc-labs/pymc-marketing)、[meta-ads-mcp](https://github.com/pipeboard-co/meta-ads-mcp) 构建。验证过这个赛道的前作:[Sett](https://www.sett.ai/)、[Kohort](https://www.kohort.ai/)、[GrowthGPT](https://growthgpt.app/)。

---

## 📜 许可

[Apache 2.0](LICENSE) —— 用它、fork 它、发布它。

<div align="center">
<br/>

<img src="assets/droplet.svg" width="116" alt="Drip" />

**Drip** · 由 [@YunyueLi](https://github.com/YunyueLi) 在开源世界里构建

如果 Drip 帮你省下一周 —— 或帮这个行业少一个无法验证的 benchmark 说辞 —— 给个 ⭐
</div>
