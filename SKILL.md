---
name: sentinel
description: A股智能投顾哨兵 - AI驱动的市场分析、追问与趋势研判
metadata: { 'openclaw': { 'emoji': '🛡️', 'requires': { 'bins': ['python3'] } } }
---

# Project Sentinel

A股智能投顾系统，通过 AkShare 采集实时行情，Gemini AI 分析，输出交易建议。

## 使用方式

**重要**: 必须先 `cd` 到项目目录，并激活虚拟环境。

### 生成分析报告

```bash
# 午盘分析（默认），输出到终端
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode midday

# 收盘复盘
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode close

# 早报
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode morning

# 生成并推送到飞书
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode midday --publish

# JSON 格式输出（供程序消费）
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode midday --output json
```

### 追问分析

```bash
# 追问最近一次分析
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --ask "黄金ETF今天怎么样"

# 追问指定日期
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --ask "半导体板块情况如何" --date 2026-02-07

# 追问收盘分析
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --ask "明天怎么操作" --mode close
```

### 趋势分析

```bash
# 一周趋势（自动检测趋势关键词）
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --ask "最近一周市场趋势如何"

# 一个月趋势
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --ask "这个月持仓表现怎么样"
```

## 使用场景

**⚠️ 核心路由规则（必须严格遵守）**:
- 只有用户**明确要求"跑分析/生成报告/推送飞书"**时，才执行 `--mode` 命令
- **所有其他问题**（包括追问、评价、询问准确率、闲聊等）一律使用 `--ask "用户的原始问题"` 转发给 Sentinel CLI
- **禁止**自行编造回答来代替 CLI 输出。必须执行命令并将 stdout 原样返回给用户
- 当不确定该用哪个命令时，默认使用 `--ask`

### 生成报告（仅当用户明确要求生成/跑/推送时）

当用户说：
- "跑一下午盘分析"
- "生成收盘复盘"
- "早报分析一下"
- "推送到飞书"

执行：`cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode midday`

### 推送飞书

当用户说：
- "把分析推到飞书"
- "发一下午盘报告"

执行：`cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --mode midday --publish`

### 所有其他问题（追问、准确率、评价、闲聊等）

当用户说任何非"生成报告"的话，包括但不限于：
- 追问标的："黄金ETF今天怎么样"、"紫金矿业能买吗"
- 准确率相关："准不准"、"准确率"、"命中率"、"靠谱吗"、"可信吗"、"胜率"
- 趋势相关："最近一周市场走势"、"这个月持仓趋势"
- 其他任何问题

**一律**执行：`cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate && python -m src.main --ask "用户的原始问题"`

将 stdout 输出原样返回给用户，**不要自行加工或编造内容**。

## 数据缓存

- SQLite 数据库: `data/sentinel.db`
- JSON 快照: `data/latest_context.json`
- 支持历史回放: `--replay` 参数
