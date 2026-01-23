# Gemini Context for AI Sentinel

This file provides context and instructions for AI agents (specifically Gemini) working on the **Project Sentinel** codebase.

## 1. Project Overview

**Project Sentinel** is a local, AI-powered investment advisor for the Chinese A-share market.
It serves as an "Intelligence & Risk Officer" by automating the data collection, analysis, and reporting pipeline:
1.  **Collects** real-time market data (AkShare) and news.
2.  **Analyzes** data using Google Gemini Pro to generate trading insights.
3.  **Reports** actionable advice (Safe/Danger/Watch) via Feishu (Lark) webhooks.

**Key Philosophy:**
- **Newsroom Model:** Reporter (Python) -> Editor-in-Chief (Gemini) -> Courier (Feishu).
- **Automation:** Runs twice daily via GitHub Actions or Cron (Midday & Close).

## 2. Technical Stack

- **Language:** Python 3.9+
- **Data Source:** `akshare` (Async parallel fetching)
- **AI Engine:** `google-generativeai` (Gemini Pro)
- **Notification:** Feishu/Lark Webhook (Interactive Cards)
- **Persistence:** SQLite (`data/sentinel.db`)
- **Key Libraries:** `pandas`, `tenacity`, `colorlog`, `pytest`

## 3. Operational Commands

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Requires GEMINI_API_KEY and FEISHU_WEBHOOK
```

### Execution Modes
The system has two primary run modes corresponding to market hours:

**1. Midday Check (11:40 CST)**
- Focus: Intraday risk control, afternoon session strategy.
```bash
python -m src.main --mode midday
```

**2. Close Review (15:10 CST)**
- Focus: Daily summary, support/resistance levels for next day.
```bash
python -m src.main --mode close
```

### Debugging & Development
- **Dry Run:** No API calls, no messages sent. Safe for logic testing.
  ```bash
  python -m src.main --mode midday --dry-run
  ```
- **Replay Mode:** Re-analyzes the last saved data context without re-fetching. Ideal for prompt tuning.
  ```bash
  python -m src.main --mode midday --replay
  ```

### Testing
```bash
pytest
```

## 4. Architecture & Data Flow

### Directory Structure
- `src/collector`: Fetches data from AkShare (Prices, Northbound funds, News).
- `src/processor`: Calculates indicators (MA20, Bias). **Key Algo: Real-time MA20 Stitching**.
- `src/analyst`: Interfaces with Gemini API using prompts from `config.yaml`.
- `src/reporter`: Formats and sends Feishu cards.
- `src/storage`: Manages SQLite database and context saving.

### The Pipeline
1.  **Collector**: Parallel async fetch of market breadth, indices, and portfolio data.
2.  **Processor**: Stitches historical data (past 19 days) with real-time price to compute a valid intraday MA20.
3.  **Analyst**: Sends structured data to Gemini. Gemini returns JSON analysis.
4.  **Reporter**: Renders the analysis into a color-coded Feishu card (Red=Up/Bullish, Green=Down/Bearish).

## 5. Development Conventions

- **Timezone**: All operations assume **Asia/Shanghai**.
- **Market Colors**: Follows A-share convention: **Red is Up**, **Green is Down**.
- **Configuration**: Managed in `config.yaml`. Do not hardcode logic that belongs in config.
- **Error Handling**: Use `tenacity` for network retries.
- **Secrets**: Never commit `.env` or API keys.

## 6. CI/CD (GitHub Actions)

- **Workflow**: `.github/workflows/daily_sentinel.yml`
- **Schedule**:
  - Midday: `40 3 * * 1-5` (03:40 UTC = 11:40 CST)
  - Close: `10 7 * * 1-5` (07:10 UTC = 15:10 CST)
- **Note**: The workflow automatically commits the updated SQLite database back to the repo to maintain context between runs.
