# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Project Sentinel** is a local A-share (Chinese stock market) intelligent investment advisor system. It acts as an intelligence and risk officer by:
- Collecting real-time A-share market data and news via AkShare
- Using Google Gemini AI for sentiment analysis and trading recommendations
- Pushing formatted reports to Feishu/Lark messaging

The system follows a "Newsroom Model": Python/AkShare (reporter) → Gemini (editor-in-chief) → Feishu (courier).

## Common Commands

### Running the System

```bash
# Midday check (run at 11:40 AM CST)
python -m src.main --mode midday

# Close review (run at 3:10 PM CST)
python -m src.main --mode close

# Dry run (no API calls, no messages sent)
python -m src.main --mode midday --dry-run

# Replay mode (re-analyze last saved data)
python -m src.main --mode midday --replay
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
   - Two modes: `midday_focus` (intraday trading) and `close_review` (end-of-day summary)
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
- `prompts`: System prompts for midday and close analysis modes

### Environment Variables

Required in `.env`:
- `GEMINI_API_KEY`: Google Gemini API key (get from https://aistudio.google.com/app/apikey)
- `FEISHU_WEBHOOK`: Feishu bot webhook URL

## Data Persistence

- **SQLite database** (`data/sentinel.db`) stores full context for replay mode
- Table `daily_records`: date, timestamp, mode, market breadth, AI summary, raw JSON input
- Replay mode loads from DB first, falls back to `data/latest_context.json`

## GitHub Actions Automation

The workflow (`.github/workflows/daily_sentinel.yml`) runs on schedule:
- Midday: 03:40 UTC (11:40 CST) Monday-Friday
- Close: 07:10 UTC (15:10 CST) Monday-Friday
- Detects mode based on current UTC hour
- Commits database changes back to repo after successful runs

## Code Conventions

- Uses `tenacity` for retry logic on network calls
- Singleton pattern for `ConfigLoader`
- Color-coded Feishu cards: red (danger/sell), yellow (watch), green (hold)
- A-share convention: red = up, green = down
- All timestamps in `Asia/Shanghai` timezone
