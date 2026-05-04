# .cursorrules — Project Sentinel

## Project
A-share intelligent investment advisor. Python 3.13, asyncio, AkShare, Pydantic, SQLite.

## Rules

### Code Style
- Type hints on all public functions
- Google-style docstrings
- snake_case functions, PascalCase classes
- A-share convention: red = up, green = down

### Error Handling
- Always `except Exception as e:` with logging
- Always `timeout` on HTTP requests
- Use `tenacity` for retries
- Never bare `except:`

### Testing
- Run `python -m pytest tests/ -q` before committing
- All 291 tests must pass
- Mock external dependencies
- New code needs tests

### Configuration
- Config in `config.yaml`, secrets in `.env`
- Use `${VAR}` for env vars
- Never hardcode credentials
- Extract magic numbers to config

### Commands
```bash
source .venv/bin/activate
python -m pytest tests/ -q                    # Test
python -m pytest tests/ --cov=src             # Coverage
python -m src.main --mode midday --dry-run    # Test midday
python -m src.main alert --dry-run            # Test alert
```

### Key Files
- `src/main.py` — CLI entry
- `src/service/analysis_service.py` — Main pipeline
- `src/processor/data_processor.py` — Indicators
- `config.yaml` — Configuration
- `tests/` — Test suite

### Don't
- ❌ Bare except
- ❌ Hardcoded credentials
- ❌ HTTP without timeout
- ❌ Skip tests
- ❌ Refactor unrelated code in bug fixes
