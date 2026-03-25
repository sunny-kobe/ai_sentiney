# Hypothesis Validation Assistant Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a first-class historical validation and experiment workflow for `swing`, then refactor the investor-facing report to consume that unified evidence model.

**Architecture:** Introduce a dedicated validation service and result model on top of the existing deterministic backtest engine, route both legacy validation snapshots and new validation commands through it, then simplify `swing` reporting around action plus evidence. Keep compatibility with current report generation while moving validation logic out of `AnalysisService`.

**Tech Stack:** Python, pytest, argparse, existing `src/backtest/*` modules, SQLite-backed historical records, current WebUI/report renderers

---

### Task 1: Add validation request/result domain models

**Files:**
- Create: `src/validation/models.py`
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_validation_models.py`

**Step 1: Write the failing test**

```python
from src.validation.models import ValidationRequest, ValidationResult


def test_validation_request_normalizes_date_range_and_codes():
    request = ValidationRequest(
        mode="swing",
        date_from="2026-03-01",
        date_to="2026-03-25",
        codes=["510300", " 512660 "],
    )

    assert request.mode == "swing"
    assert request.date_from == "2026-03-01"
    assert request.date_to == "2026-03-25"
    assert request.codes == ["510300", "512660"]


def test_validation_result_compact_snapshot_keeps_high_signal_fields_only():
    result = ValidationResult(
        mode="swing",
        as_of_date="2026-03-25",
        investor_summary="历史验证支持继续进攻，但只做分批加仓。",
        compact={"verdict": "supportive", "offensive_allowed": True},
    )

    assert result.compact["verdict"] == "supportive"
    assert result.investor_summary.startswith("历史验证支持")
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_validation_models.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing classes

**Step 3: Write minimal implementation**

Create typed dataclasses that:

- normalize trimmed code lists
- store date range fields
- expose a compact payload
- support conversion to dict for CLI / WebUI / push reuse

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_validation_models.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/validation/models.py tests/test_validation_models.py
git commit -m "feat: add validation domain models"
```

### Task 2: Build record slicing helpers for date range and code filters

**Files:**
- Create: `src/validation/history.py`
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_validation_history.py`

**Step 1: Write the failing test**

```python
from src.validation.history import slice_records


def test_slice_records_filters_date_range_and_codes(sample_records):
    result = slice_records(
        sample_records,
        date_from="2026-03-02",
        date_to="2026-03-03",
        codes=["510300"],
    )

    assert [record["date"] for record in result] == ["2026-03-02", "2026-03-03"]
    assert all(
        {stock["code"] for stock in record["raw_data"]["stocks"]} == {"510300"}
        for record in result
    )
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_validation_history.py -q`
Expected: FAIL because helper does not exist

**Step 3: Write minimal implementation**

Implement helpers that:

- filter by inclusive date range
- support recent `days`
- trim stock lists to the requested codes while preserving record shape
- return records sorted by date

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_validation_history.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/validation/history.py tests/test_validation_history.py
git commit -m "feat: add validation history slicer"
```

### Task 3: Extract a dedicated validation service from `AnalysisService`

**Files:**
- Create: `src/service/validation_service.py`
- Modify: `src/service/analysis_service.py`
- Modify: `src/backtest/report.py`
- Test: `tests/test_validation_service.py`

**Step 1: Write the failing test**

```python
from src.service.validation_service import ValidationService


def test_validation_service_builds_result_with_backtest_and_walkforward(sample_validation_db):
    service = ValidationService(sample_validation_db, config={"portfolio_state": {"lot_size": 100}})

    result = service.build_validation_result(mode="swing", days=30)

    assert result.mode == "swing"
    assert "backtest" in result.details
    assert "walkforward" in result.details
    assert isinstance(result.compact, dict)
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_validation_service.py -q`
Expected: FAIL because service does not exist

**Step 3: Write minimal implementation**

Move validation-specific logic out of `AnalysisService` into a dedicated service that:

- loads historical records
- computes live validation
- computes synthetic scorecard
- runs deterministic backtest
- runs walk-forward
- builds a `ValidationResult`

Add summary helpers in `src/backtest/report.py` only when necessary for reuse.

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_validation_service.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py src/service/analysis_service.py src/backtest/report.py tests/test_validation_service.py
git commit -m "refactor: extract validation service"
```

### Task 4: Extend backtest reporting with trade ledger and equity evidence

**Files:**
- Modify: `src/backtest/report.py`
- Modify: `src/backtest/engine.py`
- Test: `tests/test_backtest_report_details.py`

**Step 1: Write the failing test**

```python
from src.backtest.engine import run_deterministic_backtest


def test_backtest_result_includes_trade_ledger_and_equity_summary(sample_backtest_records):
    result = run_deterministic_backtest(sample_backtest_records, initial_cash=100000.0)

    assert isinstance(result["trades"], list)
    assert isinstance(result["equity_curve"], list)
    assert "trade_count" in result
    assert "max_drawdown" in result
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_backtest_report_details.py -q`
Expected: FAIL because expected summary/detail fields are missing or incomplete

**Step 3: Write minimal implementation**

Ensure backtest outputs include:

- compact trade ledger items
- compact equity curve items
- stable summary keys for CLI / JSON
- optional benchmark-relative summary input if available

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_backtest_report_details.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/backtest/report.py src/backtest/engine.py tests/test_backtest_report_details.py
git commit -m "feat: expose richer backtest evidence"
```

### Task 5: Add CLI validation and experiment commands

**Files:**
- Modify: `src/main.py`
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/validation_service.py`
- Test: `tests/test_main_validate_command.py`

**Step 1: Write the failing test**

```python
def test_main_validate_command_outputs_compact_validation_json(cli_runner):
    result = cli_runner([
        "validate",
        "--mode",
        "swing",
        "--from",
        "2026-03-01",
        "--to",
        "2026-03-20",
        "--output",
        "json",
    ])

    assert result.returncode == 0
    assert '"mode": "swing"' in result.stdout
    assert '"compact"' in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_main_validate_command.py -q`
Expected: FAIL because command is unsupported

**Step 3: Write minimal implementation**

Add subcommands that:

- support `validate`
- support `experiment`
- accept `--days`, `--from`, `--to`, `--codes`
- preserve legacy `--validation-report`

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_main_validate_command.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/service/analysis_service.py src/service/validation_service.py tests/test_main_validate_command.py
git commit -m "feat: add validation and experiment commands"
```

### Task 6: Redesign `swing` investor summary around action plus evidence

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/strategy_engine.py`
- Modify: `src/reporter/*` if needed
- Test: `tests/test_swing_report_investor_summary.py`

**Step 1: Write the failing test**

```python
def test_swing_report_places_action_before_evidence(sample_analysis_service):
    result = sample_analysis_service.build_swing_output()

    assert "市场判断" in result
    assert "账户动作" in result
    assert "撤退条件" in result
    assert "历史证据" in result
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_swing_report_investor_summary.py -q`
Expected: FAIL because old summary layout is still in use

**Step 3: Write minimal implementation**

Refactor `swing` rendering so that:

- conclusion comes first
- jargon is reduced
- retreat condition is explicit
- validation summary is tied to the current action bias

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_swing_report_investor_summary.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/analysis_service.py src/service/strategy_engine.py tests/test_swing_report_investor_summary.py
git commit -m "feat: simplify swing investor summary"
```

### Task 7: Unify compact validation output for CLI, WebUI, and push

**Files:**
- Modify: `src/service/validation_service.py`
- Modify: `src/web/api.py`
- Modify: `src/reporter/*`
- Test: `tests/test_validation_surface_unification.py`

**Step 1: Write the failing test**

```python
def test_validation_surfaces_share_same_compact_payload(sample_validation_service):
    payload = sample_validation_service.build_validation_snapshot(mode="swing")

    assert "compact" in payload
    assert "summary_text" in payload
    assert "as_of_date" in payload
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_validation_surface_unification.py -q`
Expected: FAIL because output assembly differs by surface

**Step 3: Write minimal implementation**

Route CLI snapshot, Web validation API, and push hint lines through the same compact payload builder.

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_validation_surface_unification.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py src/web/api.py tests/test_validation_surface_unification.py
git commit -m "refactor: unify validation output surfaces"
```

### Task 8: Verify core workflows and document operator usage

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-25-hypothesis-validation-assistant-design.md`
- Modify: `docs/plans/2026-03-25-hypothesis-validation-assistant-implementation.md`
- Test: `tests/test_main_validate_command.py`
- Test: `tests/test_web_validation_api.py`
- Test: `tests/test_main_validation_report.py`

**Step 1: Write the failing test**

```python
def test_readme_mentions_validate_command():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "python -m src.main validate --mode swing" in text
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_main_validate_command.py tests/test_web_validation_api.py tests/test_main_validation_report.py -q`
Expected: FAIL until docs and integrations are aligned

**Step 3: Write minimal implementation**

Update docs and operator guidance so that:

- the new validation workflow is discoverable
- users know how to validate a date range
- legacy snapshot usage remains documented

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_main_validate_command.py tests/test_web_validation_api.py tests/test_main_validation_report.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-25-hypothesis-validation-assistant-design.md docs/plans/2026-03-25-hypothesis-validation-assistant-implementation.md tests/test_main_validate_command.py tests/test_web_validation_api.py tests/test_main_validation_report.py
git commit -m "docs: document validation workflow"
```
