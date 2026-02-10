# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Project Sentinel** is a local A-share (Chinese stock market) intelligent investment advisor system. It acts as an intelligence and risk officer by:
- Collecting real-time A-share market data and news via AkShare
- Using Google Gemini AI for sentiment analysis and trading recommendations
- Pushing formatted reports to Feishu/Lark messaging
- Supporting interactive Q&A and trend analysis via CLI or OpenClaw chat

The system follows a "Newsroom Model": Python/AkShare (reporter) → Gemini (editor-in-chief) → Feishu (courier).
It also functions as an **OpenClaw Skill**, enabling conversational access through Feishu group chat.

## Common Commands

### Running the System

```bash
# Midday check (run at 11:40 AM CST)
python -m src.main --mode midday

# Close review (run at 3:10 PM CST)
python -m src.main --mode close

# Morning brief (run at 8:00 AM CST)
python -m src.main --mode morning

# Push results to Feishu (required for actual delivery)
python -m src.main --mode midday --publish

# Dry run (no API calls, no messages sent)
python -m src.main --mode midday --dry-run

# Replay mode (re-analyze last saved data)
python -m src.main --mode midday --replay

# JSON output (for programmatic consumption)
python -m src.main --mode midday --output json
```

### Q&A and Trend Analysis

```bash
# Ask a follow-up question about the latest analysis
python -m src.main --ask "黄金ETF今天怎么样"

# Ask about a specific date
python -m src.main --ask "半导体板块情况" --date 2026-02-07 --mode close

# Trend analysis (auto-detected by keywords like 趋势/一周/最近)
python -m src.main --ask "最近一周市场走势如何"
```

### Environment Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with GEMINI_API_KEY and FEISHU_WEBHOOK
```

### Testing Individual Modules

```bash
# Test data collector
python -m src.collector.data_fetcher

# Test database operations
python -m src.storage.database
```

## Architecture

### Module Structure

```
src/
├── collector/     # Data fetching (AkShare API calls)
├── processor/     # Indicator calculation (MA20 stitching)
├── analyst/       # Gemini AI client
├── reporter/      # Feishu webhook client
├── storage/       # SQLite persistence
├── utils/         # Config, logging
└── main.py        # Orchestration entry point
```

### Data Flow Pipeline

1. **Collector** (`DataCollector`) - Async parallel fetching:
   - Market breadth (rise/fall ratio)
   - Northbound funds flow
   - Major indices (Shanghai/Shenzhen/ChiNext)
   - Macro news + AI tech news
   - Per-stock: spot price, 60-day history, recent news

2. **Processor** (`DataProcessor`) - Indicator calculation:
   - **Real-time MA20 Stitching**: Combines 19 days of historical close prices with current real-time price to calculate intraday MA20 (since historical data doesn't include today)
   - Bias rate calculation: `(Price - MA20) / MA20`
   - Signal generation: SAFE/DANGER/WATCH based on price vs MA20 and northbound funds

3. **Analyst** (`GeminiClient`) - AI analysis:
   - Uses configurable prompts from `config.yaml`
   - Three analysis modes: `midday_focus`, `close_review`, `morning_brief`
   - Free-text Q&A via `ask_question()` for follow-up questions
   - Parses structured JSON responses from Gemini

4. **Reporter** (`FeishuClient`) - Message delivery:
   - Constructs interactive Feishu cards with market sentiment, indices info, and per-stock actions
   - Groups stocks by action type (SELL/WATCH/HOLD)
   - Color-coded headers based on market sentiment

### Key Algorithm: Real-time MA20 Stitching

The core innovation in `processor/data_processor.py:calculate_indicators()`:
- Historical data via AkShare doesn't include today's intraday price
- Solution: Take last 19 days of historical close + current real-time price = 20-period MA
- Formula: `MA20 = sum(past_19_closes + current_price) / 20`
- Enables accurate MA20-based signals during trading hours

### Async Patterns

The system uses `asyncio` with a `ThreadPoolExecutor` (16 workers) to parallelize blocking AkShare calls:
- `_run_blocking()` wrapper adds tenacity-based retry with exponential backoff
- Global market data and individual stock data fetch in parallel via `asyncio.gather()`
- Handles exceptions gracefully to prevent single-point failures

## Configuration

### config.yaml Structure

- `system`: Log level, retry count, timeout, timezone
- `ai`: Model name (default: `gemini-3-pro-preview`)
- `api_keys`: Gemini API key and Feishu webhook (use `${VAR}` syntax for env vars)
- `portfolio`: List of stock/ETF positions with code, name, cost basis, strategy (trend/value)
- `risk_management`: Stop loss %, MA window, north money threshold
- `prompts`: System prompts for midday, close, morning, Q&A, and trend analysis modes

### CLI Arguments

| Argument | Description |
|----------|-------------|
| `--mode {midday,close,morning}` | Analysis mode (default: midday) |
| `--publish` | Push results to Feishu (default: no push) |
| `--dry-run` | Skip API calls and notifications |
| `--replay` | Re-analyze last saved data |
| `--output {text,json}` | Output format (default: text) |
| `--ask "question"` | Q&A mode: ask follow-up questions |
| `--date YYYY-MM-DD` | Target date for analysis or Q&A |
| `--webui` | Start WebUI server |

### Environment Variables

Required in `.env`:
- `GEMINI_API_KEY`: Google Gemini API key (get from https://aistudio.google.com/app/apikey)
- `FEISHU_WEBHOOK`: Feishu bot webhook URL

## Data Persistence

- **SQLite database** (`data/sentinel.db`) stores full context for replay mode
- Table `daily_records`: date, timestamp, mode, market breadth, AI summary, raw JSON input, AI result
- Q&A mode queries DB by date/mode for cached raw_data and ai_result
- Trend analysis loads multiple days via `get_records_range()`
- Replay mode loads from DB first, falls back to `data/latest_context.json`

## GitHub Actions Automation

The workflow (`.github/workflows/daily_sentinel.yml`) runs on schedule:
- Morning: 00:00 UTC (08:00 CST) Monday-Friday
- Midday: 03:40 UTC (11:40 CST) Monday-Friday
- Close: 07:10 UTC (15:10 CST) Monday-Friday
- All commands include `--publish` to push to Feishu
- Detects mode based on current UTC hour
- Commits database changes back to repo after successful runs

## OpenClaw Skill Integration

This project is registered as an **OpenClaw Skill** (see `SKILL.md`), enabling conversational access via Feishu group chat through the OpenClaw gateway.

### How It Works

```
User @bot in Feishu → ngrok → OpenClaw gateway (port 3001)
  → matches "sentinel" skill → executes CLI command
  → stdout returned as chat reply
```

### Setup

1. Symlink project as skill: `ln -s /path/to/ai_sentiney ~/.openclaw/skills/sentinel`
2. Ensure `SKILL.md` exists at project root with `openclaw` metadata
3. Start gateway: `openclaw gateway`
4. ngrok tunnel: `ngrok http 3001` (URL must match Feishu app webhook config)

### Supported Chat Triggers

- "跑一下午盘分析" → `python -m src.main --mode midday`
- "黄金ETF今天怎么样" → `python -m src.main --ask "黄金ETF今天怎么样"`
- "最近一周市场走势" → `python -m src.main --ask "最近一周市场走势"` (auto-detects trend)

## Code Conventions

- Uses `tenacity` for retry logic on network calls
- Singleton pattern for `ConfigLoader`
- Color-coded Feishu cards: red (danger/sell), yellow (watch), green (hold)
- A-share convention: red = up, green = down
- All timestamps in `Asia/Shanghai` timezone
