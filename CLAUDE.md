# CLAUDE.md — Project Sentinel

> This file provides guidance to Claude Code when working in this repository.

## Project Overview

**Project Sentinel** is a local A-share intelligent investment advisor system.

- **Tech Stack**: Python 3.13, asyncio, AkShare, Pydantic, SQLite
- **Architecture**: Collector → Processor → Analyst → Reporter pipeline
- **AI Models**: Google Gemini (primary), MiMo v2 Pro (via OpenAI-compat API)

## Quick Reference

```bash
# Activate environment
source .venv/bin/activate

# Run tests
python -m pytest tests/ -q

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# Common commands
python -m src.main --mode midday          # Midday analysis
python -m src.main --mode close           # Close review
python -m src.main --mode morning         # Morning brief
python -m src.main alert --dry-run        # Test alert system
python -m src.main radar --dry-run        # Test radar system
python -m src.main report --dry-run       # Test report generator
```

## Code Conventions

### Style
- **Type hints**: Required on all public functions
- **Docstrings**: Google style for public APIs
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Imports**: stdlib → third-party → local (sorted alphabetically within groups)
- **A-share convention**: Red = up, Green = down

### Error Handling
- Use `except Exception as e:` — NEVER use bare `except:`
- All HTTP requests MUST have `timeout` parameter
- Use `tenacity` for retry logic on network calls
- Log errors with context before re-raising

### Logging
- Use `from src.utils.logger import logger`
- Log format: `logger.info/warning/error(f"description: {context}")`
- DEBUG for detailed tracing, INFO for milestones, WARNING for recoverable, ERROR for failures

### Configuration
- Config values in `config.yaml`, secrets in `.env`
- Use `${VAR}` syntax for env var references in config
- NEVER hardcode API keys, webhooks, or tokens
- Extract magic numbers to config with sensible defaults

## Architecture Rules

### Module Boundaries
```
collector/    → Only fetches data, no business logic
processor/    → Only calculates indicators, no I/O
analyst/      → Only AI interactions, no data fetching
reporter/     → Only message formatting and sending
service/      → Business logic orchestration
storage/      → Database operations only
utils/        → Shared utilities, no business logic
```

### Data Flow
1. `collector/data_fetcher.py` → fetches raw market data
2. `processor/data_processor.py` → calculates indicators (MA20, bias, signals)
3. `analyst/gemini_client.py` → AI analysis via Gemini
4. `reporter/feishu_client.py` / `telegram_client.py` → sends results

### Key Algorithms
- **MA20 Stitching**: Combines 19 days history + current price for real-time MA20
- **Circuit Breaker**: 3 failures → circuit open, 30s cooldown
- **Deduplication**: Same anomaly type+severity not repeated same day

## Testing Rules

### Requirements
- ALL tests must pass before committing: `python -m pytest tests/ -q`
- New features MUST include tests
- Bug fixes MUST include regression tests
- Use `unittest.mock` for external dependencies (API calls, DB, network)

### Test Structure
```python
class TestFeatureName:
    def test_normal_case(self):
        """Test expected behavior."""
        ...
    
    def test_edge_case(self):
        """Test boundary conditions."""
        ...
    
    def test_error_handling(self):
        """Test failure scenarios."""
        ...
```

### Coverage Target
- Minimum: 60% overall
- New code: 80%+ coverage required

## Task Execution Rules

When receiving a task from Hermes (the orchestrator):

1. **Read first** — Understand existing code before modifying
2. **Minimal changes** — Only modify what's necessary for the task
3. **Verify immediately** — Run tests after each logical change
4. **Atomic commits** — One logical change per commit
5. **Report boundaries** — If you find issues outside scope, note them but don't fix

## Forbidden Actions

- ❌ Never commit API keys or secrets
- ❌ Never use bare `except:` clauses
- ❌ Never make HTTP requests without timeout
- ❌ Never modify `.env` or config files with real credentials
- ❌ Never skip tests to "save time"
- ❌ Never refactor unrelated code while fixing a bug

## Key Files

| File | Purpose |
|------|---------|
| `src/main.py` | CLI entry point and orchestration |
| `src/service/analysis_service.py` | Main analysis pipeline |
| `src/processor/data_processor.py` | Indicator calculations |
| `src/analyst/gemini_client.py` | Gemini AI client |
| `src/utils/config_loader.py` | Configuration management |
| `src/utils/json_parser.py` | Shared JSON parsing |
| `src/utils/context_builder.py` | Shared context building |
| `config.yaml` | Main configuration |
| `tests/` | Test suite (291 tests) |
