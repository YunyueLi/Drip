<div align="center">

# Drip

### 一个 agent，替掉一支 5 人 UA 团队。

**面向二次元 / 抽卡手游的开源自主用户增长 agent。**
自动生成创意 · 仿真目标受众 · 跨平台投放 · 给出下一步决策。

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-3776ab.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/YunyueLi/Drip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/YunyueLi/Drip/actions)
[![Stars](https://img.shields.io/github/stars/YunyueLi/Drip?style=flat-square&color=fbbf24)](https://github.com/YunyueLi/Drip/stargazers)
[![X follow](https://img.shields.io/twitter/follow/drip_agent?style=flat-square&label=%40drip_agent&color=000)](https://x.com/drip_agent)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg?style=flat-square)](#status)

[**快速开始**](#%EF%B8%8F-快速开始) · [**架构原理**](#-架构原理) · [**Roadmap**](#%EF%B8%8F-路线图) · [**贡献**](CONTRIBUTING.md) · [**Discord**](https://discord.gg/drip-agent)

[English](README.md) · **简体中文**

</div>

---

> 二次元 / 抽卡手游每年在用户增长上烧掉 **50 亿美元+**。今天仍是手动写每一条创意、人肉看每一张报表、靠经验跑每一次 A/B。
>
> Drip 就是替你做这件事的 agent —— 端到端、默认 shadow 模式、有真实人工兜底。

```text
$ drip launch --game ./astral-drift.yaml --budget 500 --regions jp,sg,tw

▸ creative
  通过 claude-agent-sdk 头脑风暴出 6 个创意
  [1/6] 飞花飘落中 Hina 出场的电影感开场 ………………………… 3.2s
  [2/6] Riku 释放标志性技能的玩法 hero shot ………………… 4.1s
  …
  产出 6 条候选创意 (gpt-image-2 + Seedance 2.0)

▸ audience
  通过 OASIS 仿真 5,000 个合成二次元玩家
    ctr≈1.62%  install≈0.11%  飞花飘落中 Hina 出场…
    ctr≈1.54%  install≈0.10%  玩法 hero shot —— Riku…
    ctr≈1.41%  install≈0.09%  Vesper 情感高潮揭示…

▸ bidding
  规划出 18 个广告组,覆盖 3 个地区 × 2 个平台
  [shadow 模式] 不推送至投放平台

▸ reporter
  花费 $432  →  5,234 安装  →  CPI $0.083  →  D7 ROAS 36%
  建议:暂停 Meta SG,把 TikTok JP 放量 +50%
```

---

## ✨ Drip 在做什么

六步,一条命令,一个 agent。

| # | 步骤 | 在做什么 | 由谁驱动 |
|---|---|---|---|
| 1 | **创意头脑风暴** | 每次跑出 6 个二次元调性的广告概念 | `claude-agent-sdk` |
| 2 | **生成关键帧** | 角色 hero 立绘 + 多语言 CTA,1024–2048px | OpenAI `gpt-image-2` |
| 3 | **生成视频** | 6 秒竖版短片,适配 Reels / TikTok | 字节跳动 `Seedance 2.0` |
| 4 | **预测群体反应** | 烧钱之前,先让 5,000 个合成玩家替你试一次 | CAMEL-AI `OASIS` |
| 5 | **规划与投放** | 自动按地区 × 平台分配预算 | `MCP` · Meta + TikTok |
| 6 | **报告** | 自然语言总结 · 排序好的决策 · 下一步动作 | Claude `Haiku 4.5` |

> **注** —— 每一步都有降级。哪怕一个 API key 都没配,`drip demo` 依然能用确定性 stub 跑通完整 pipeline。飞机上也能看代码。

---

## 🎯 为什么是现在

**2025–2026** 三件事改变了游戏:

**1. 投放平台 AI 已经吃掉了出价层。**
Meta GEM、AppLovin AXON 2.0、TikTok Smart+、Unity Vector —— 它们已经把"调出价"这件事自动化掉了。光 AppLovin 一家,每个季度跑 14 亿美元的软件营收都来自 AXON。新的战场是**创意 pipeline 和跨平台编排**。

**2. 二次元这一垂类仍然是空白。**
Sett 拿了 3000 万美元 B 轮做泛手游 UA agent —— *闭源*。二次元 / 抽卡每年烧 50 亿+ 美元做 UA,却仍是手工生产每一条创意。**这个领域没有像样的开源对手。**

**3. Agent 栈终于成熟了。**
`claude-sonnet-4-6` + Agent SDK 今天就能用了,且具备真金白银决策需要的确定性。`gpt-image-2` 和 `Seedance 2.0` 能产出多语言 CTA 和电影感 6 秒短片,**每条成本 < $0.20**。

Drip 就是缺失的那一块拼图。

---

## ⚡️ 快速开始

**环境要求:** Python **3.11**(OASIS 锁了 `<3.12`),推荐用 [`uv`](https://docs.astral.sh/uv/)。

```bash
# 1. 克隆 & 进入
git clone https://github.com/YunyueLi/Drip.git
cd Drip

# 2. 安装
uv venv -p 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. 配置
cp .env.example .env  # 最少配一个 ANTHROPIC_API_KEY 即可

# 4. Dry-run(完全离线)
drip demo

# 5. Live(默认 shadow 模式 —— 规划但不真投)
drip launch \
  --game ./examples/demo_game.yaml \
  --budget 500 \
  --regions jp,sg,tw
```

详细步骤见 [`docs/quickstart.md`](docs/quickstart.md)。

---

## 🧠 架构原理

Drip 是基于 Anthropic Claude Agent SDK 的 **supervisor + workers** 多 agent 系统。Supervisor 持有运行生命周期、预算和 HITL 审批门;每个 worker 是一个领域专家,把结构化结果交回给 supervisor;supervisor 决定下一步。

```
                    ┌──────────────────────────────┐
                    │   Drip Supervisor            │   claude-agent-sdk
                    │   (Sonnet 4.6)               │   supervisor pattern
                    └──────────────────────────────┘
                                │
       ┌────────────┬───────────┼───────────┬─────────────┐
       ▼            ▼           ▼           ▼             ▼
  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐
  │Creative │ │ Audience │ │ Bidding │ │ Reporter│ │  Eval    │
  │Sonnet + │ │ OASIS    │ │ Sonnet  │ │  Haiku  │ │ Trajectory│
  │Seedance │ │ 仿真     │ │         │ │         │ │          │
  └─────────┘ └──────────┘ └─────────┘ └─────────┘ └──────────┘
       │            │           │           │
       └────────────┴───────────┴───────────┘
                         │
                         ▼
            ┌────────────────────────────────┐
            │   MCP 工具层                    │
            │   meta-ads · tiktok-ads        │
            │   appsflyer · gpt-image · …    │
            └────────────────────────────────┘
```

### 设计原则

- **默认 shadow 模式。** 真正写入投放平台需要 `DRIP_MODE != shadow` *并且* 配置好 token。哪怕忘了安全检查也烧不到钱。
- **预算上限是硬墙。** `DRIP_BUDGET_CAP` 在 supervisor 启动之前就会被强制执行。
- **Adapter 优雅降级。** 没有 API key?Adapter 返回确定性 stub,`drip demo` 在飞机上也能跑。
- **Worker 是 context 的纯函数。** 输入 `RunContext`,返回 `WorkerResult`。零全局状态,易测试,易替换。
- **Provider 可换。** 把 `gpt-image-2` 换成 Midjourney、把 Seedance 换成可灵 —— 改一个文件就行。

完整设计笔记见 [`docs/architecture.md`](docs/architecture.md)。

---

## 📦 `v0.0.1` 都有什么

```
drip/
├── src/drip/
│   ├── cli.py               drip launch / demo / eval
│   ├── orchestrator.py      supervisor、RunContext、RunMode
│   ├── workers/
│   │   ├── creative.py      → gpt-image-2 + Seedance 2.0
│   │   ├── audience.py      → OASIS 社交仿真
│   │   ├── bidding.py       → 跨平台预算分配
│   │   └── reporter.py      → 自然语言总结
│   ├── adapters/            ← provider 特定层,可换
│   └── eval/bench.py        Drip-Bench v0(案例征集中)
├── examples/demo_game.yaml  虚构示例游戏配置
├── web/index.html           drip.dev landing
└── docs/                    架构、快速开始
```

---

## 🛠️ 配置项

全部通过 `.env` 配置(完整列表见 [`.env.example`](.env.example))。

| 变量 | 是否必需 | 用途 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 必需 | Claude Agent SDK + 所有 worker 大脑 |
| `OPENAI_API_KEY` | live 必需 | `gpt-image-2` 关键帧 |
| `ARK_API_KEY` | live 必需 | 字节跳动 Seedance 2.0(火山引擎 ARK) |
| `META_ACCESS_TOKEN` | live 必需 | Meta Marketing API |
| `TIKTOK_ACCESS_TOKEN` | live 必需 | TikTok Marketing API |
| `APPSFLYER_API_TOKEN` | 可选 | 归因 / MMP |
| `LANGFUSE_*` | 可选 | Trace + 成本可观测 |
| `DRIP_MODE` | — | `shadow`(默认) · `copilot` · `autonomous` |
| `DRIP_BUDGET_CAP` | — | 单次运行的硬预算上限(USD) |

---

## 🗺️ 路线图

### `v0.0.1` — Day 0 *(当前)*
- [x] 项目脚手架、CLI、orchestrator 骨架
- [x] 四个 Worker(Creative / Audience / Bidding / Reporter)
- [x] Adapter:gpt-image-2、Seedance 2.0、OASIS、MCP-ready 投放层
- [x] 三档运行模式(shadow / copilot / autonomous)
- [x] 预算硬上限
- [x] Apache-2.0 + CI + issue/PR 模板

### `v0.1` — Week 2–4
- [ ] Claude Agent SDK subagent 替换掉确定性的概念头脑风暴
- [ ] OASIS audience profile 针对二次元玩家调参(JP / TW / SG / KR)
- [ ] 在真实 Meta 测试账户上首次端到端 run
- [ ] Drip-Bench 前 20 个 case
- [ ] Langfuse trace + 成本 dashboard

### `v0.2` — Month 2
- [ ] 真正的 Supervisor agent(把固定 pipeline 换成动态路由)
- [ ] TikTok 创意变体(9:16 竖版,6s / 15s)
- [ ] LiveOps Tie-in worker(版本卡池 → 创意自动切换)
- [ ] KOL Scout worker(HoYoCreators / Twitch / YouTube 红人选品)
- [ ] 公开 Discord + 首批社区贡献者

### `v1.0` — Quarter 2
- [ ] 多市场联跑(JP + SEA + NA + EU + KR)
- [ ] 同发行商多游戏 cross-promotion
- [ ] PyPI 发布,完整 Drip-Bench(50+ case)
- [ ] 公开 AdLoop-Bench leaderboard 给整个社区

跟进进度:[@drip_agent](https://x.com/drip_agent)。

---

## 🤝 贡献

Drip 还在 early alpha。当下最有价值的贡献:

1. **拿真实的二次元 / 抽卡游戏试跑**,把坏掉的地方提 issue。
2. **贡献 Drip-Bench 案例** —— 我们需要 20 个手工挑选的 UA 决策 case。详见 [#3](https://github.com/YunyueLi/Drip/issues/3)。
3. **新平台 adapter** —— Apple Search Ads、Pangle、巨量引擎。每个都是大概 150 行的小 PR。
4. **改进 worker**,尤其是 `creative.py`(创意头脑风暴)和 `bidding.py`(预算分配策略)。

开发环境见 [CONTRIBUTING.md](CONTRIBUTING.md)。提 PR 前请确保 `ruff check .` · `mypy src` · `pytest` 全绿。

---

## 🙏 致谢

Drip 站在以下肩膀上:

- [**Anthropic Claude Agent SDK**](https://github.com/anthropics/claude-agent-sdk-python) —— supervisor runtime
- [**CAMEL-AI OASIS**](https://github.com/camel-ai/oasis) —— 百万级 agent 社交仿真
- [**pipeboard-co/meta-ads-mcp**](https://github.com/pipeboard-co/meta-ads-mcp) —— Meta Ads MCP
- [**amekala/ads-mcp**](https://github.com/amekala/ads-mcp) —— 多平台 ads MCP
- [**火山引擎 ARK**](https://www.volcengine.com/product/ark) —— Seedance 2.0
- [**OpenAI Images API**](https://openai.com/api/) —— `gpt-image-2`
- [**Langfuse**](https://langfuse.com) —— 开源 LLM observability

以及那些证明了这个赛道值得做的 prior art:[**Sett**](https://www.sett.ai/)、[**Kohort**](https://www.kohort.ai/)、[**AppsFlyer Agent Hub**](https://www.appsflyer.com/products/agentic-ai/)。

---

## 📜 License

[Apache 2.0](LICENSE) —— 用它、fork 它、装船。保留 NOTICE 就行。

---

<div align="center">

**Drip** · Built in the open by [@YunyueLi](https://github.com/YunyueLi)

如果 Drip 替你省下一周,给个 ⭐ —— 这是我们唯一的指标。

</div>
