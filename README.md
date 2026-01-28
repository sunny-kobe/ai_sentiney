# 🦅 Project Sentinel: A 股智能投顾系统

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Pro-orange)
![Resilience](https://img.shields.io/badge/Resilience-Dual%20Source-green)

**Project Sentinel** 是一个运行在本地的“全栈式 AI 投顾助理”。它不是自动交易软件，而是你的**情报官 (Intelligence Officer)** 和 **风控官 (Risk Officer)**。

它利用 Python 采集 A 股实时行情与新闻，结合 Google Gemini 的长文本分析能力，为您提供理性、客观的午间风控预警和收盘复盘报告，并通过飞书 (Feishu/Lark) 第一时间推送到您的手机。

---

## 🚀 核心痛点解决

1.  **拒绝数据碎片化**: 自动聚合行情软件、财联社电报、个股公告，无需手动刷新。
2.  **克服决策情绪化**: 依靠代码逻辑（如动态 MA20 生命线、北向资金流向）强制进行冷酷的买卖判断。
3.  **消除信息不对称**: 利用 Gemini 识别新闻背后的真伪，区分“杀估值”与“错杀”。
4.  **数据源高可用**: 采用 **双源热备 (Dual Source Strategy)**，确保在单一数据源挂掉时仍能正常工作。

## ✨ 功能特性

- **🛡️ 韧性数据采集 (Resilient Collection)**:
  - **三源热备**: 采用 **Tencent (腾讯)** 作为首选源，**Efinance** 和 **AkShare** 作为二级备用。
  - **智能路由**: 当首选源超时或失败时，自动无缝切换至备用源，确保数据高可用。
  - **超时熔断**: 为所有网络请求内置 30秒 熔断机制，防止任务挂起。
  - **全维覆盖**: 实时行情、北向资金、财联社电报 (>500字长文自动摘要)。
- **🧮 动态指标计算**:
  - 独创 **实时均线拼接 (Real-time MA Stitching)** 算法，盘中即可计算当日 MA20，解决数据延迟问题。
  - 自动计算乖离率 (Bias)，作为趋势判断辅助。
- **🧠 Gemini 智能分析**:
  - **午间哨兵 (Midday Check)**: 11:40 运行，判断下午开盘策略（DANGER/WATCH/HOLD）。
  - **收盘复盘 (Close Review)**: 15:10 运行，总结全天行情，利用 AI 生成明日支撑/压力位及操作建议。
- **💻 轻量级 WebUI**:
  - 内置零依赖 Dashboard (`http://localhost:8000`)。
  - 支持查看监控列表、手动触发 AI 分析、健康状态检查。
- **📱 飞书实时推送**:
  - 图文并茂的卡片消息，支持红涨绿跌展示。

## 🛠️ 技术栈

- **语言**: Python 3.9+
- **数据源**: Tencent (Primary), Efinance (Secondary), AkShare (Fallback)
- **AI 引擎**: Google Gemini Pro (`google-generativeai`)
- **Web 服务**: Python `http.server` (Zero dependency)
- **消息推送**: Feishu Webhook

## 🏁 快速开始

### 1. 环境准备

确保您的本地环境已安装 Python 3.9 或更高版本。

### 2. 克隆项目

```bash
git clone https://github.com/yourusername/ai_sentiney.git
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

### 5. 配置持仓 (Configuration)

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

如果您处于受限网络环境（如无法连接 AkShare/Efinance），可以在 `config.yaml` 中配置全局代理：

```yaml
system:
  # ... other settings
  proxy: "http://127.0.0.1:7890"
```

系统启动时会自动将此代理注入到环境变量，使所有数据采集和 AI 请求都通过代理转发。

## 🏃‍♂️ 运行指南

本项目支持 **CLI 命令行** 和 **WebUI** 两种运行方式。

### 方式一：CLI 命令行 (适合 Crontab 自动调度)

#### 1. 午间风控 (Midday Check)

建议在 **11:40** 左右运行。

```bash
python3 src/main.py --mode midday
```

#### 2. 收盘复盘 (Close Review)

建议在 **15:10** 左右运行。

```bash
python3 src/main.py --mode close
```

#### 3. 试运行 (Dry Run)

不消耗 API 额度，不发消息，仅跑通逻辑。

```bash
python3 src/main.py --mode midday --dry-run
```

### 方式二：WebUI 管理界面

启动 Web 服务：

```bash
python3 -m src.main --webui
```

访问 `http://localhost:8000`：

- **Dashboard**: 监控当前配置的持仓。
- **Trigger**: 手动点击 "Trigger Analysis" 按钮立即运行分析（默认 Dry Run 模式，避免误触）。
- **Health Check**: 访问 `/api/status` 查看服务存活状态。

## ⏱️ 自动化部署 (Crontab)

```bash
crontab -e
```

添加以下内容 (假设项目路径为 `/root/ai_sentiney`)：

```bash
# 1. 午间哨兵 (11:40)
40 11 * * 1-5 cd /root/ai_sentiney && /root/ai_sentiney/.venv/bin/python3 src/main.py --mode midday >> logs/cron.log 2>&1

# 2. 收盘复盘 (15:10)
10 15 * * 1-5 cd /root/ai_sentiney && /root/ai_sentiney/.venv/bin/python3 src/main.py --mode close >> logs/cron.log 2>&1
```

## 🧪 开发者指南 (Testing)

项目包含全链路验证脚本，用于测试数据源连接和系统稳定性。

```bash
# 运行全链路测试 (同时验证 WebUI 和 数据源 fallback)
PYTHONPATH=. .venv/bin/python tests/verify_full_flow.py
```

## ⚠️ 免责声明 (Disclaimer)

1.  **本项目仅供学习与技术研究使用**。
2.  也就是作者写来自己玩的，**不构成任何投资建议**。
3.  股市有风险，入市需谨慎。根据本系统生成的报告进行交易产生的盈亏，**作者概不负责**。
4.  请遵守当地法律法规。

## 📄 License

MIT License

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Pro-orange)

**Project Sentinel** 是一个运行在本地的“全栈式 AI 投顾助理”。它不是自动交易软件，而是你的**情报官 (Intelligence Officer)** 和 **风控官 (Risk Officer)**。

它利用 Python 采集 A 股实时行情与新闻，结合 Google Gemini 的长文本分析能力，为您提供理性、客观的午间风控预警和收盘复盘报告，并通过飞书 (Feishu/Lark) 第一时间推送到您的手机。

---

## 🚀 核心痛点解决

1.  **拒绝数据碎片化**: 自动聚合行情软件、财联社电报、个股公告，无需手动刷新。
2.  **克服决策情绪化**: 依靠代码逻辑（如动态 MA20 生命线、北向资金流向）强制进行冷酷的买卖判断。
3.  **消除信息不对称**: 利用 Gemini 识别新闻背后的真伪，区分“杀估值”与“错杀”。

## ✨ 功能特性

- **🕷️ 全维数据采集**:
  - 集成 `AkShare` 获取 A 股实时行情（个股 Spot / 分钟线）。
  - 实时监控**北向资金**净流入，捕捉主力动向。
  - 抓取**财联社电报**与个股新闻，覆盖宏观与微观面。
  - 计算全市场**涨跌家数比**，量化市场情绪。
- **🧮 动态指标计算**:
  - 独创 **实时均线拼接 (Real-time MA Stitching)** 算法，盘中即可计算当日 MA20，解决数据延迟问题。
  - 自动计算乖离率 (Bias)，作为趋势判断辅助。
- **🧠 Gemini 智能分析**:
  - **午间哨兵 (Midday Check)**: 11:40 运行，判断下午开盘策略（DANGER/WATCH/HOLD）。
  - **收盘复盘 (Close Review)**: 15:10 运行，总结全天行情，利用 AI 生成明日支撑/压力位及操作建议。
- **📱 飞书实时推送**:
  - 图文并茂的卡片消息，关键信息一目了然。
  - 支持红涨绿跌（符合 A 股习惯）的富文本展示。

## 🛠️ 技术栈

- **语言**: Python 3.9+
- **数据源**: AkShare
- **AI 引擎**: Google Gemini Pro (`google-generativeai`)
- **逻辑处理**: Pandas
- **消息推送**: Feishu Webhook

## 🏁 快速开始

### 1. 环境准备

确保您的本地环境已安装 Python 3.9 或更高版本。

### 2. 克隆项目

```bash
git clone https://github.com/yourusername/ai_sentiney.git
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

### 5. 配置持仓 (Configuration)

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

## 🏃‍♂️ 运行指南

本项目包含两种主要运行模式：

### 1. 午间风控 (Midday Check)

建议在 **11:40** 左右运行，用于辅助下午开盘决策。

```bash
python3 src/main.py --mode midday
```

### 2. 收盘复盘 (Close Review)

建议在 **15:10** 左右运行，用于全天总结和明日计划。

```bash
python3 src/main.py --mode close
```

### 其他参数

- `--dry-run`: 试运行模式。不调用 Gemini API (节省额度)，不发送飞书消息，仅打印日志。
  ```bash
  python3 src/main.py --mode midday --dry-run
  ```
- `--replay`: (仅 Midday 模式) 重播模式。使用上一次保存的数据上下文重新进行 AI 分析，用于调试 Prompt。
  ```bash
  python3 src/main.py --mode midday --replay
  ```

### 3. WebUI 管理界面 (Lightweight)

启动轻量级 Web 界面，用于管理持仓和手动触发分析：

```bash
python3 src/main.py --webui
```

启动后访问: `http://localhost:8000`

- **Dashboard**: 查看当前监控的股票代码。
- **Trigger Analysis**: 手动运行一次全流程分析 (Midday 模式)。
- **Config**: 即时修改 `stock_list` (内存生效，需手动同步到 yaml)。

## ⏱️ 自动化部署 (Crontab)

为了实现全自动运行，建议设置定时任务。

**MacOS / Linux (Crontab):**

```bash
crontab -e
```

添加以下内容 (假设项目路径为 `/root/ai_sentiney`)：

```bash
# 交易日周一到周五

# 1. 午间哨兵 (11:40)
40 11 * * 1-5 cd /root/ai_sentiney && /root/ai_sentiney/.venv/bin/python3 src/main.py --mode midday >> logs/cron.log 2>&1

# 2. 收盘复盘 (15:10)
10 15 * * 1-5 cd /root/ai_sentiney && /root/ai_sentiney/.venv/bin/python3 src/main.py --mode close >> logs/cron.log 2>&1
```

## ⚠️ 免责声明 (Disclaimer)

1.  **本项目仅供学习与技术研究使用**。
2.  也就是作者写来自己玩的，**不构成任何投资建议**。
3.  股市有风险，入市需谨慎。根据本系统生成的报告进行交易产生的盈亏，**作者概不负责**。
4.  请遵守当地法律法规。

## 📄 License

MIT License
