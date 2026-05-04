# AGENTS.md — Project Sentinel

> This file provides guidance to Codex and other AI coding agents working in this repository.

## Project Overview

**Project Sentinel** is a local A-share intelligent investment advisor system.

- **Language**: Python 3.13
- **Framework**: asyncio + Pydantic
- **Data Source**: AkShare (market data), custom scrapers (news/GitHub)
- **AI**: Google Gemini (primary), MiMo v2 Pro (OpenAI-compat)
- **Storage**: SQLite (data/sentinel.db)
- **Output**: Feishu/Lark, Telegram

## Quick Start

```bash
cd /Users/lan/Desktop/code/ai_sentiney
source .venv/bin/activate
python -m pytest tests/ -q  # Run tests first
```

## Architecture

```
src/
├── alerts/        # Market anomaly detection (price/volume spikes)
├── analyst/       # AI clients (Gemini, OpenAI-compat, hybrid)
├── backtest/      # Backtesting engine
├── collector/     # Data fetching (AkShare, efinance, Tencent)
├── lab/           # Strategy lab (experimentation)
├── processor/     # Technical indicators (MA, MACD, RSI, etc.)
├── radar/         # Intelligence gathering (news, policy, GitHub)
├── report_gen/    # Automated report generation
├── reporter/      # Message delivery (Feishu, Telegram)
├── service/       # Business logic orchestration
├── storage/       # SQLite database
├── utils/         # Shared utilities
├── validation/    # Signal validation
└── web/           # Web UI
```

## Commands

```bash
# Analysis modes
python -m src.main --mode midday          # 11:40 CST
python -m src.main --mode close           # 15:10 CST
python -m src.main --mode morning         # 08:10 CST
python -m src.main --mode preclose        # 15:05 CST

# Special commands
python -m src.main alert                  # Market anomaly scan
python -m src.main radar                  # Intelligence scan
python -m src.main report                 # Auto report generation

# Testing
python -m pytest tests/ -q                # Quick test
python -m pytest tests/ --cov=src         # With coverage
python -m pytest tests/test_xxx.py -q     # Specific test
```

## Code Standards

### DO
- ✅ Type hints on all public functions
- ✅ Google-style docstrings
- ✅ `except Exception as e:` with logging
- ✅ `timeout` on all HTTP requests
- ✅ `tenacity` for retry logic
- ✅ Tests for new features and bug fixes

### DON'T
- ❌ Bare `except:` clauses
- ❌ Hardcoded credentials
- ❌ HTTP requests without timeout
- ❌ Magic numbers (use config or constants)
- ❌ Skipping tests

## Testing Rules

1. **Run tests before any change**: `python -m pytest tests/ -q`
2. **All 291 tests must pass** before committing
3. **Mock external dependencies**: API calls, network, filesystem
4. **Test structure**: Arrange → Act → Assert
5. **Coverage**: New code needs 80%+

## Configuration

- `config.yaml` — Main config (no secrets)
- `.env` — Secrets (API keys, webhooks)
- `pyproject.toml` — pytest + coverage config
- `requirements.txt` — Dependencies (with version constraints)
- `requirements-lock.txt` — Locked versions

## Key Algorithms

### MA20 Stitching
```python
# Combines 19 days history + current price
MA20 = sum(past_19_closes + current_price) / 20
```

### Circuit Breaker
```
3 failures → circuit OPEN → 30s cooldown → half-open → test → close
```

### Signal Generation
```
bias_pct > 4.5%  → DANGER (sell signal)
bias_pct < -4.5% → WATCH (potential buy)
northbound < -3B → DANGER (capital outflow)
```

## Common Pitfalls

1. **AkShare column names vary**: Check for both '收盘'/'Close'/'close'
2. **Timezone**: All timestamps are Asia/Shanghai
3. **A-share convention**: Red = up, Green = down (opposite of Western)
4. **Trading calendar**: Use `chinese_calendar.is_workday()` for holidays
5. **Telegram limit**: Messages capped at 3900 chars

## Git Workflow

```bash
# Before committing
python -m pytest tests/ -q    # Tests pass?
git add -A
git commit -m "type: description"

# Commit types: fix, feat, refactor, test, docs, chore
```

## File Reference

| File | Purpose |
|------|---------|
| `src/main.py` | CLI entry point |
| `src/service/analysis_service.py` | Main pipeline |
| `src/processor/data_processor.py` | Indicators |
| `src/analyst/gemini_client.py` | AI client |
| `src/utils/config_loader.py` | Config loader |
| `src/utils/json_parser.py` | JSON extraction |
| `src/utils/context_builder.py` | Context building |
| `src/alerts/anomaly_detector.py` | Anomaly detection |
| `src/radar/github_trending.py` | GitHub monitoring |
