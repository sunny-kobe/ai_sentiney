# Project Sentinel: A 股智能投顾系统

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Pro-orange)
![Resilience](https://img.shields.io/badge/Resilience-Dual%20Source-green)

**Project Sentinel** 是一个运行在本地的"全栈式 AI 投顾助理"。它不是自动交易软件，而是你的**情报官 (Intelligence Officer)** 和 **风控官 (Risk Officer)**。

它利用 Python 采集 A 股实时行情与新闻，结合 Google Gemini 的长文本分析能力，为您提供理性、客观的午间风控预警和收盘复盘报告，并通过飞书 (Feishu/Lark) 第一时间推送到您的手机。

同时，它也是一个 **OpenClaw Skill**，支持通过飞书群聊进行自然语言交互式追问和趋势分析。

---

## 核心痛点解决

1.  **拒绝数据碎片化**: 自动聚合行情软件、财联社电报、个股公告，无需手动刷新。
2.  **克服决策情绪化**: 依靠代码逻辑（如动态 MA20 生命线、量价分析）强制进行冷酷的买卖判断。
3.  **消除信息不对称**: 利用 Gemini 识别新闻背后的真伪，区分"杀估值"与"错杀"。
4.  **数据源高可用**: 采用 **双源热备 (Dual Source Strategy)**，确保在单一数据源挂掉时仍能正常工作。

## 功能特性

- **韧性数据采集 (Resilient Collection)**:
  - **三源热备**: 采用 **Tencent (腾讯)** 作为首选源，**Efinance** 和 **AkShare** 作为二级备用。
  - **智能路由**: 当首选源超时或失败时，自动无缝切换至备用源，确保数据高可用。
  - **超时熔断**: 为所有网络请求内置 30秒 熔断机制，防止任务挂起。
  - **全维覆盖**: 实时行情、北向资金、财联社电报 (>500字长文自动摘要)。
- **动态指标计算**:
  - 独创 **实时均线拼接 (Real-time MA Stitching)** 算法，盘中即可计算当日 MA20，解决数据延迟问题。
  - 自动计算乖离率 (Bias)，作为趋势判断辅助。
- **Gemini 智能分析**:
  - **盘前战备 (Morning Brief)**: 08:00 运行，扫描隔夜外盘（美股/大宗/美债），推演对 A 股持仓的影响，给出开盘策略。
  - **午间哨兵 (Midday Check)**: 11:40 运行，判断下午开盘策略（DANGER/WATCH/HOLD）。
  - **收盘复盘 (Close Review)**: 15:10 运行，总结全天行情，利用 AI 生成明日支撑/压力位及操作建议。
  - **智能追问 (Q&A)**: 基于缓存数据回答用户关于个股、板块的追问。
  - **趋势分析 (Trend)**: 自动检测趋势关键词，加载多日历史数据进行中短期趋势研判。
- **全球市场联动**:
  - 自动采集美股三大指数（S&P500/NASDAQ/道琼斯）、恒生指数、美元指数。
  - 追踪大宗商品期货（黄金/白银/铜/原油）与美债收益率（2Y/10Y/利差）。
  - 智能映射：外盘变动 → A 股持仓影响（如黄金涨 → 利好 159934/601899）。
- **飞书实时推送**:
  - 图文并茂的卡片消息，支持红涨绿跌展示。
  - 推送由 `--publish` 显式控制，默认仅输出到终端。
- **OpenClaw Skill 集成**:
  - 注册为 OpenClaw Skill 后，可通过飞书群聊 @bot 进行自然语言交互。
  - 支持聊天式追问："黄金ETF今天怎么样"、"最近一周市场走势"。
- **轻量级 WebUI**:
  - 内置零依赖 Dashboard (`http://localhost:8000`)。
  - 支持查看监控列表、手动触发 AI 分析、健康状态检查。

## 技术栈

- **语言**: Python 3.9+
- **数据源**: Tencent (Primary), Efinance (Secondary), AkShare (Fallback)
- **AI 引擎**: Google Gemini Pro (`google-generativeai`)
- **消息推送**: Feishu Webhook
- **聊天集成**: [OpenClaw](https://github.com/nicepkg/openclaw) (可选)
- **Web 服务**: Python `http.server` (Zero dependency)
- **持久化**: SQLite

## 快速开始

### 1. 环境准备

确保您的本地环境已安装 Python 3.9 或更高版本。

### 2. 克隆项目

```bash
git clone https://github.com/sunny-kobe/ai_sentiney.git
cd ai_sentiney
```

### 3. 安装依赖

建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 4. 配置环境

复制配置模板并填入您的密钥：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```ini
# Gemini API Key (申请地址: https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# 飞书机器人 Webhook (飞书群 -> 设置 -> 群机器人 -> 自定义机器人)
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_webhook_id
```

### 5. 配置持仓

编辑 `config.yaml` 文件，在 `portfolio` 列表中添加您关注的股票或 ETF。

```yaml
portfolio:
  - code: "600519"
    name: "贵州茅台"
    cost: 1700.0
    strategy: "value" # 策略标签: value(价值) / trend(趋势)

  - code: "300750"
    name: "宁德时代"
    cost: 180.0
    strategy: "trend"
```

### 6. 网络代理 (Optional)

如果您处于受限网络环境，可以在 `config.yaml` 中配置全局代理：

```yaml
system:
  proxy: "http://127.0.0.1:7890"
```

## 运行指南

### 定时分析模式

```bash
# 盘前战备 (建议 08:00)
python -m src.main --mode morning

# 午间风控 (建议 11:40)
python -m src.main --mode midday

# 收盘复盘 (建议 15:10)
python -m src.main --mode close
```

### 推送到飞书

默认情况下，分析结果仅输出到终端。加 `--publish` 推送飞书卡片消息：

```bash
python -m src.main --mode midday --publish
```

### 智能追问 (Q&A)

基于最近一次分析的缓存数据，向 AI 提问：

```bash
# 追问最近一次分析
python -m src.main --ask "黄金ETF今天怎么样"

# 追问指定日期的收盘分析
python -m src.main --ask "半导体板块情况如何" --date 2026-02-07 --mode close
```

### 趋势分析

包含"趋势/走势/一周/最近"等关键词时，自动加载多日历史数据进行趋势研判：

```bash
# 一周趋势
python -m src.main --ask "最近一周市场走势如何"

# 一个月趋势
python -m src.main --ask "这个月持仓表现怎么样"
```

### 其他参数

| 参数 | 说明 |
|------|------|
| `--mode {midday,close,morning}` | 分析模式 (默认: midday) |
| `--publish` | 推送到飞书 (默认不推) |
| `--dry-run` | 试运行，不调 API 不发消息 |
| `--replay` | 使用上次缓存数据重新分析 |
| `--output {text,json}` | 输出格式 (默认: text) |
| `--ask "问题"` | 追问模式 |
| `--date YYYY-MM-DD` | 指定日期 |
| `--webui` | 启动 WebUI |

### WebUI 管理界面

```bash
python -m src.main --webui
```

访问 `http://localhost:8000`：Dashboard、手动触发分析、健康检查。

## OpenClaw Skill 集成

本项目可作为 [OpenClaw](https://github.com/nicepkg/openclaw) 的 Skill 插件运行，实现通过飞书群聊自然语言交互。

### 接入方式

1. 安装 OpenClaw: `npm install -g openclaw@latest`
2. 将项目注册为 Skill:
   ```bash
   ln -s /path/to/ai_sentiney ~/.openclaw/skills/sentinel
   ```
3. 启动 gateway: `openclaw gateway`
4. 在飞书群 @bot 发送消息即可触发

### 支持的聊天指令

| 消息示例 | 触发行为 |
|---------|---------|
| "跑一下午盘分析" | 执行午盘分析并返回结果 |
| "黄金ETF今天怎么样" | 基于缓存数据追问 AI |
| "最近一周市场走势" | 多日趋势分析 |
| "把分析推到飞书" | 执行分析并推送飞书卡片 |

## 自动化部署

### GitHub Actions (推荐)

项目自带 GitHub Actions 工作流 (`.github/workflows/daily_sentinel.yml`)，交易日自动运行：

- Morning: 08:00 CST (Mon-Fri)
- Midday: 11:40 CST (Mon-Fri)
- Close: 15:10 CST (Mon-Fri)

需在 GitHub Repo Settings → Secrets 中配置 `GEMINI_API_KEY` 和 `FEISHU_WEBHOOK`。

### Crontab (本地部署)

```bash
crontab -e
```

```bash
# 交易日周一到周五 (假设项目路径为 /root/ai_sentiney)
30 8  * * 1-5 cd /root/ai_sentiney && .venv/bin/python -m src.main --mode morning --publish >> logs/cron.log 2>&1
40 11 * * 1-5 cd /root/ai_sentiney && .venv/bin/python -m src.main --mode midday  --publish >> logs/cron.log 2>&1
10 15 * * 1-5 cd /root/ai_sentiney && .venv/bin/python -m src.main --mode close   --publish >> logs/cron.log 2>&1
```

## 开发者指南

```bash
# 运行全链路测试
PYTHONPATH=. .venv/bin/python tests/verify_full_flow.py
```

## 免责声明 (Disclaimer)

1.  **本项目仅供学习与技术研究使用**。
2.  也就是作者写来自己玩的，**不构成任何投资建议**。
3.  股市有风险，入市需谨慎。根据本系统生成的报告进行交易产生的盈亏，**作者概不负责**。
4.  请遵守当地法律法规。

## License

MIT License
