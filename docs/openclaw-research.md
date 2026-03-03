# OpenClaw 深度调研报告

> 调研日期：2026-03-03 | OpenClaw 版本：2026.3.1

## 目录

- [项目概述](#项目概述)
- [当前环境](#当前环境)
- [核心架构](#核心架构)
- [Skill 系统详解](#skill-系统详解)
- [ClawHub 技能市场](#clawhub-技能市场)
- [优秀开源案例](#优秀开源案例)
- [Skill 开发最佳实践](#skill-开发最佳实践)
- [Sentinel Skill 优化建议](#sentinel-skill-优化建议)
- [安全注意事项](#安全注意事项)
- [学习资源](#学习资源)

---

## 项目概述

**OpenClaw** 是一个开源自主 AI Agent 框架，由 PSPDFKit 创始人 Peter Steinberger 创建。GitHub **247,000+ stars**，2026 年初最火的开源 AI agent 项目。2026.2.14 Steinberger 宣布加入 OpenAI，项目转移到开源基金会。

**演化路径**: Clawdbot → Moltbot → OpenClaw

**核心定位**: 不只是聊天机器人，而是一个 **Agent 操作系统** — 管理身份、会话、权限，通过 Skills 扩展能力，跨平台消息路由。

**官方仓库与资源**:

| 资源 | 链接 |
|---|---|
| 主仓库 | https://github.com/openclaw/openclaw |
| 官方文档 | https://docs.openclaw.ai |
| ClawHub (Skill 市场) | https://clawhub.ai |
| 官方 Skills 仓库 | https://github.com/openclaw/skills |
| Discord 社区 | https://discord.gg/clawd |

---

## 当前环境

| 项目 | 值 |
|---|---|
| 版本 | **2026.3.1** (最新 2026.3.2 可更新) |
| 安装方式 | npm 全局安装 (`~/.nvm/versions/node/v22.15.0/bin/openclaw`) |
| Gateway | `ws://127.0.0.1:18789` (本地 loopback, pid 58820) |
| Dashboard | http://127.0.0.1:18789/ |
| 主模型 | `google-gemini-cli/gemini-3-pro-preview` |
| 备选模型 | `qwen-portal/coder-model`, `qwen-portal/vision-model` |
| 工作区 | `/Users/lan/clawd` |
| 配置文件 | `~/.openclaw/openclaw.json` |
| 通道 | Telegram (已配置, groupPolicy=open) |
| 会话 | 11 个活跃 |
| Agent | 1 个 ("Kobe 个人股票助手") |

### 已安装 Skills (20/58 ready)

**自定义 Skills** (4个, 在 `~/.openclaw/skills/`):

| Skill | 描述 | 来源 |
|---|---|---|
| sentinel | A股智能投顾哨兵 | 符号链接 → `/Users/lan/Desktop/code/ai_sentiney` |
| gosh-ops | Gosh 运维智能助手 | 符号链接 → `/Users/lan/Desktop/gosh_code/gosh_clawd_bot` |
| daily-briefing | Gosh 平台 AI 业务日报 | 符号链接 → gosh_admin_fe 子目录 |
| gosh-recruitment-playbook | Talent Scout Copilot | 本地目录 |

**已就绪的内置 Skills**: coding-agent, gemini, gh-issues, github, openai-image-gen, openai-whisper-api, summarize, wacli, weather 等。

### 残留的旧服务

本地检测到多个 gateway 服务共存（建议清理）:
- `ai.openclaw.gateway` (当前, OpenClaw 2026.3.1)
- `bot.molt.gateway` (旧版 Molt)
- `com.clawdbot.feishu-bridge` (旧版 ClawdBot)
- `com.clawdbot.gateway` (旧版 ClawdBot)

---

## 核心架构

```
用户消息 (Telegram / Discord / WhatsApp / Slack / Feishu)
    ↓
  Gateway (WebSocket, port 18789)
    ↓
  Agent Router (匹配 skill、session 管理)
    ↓
  Skill 执行 (SKILL.md 指令 + 工具调用)
    ↓
  结果返回用户
```

### 三大核心能力

1. **Skills** - Markdown 驱动的可组合能力单元，遵循 AgentSkills 开放标准（Anthropic 发布，OpenAI Codex 也采用）
2. **Channels** - 跨平台消息路由（Telegram/Discord/Slack/WhatsApp/Signal/Feishu）
3. **Memory** - 持久记忆系统，跨会话保留上下文（向量搜索 + FTS）

### 技术栈

- 运行时基于 **Pi Agent 框架** (TypeScript: pi-agent-core, pi-ai, pi-coding-agent)
- 6 阶段执行管线
- 9 层工具权限系统
- 串行默认队列
- 混合记忆搜索 (vector + FTS)

---

## Skill 系统详解

### 加载优先级（高 → 低）

1. **Workspace skills**: `<workspace>/skills/` (当前工作区，最高优先级)
2. **Managed/local skills**: `~/.openclaw/skills/` (跨 agent 共享)
3. **Bundled skills**: npm 包自带的 58 个内置 skill

### 三级加载机制

| 级别 | 内容 | 何时加载 | Token 消耗 |
|---|---|---|---|
| Level 1 | YAML frontmatter (name, description, triggers) | **始终加载** | 极小 (~24 tokens/skill) |
| Level 2 | Markdown body (具体指令/runbook) | **触发时加载** | 中等 |
| Level 3 | `references/` 目录 (详细文档) | **按需加载** | 按需 |

### SKILL.md 格式

```yaml
---
name: my-skill
description: Does a thing with an API. Use when the user asks to "do X" or "check Y".
metadata:
  openclaw:
    emoji: '🔧'
    requires:
      bins: ['python3', 'curl']      # 二进制依赖
      env: ['MY_API_KEY']            # 环境变量依赖
    primaryEnv: MY_API_KEY           # 主要 API key
    skillKey: my-skill               # 用于 config entries 匹配
user-invocable: true                 # 支持 /my-skill 直接触发
---

# My Skill

## 使用方式
具体的命令和使用说明...

## 使用场景
路由规则和触发条件...
```

### Skill 目录结构

```
skill-name/
├── SKILL.md          # 必须：指令 + 元数据
├── scripts/          # 可选：可执行代码
├── references/       # 可选：详细文档 (Level 3 加载)
├── examples/         # 可选：示例
└── assets/           # 可选：模板、图片等
```

### Config 中的 Skill 配置

在 `~/.openclaw/openclaw.json` 中可以精细控制每个 skill:

```json
{
  "skills": {
    "allowBundled": ["gemini", "github"],
    "load": {
      "extraDirs": ["~/Projects/my-skills/skills"],
      "watch": true,
      "watchDebounceMs": 250
    },
    "entries": {
      "my-skill": {
        "enabled": true,
        "apiKey": { "source": "env", "provider": "default", "id": "MY_API_KEY" },
        "env": { "MY_API_KEY": "sk-xxx" }
      }
    }
  }
}
```

---

## ClawHub 技能市场

ClawHub 是 OpenClaw 的公共 Skill 注册表，2026.3 月已有 **5,400+ skills**。

### 安装使用

```bash
# 安装 ClawHub CLI
npm i -g clawhub

# 搜索 skills
clawhub search "finance"
clawhub search "stock"
clawhub search "news"

# 安装 skill
clawhub install <slug>

# 更新所有已安装的 skills
clawhub update --all

# 列出已安装
clawhub list

# 发布自己的 skill
clawhub publish ./my-skill --slug my-skill --name "My Skill" --version 1.0.0

# 同步本地 skills 到 registry
clawhub sync --all
```

### 安装位置

默认安装到 `./skills/` (当前工作目录) 或 workspace 配置的目录，OpenClaw 自动识别为 workspace skills。

---

## 优秀开源案例

### 金融/交易类 (与 Sentinel 最相关)

#### 1. Stock Analysis (巴菲特风格选股)

- **来源**: florinelchis (Medium 详细博文)
- **功能**: S&P 500 全扫描，10 条巴菲特公式 + Williams %R 技术指标
- **架构**: ~2000 行 Python，SEC EDGAR + Yahoo Finance + TA-Lib
- **亮点**: 通过 Telegram 直接发命令 `oversold` 扫描超卖股
- **博文**: https://florinelchis.medium.com/building-a-wall-street-grade-stock-screener-with-openclaw-ai-agents-and-free-apis-48cbeeadd9d5

```
stock-analysis/
├── analyze.py              # 单只股票巴菲特分析
├── technical_only.py       # 快速技术面超卖扫描
├── screening.py            # 组合技术面 + 基本面
├── price_data.py           # Yahoo Finance 数据获取 + 缓存
├── technical_indicators.py # Williams %R, EMA 计算 (TA-Lib)
├── sec_api.py              # SEC EDGAR API 客户端
├── formulas.py             # 10 条巴菲特公式实现
├── database.py             # SQLite 缓存层
├── sp500_tickers.py        # S&P 500 列表获取
├── SKILL.md                # OpenClaw skill 定义
└── data/
    ├── askten.db           # SEC 基本面数据缓存
    └── price_cache.db      # 价格数据缓存
```

#### 2. Stocks (56+ 金融工具)

- **来源**: openclaw/skills 官方
- **功能**: 股价、基本面、盈利、股息、期权、加密、外汇、大宗商品、新闻
- **架构**: yfinance-ai 封装，独立 venv 隔离依赖
- **亮点**: OS-agnostic 设计 + 单次交互模式 + TOOLS.md 注入模式
- **参考**: https://playbooks.com/skills/openclaw/skills/stocks

关键模式 — Venv 隔离:
```bash
# 独立 venv，不污染主项目
/home/openclaw/.openclaw/venv/stocks/bin/python3 - << 'PY'
import asyncio, sys
sys.path.insert(0, '.')
from yfinance_ai import Tools
t = Tools()
async def main():
    r = await t.get_key_ratios(ticker='UNH')
    print(r)
asyncio.run(main())
PY
```

#### 3. Trade Signal (交易信号生成)

- **功能**: SEC 10-K/10-Q 深度分析 + 分析师覆盖 + 期权隐含波动
- **亮点**: 完整 agent 交互流程，`search.sh` 自然语言查询
- **参考**: https://playbooks.com/skills/openclaw/skills/trade-signal

#### 4. Financial Market Analysis

- **来源**: openclaw/skills 官方
- **功能**: Yahoo Finance 数据 + 智能新闻聚合
- **安装**: `clawhub install financial-market-analysis`
- **参考**: https://lobehub.com/skills/openclaw-skills-financial-market-analysis

#### 5. News Aggregator (新闻聚合)

- **功能**: 8 大源聚合 (Hacker News / GitHub Trending / Product Hunt / 36Kr / 腾讯新闻 / 华尔街见闻 / V2EX)
- **适合**: 补充 Sentinel 的新闻采集能力

### 其他值得关注的 Skills

| Skill | 说明 | 下载量 |
|---|---|---|
| Polymarket Trading Bot | ClawHub CLI 搜索/安装/发布 skills | 1,289 |
| Stock Analysis | 组合分析 + 加密货币 + 定期报告 | 1,236 |
| Perplexity | AI 搜索 + 引用 | 1,038 |
| Heurist Mesh Crypto | Web3 / 加密分析 | 482 |
| News Aggregator | 8 源新闻聚合 | 411 |
| Deploy Agent | 全栈部署 Build→Test→GitHub→Cloudflare | 210 |
| Yahoo Finance CLI | 股价/盈利/金融数据 | 204 |
| PR + Commit Workflow | PR 规范化 | 204 |
| n8n Automation | n8n 工作流自动化 | 113 |

### 其他参考项目

| 项目 | 说明 |
|---|---|
| HKUDS/nanobot | "Ultra-Lightweight OpenClaw" ~4000 行 (vs 430k+) |
| qwibitai/nanoclaw | 轻量替代，容器运行，基于 Anthropic Agents SDK |
| grp06/openclaw-studio | Web Dashboard for OpenClaw |
| abhi1693/openclaw-mission-control | 多 Agent 编排面板 |
| cloudflare/moltworker | 在 Cloudflare Workers 上运行 OpenClaw |
| ComposioHQ/secure-openclaw | 24/7 AI 助手 (WhatsApp/Telegram/Signal) + 500 app 集成 |
| BytePioneer-AI/openclaw-china | 中国插件：飞书/钉钉/企微/QQ |

### Awesome Lists (精选集合)

| 合集 | 链接 |
|---|---|
| VoltAgent/awesome-openclaw-skills | 5,400+ skills 分类整理 |
| hesamsheikh/awesome-openclaw-usecases | 社区 Use Cases 收集 |
| LeoYeAI/openclaw-master-skills | 127+ 精选 Skills (周更) |
| sundial-org/awesome-openclaw-skills | 分类精选列表 |

---

## Skill 开发最佳实践

### 1. Description 撰写

用第三人称 + 明确的触发短语，让 Agent Router 精准匹配:

```yaml
# 好的写法
description: >
  This skill should be used when the user asks to "check stock prices",
  "analyze market sentiment", or "get trading signals".

# 不好的写法
description: Stock analysis tool.
```

### 2. 三级加载控制 Token 消耗

- **Frontmatter**: 保持精简（始终被加载到每次会话）
- **Body**: 放具体操作指令（仅触发时加载）
- **references/**: 放详细文档（按需加载，减少基础 token 消耗）

### 3. Python Skill 的 Venv 隔离

```bash
# 在 skill 目录下创建独立 venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# SKILL.md 中使用 venv 的 Python
cd /path/to/skill && .venv/bin/python3 script.py
```

### 4. 文件记忆优先

Session memory 在 compaction 时会丢失。重要状态写文件:
- `MEMORY.md` — 长期上下文
- `memory/YYYY-MM-DD.md` — 每日日志

### 5. 安全原则

- **自建优先**: 社区发现 ClawHub 上 341 个恶意 skill (12%)，自建比安装更安全
- **审查代码**: 安装第三方 skill 前务必阅读源码
- **沙箱隔离**: 不信任的 skill 用 Docker sandbox 运行
- **权限最小化**: 只声明必要的 `requires`

### 6. 路由规则设计

参考 Sentinel 的模式 — 明确区分"生成报告"和"追问"两种路由:

```markdown
## 使用场景

**生成报告** (仅当用户明确要求):
- "跑一下午盘分析" → `--mode midday`

**所有其他问题** (默认路由):
- 任何问题 → `--ask "用户原始问题"`
```

### 7. 模型选择

- **主 Agent**: 用强模型 (Opus/Pro) 做编排和复杂推理
- **子 Agent**: 用快模型 (Sonnet/Flash) 做具体执行
- 通过 `agents.defaults.model` 配置默认模型

---

## Sentinel Skill 优化建议

### SKILL.md Frontmatter 增强

```yaml
---
name: sentinel
description: >
  A股智能投顾哨兵 - AI驱动的市场分析、追问与趋势研判。
  This skill should be used when the user asks about A-share market analysis,
  stock/ETF trading signals, portfolio review, or Chinese stock market trends.
metadata:
  openclaw:
    emoji: '🛡️'
    requires:
      bins: ['python3']
      env: ['GEMINI_API_KEY']
    primaryEnv: GEMINI_API_KEY
user-invocable: true
---
```

### 增加 references/ 目录

```
ai_sentiney/
├── SKILL.md              # Level 1+2: 路由规则和基本指令
├── references/           # Level 3: 详细文档 (新增)
│   ├── portfolio.md      # 持仓配置说明
│   ├── strategies.md     # 策略详解 (trend/value)
│   └── api-reference.md  # CLI 参数完整参考
└── ...
```

### 利用 OpenClaw Cron 替代 GitHub Actions

```bash
# 查看 cron 功能
openclaw cron --help

# 设置定时任务（替代 GitHub Actions）
# 早报 08:00 CST
# 午盘 11:40 CST
# 收盘 15:10 CST
```

### 发布到 ClawHub (可选)

```bash
clawhub publish /Users/lan/Desktop/code/ai_sentiney \
  --slug sentinel \
  --name "A-Share Sentinel" \
  --version 1.0.0 \
  --tags latest
```

---

## 安全注意事项

### 当前安全审计结果 (4 CRITICAL)

1. **CRITICAL**: Telegram `groupPolicy="open"` + elevated tools → 任何群可触发高权限操作
2. **CRITICAL**: Runtime/filesystem 工具暴露在 Telegram 群中
3. **CRITICAL**: Telegram 无群组白名单
4. **CRITICAL**: Telegram 群命令无发送者白名单

### 修复建议

```bash
# 自动修复
openclaw doctor --repair

# 手动修复关键项
openclaw config set channels.telegram.groupPolicy allowlist
openclaw config set channels.telegram.groups.<GROUP_ID>.allowFrom '["your_telegram_id"]'

# 清理旧服务
launchctl bootout gui/$UID/com.clawdbot.gateway
launchctl bootout gui/$UID/com.clawdbot.feishu-bridge
launchctl bootout gui/$UID/bot.molt.gateway
```

### 通用安全建议

- 设置 `tools.profile="messaging"` 限制群组工具
- 启用 `agents.defaults.sandbox.mode="all"` 沙箱
- 设置 `tools.fs.workspaceOnly=true` 限制文件系统访问
- 使用 `pairing` 模式进行 Telegram DM 认证

---

## 学习资源

### 入门教程

| 资源 | 链接 |
|---|---|
| 中文 7 天精通教程 | https://github.com/mengjian-github/openclaw101 |
| freeCodeCamp 完整教程 | https://freecodecamp.org/news/openclaw-full-tutorial-for-beginners |
| DigitalOcean Skills 指南 | https://digitalocean.com/resources/articles/what-are-openclaw-skills |

### 深度技术文章

| 资源 | 链接 |
|---|---|
| SKILL.md 模式详解 | https://bibek-poudel.medium.com/the-skill-md-pattern |
| 设计模式 7 篇系列 | https://kenhuangus.substack.com (Design Patterns Part 1-7) |
| 架构深度解析 | LinkedIn - Elaheh Ahmadi |
| 金融行业分析 | https://institutionalinvestor.com/article/openclaw-ai-agent |
| 金融专业人士 7 点感悟 | LinkedIn - 7 Things a Financial Markets Professional Learned |

### 安全分析

| 资源 | 链接 |
|---|---|
| Akamai 安全分析 | https://akamai.com/blog/security/clawdbot-openclaw-practical-lessons |
| 1Password 安全分析 | https://1password.com/blog/from-magic-to-malware-how-openclaws-agent-skills-become-an-attack-surface |
| Snyk 安全分析 | https://snyk.io/articles/skill-md-shell-access |

### 官方文档

| 页面 | 链接 |
|---|---|
| Skills 系统 | https://docs.openclaw.ai/tools/skills |
| Skills 配置 | https://docs.openclaw.ai/tools/skills-config |
| ClawHub | https://docs.openclaw.ai/tools/clawhub |
| 架构 | https://docs.openclaw.ai/concepts/architecture |
| CLI 参考 | https://docs.openclaw.ai/cli |
| 安全 | https://docs.openclaw.ai/security |

### 中国生态

| 项目 | 说明 |
|---|---|
| BytePioneer-AI/openclaw-china | 飞书/钉钉/企微/QQ/微信 插件 |
| m1heng/clawdbot-feishu | 飞书直连插件 |
| AlexAnys/feishu-openclaw | WebSocket 桥接，无需 ngrok |
| 1186258278/OpenClawChineseTranslation | 完整中文翻译 |

### 社区

| 平台 | 链接 |
|---|---|
| Reddit | https://reddit.com/r/openclaw |
| Discord | https://discord.gg/clawd |
| GitHub Discussions | https://github.com/openclaw/openclaw/discussions |
