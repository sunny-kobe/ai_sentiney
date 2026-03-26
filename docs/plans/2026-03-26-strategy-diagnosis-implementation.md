# Strategy Diagnosis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add grouped strategy diagnostics on top of the new historical validation workflow so `swing` can explain which decision buckets are currently causing underperformance.

**Architecture:** Extend the validation pipeline with a diagnosis observation layer derived from scorecard evaluations plus synthetic context metadata, aggregate those observations by `action / cluster / regime / confidence`, and expose the result through the existing `validate` and `experiment` commands. Keep the first round CLI/JSON-only and leave WebUI unchanged.

**Tech Stack:** Python, pytest, argparse, existing `ValidationService`, `build_swing_scorecard`, `infer_cluster`, current CLI rendering

---

### Task 1: Add diagnosis request/result models

**Files:**
- Create: `src/validation/diagnostics.py`
- Modify: `src/validation/__init__.py`
- Test: `tests/test_validation_diagnostics.py`

**Step 1: Write the failing test**

```python
from src.validation.diagnostics import DiagnosisRequest, DiagnosticGroup


def test_diagnosis_request_normalizes_group_by():
    request = DiagnosisRequest(group_by=" cluster ")

    assert request.group_by == "cluster"


def test_diagnostic_group_serializes_core_metrics():
    group = DiagnosticGroup(
        key="small_cap",
        sample_count=12,
        avg_absolute_return=-0.031,
        avg_relative_return=-0.012,
        avg_max_drawdown=-0.102,
    )

    payload = group.to_dict()
    assert payload["key"] == "small_cap"
    assert payload["sample_count"] == 12
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: FAIL because module/classes do not exist

**Step 3: Write minimal implementation**

Create small dataclasses for:

- diagnosis request
- grouped metrics
- diagnosis summary payload

Keep them serialization-friendly for CLI/JSON reuse.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/validation/diagnostics.py src/validation/__init__.py tests/test_validation_diagnostics.py
git commit -m "feat: add strategy diagnosis models"
```

### Task 2: Build diagnostic observation rows from validation evidence

**Files:**
- Modify: `src/service/validation_service.py`
- Modify: `src/service/swing_strategy.py`
- Test: `tests/test_validation_diagnostics.py`

**Step 1: Write the failing test**

```python
from src.service.validation_service import ValidationService


def test_validation_service_builds_diagnostic_rows_with_cluster_and_regime(sample_validation_service):
    rows = sample_validation_service._build_diagnostic_rows(
        evaluations=[{
            "code": "512480",
            "name": "半导体ETF",
            "action_label": "持有",
            "confidence": "高",
            "windows": {20: {"absolute_return": -0.04, "relative_return": -0.02, "max_drawdown": -0.09}},
        }],
        metadata_by_code={"512480": {"cluster": "semiconductor", "market_regime": "防守"}},
        window=20,
    )

    assert rows[0]["cluster"] == "semiconductor"
    assert rows[0]["market_regime"] == "防守"
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: FAIL because helper does not exist

**Step 3: Write minimal implementation**

Add helpers that:

- flatten scorecard evaluations into one row per code/window
- attach `cluster` via existing `infer_cluster`
- attach `market_regime` from synthetic record metadata
- preserve action/confidence fields

Do not redesign scorecard internals; build this as a thin post-processing layer.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py src/service/swing_strategy.py tests/test_validation_diagnostics.py
git commit -m "feat: add diagnostic observation rows"
```

### Task 3: Add grouped aggregation by action, cluster, regime, and confidence

**Files:**
- Modify: `src/service/validation_service.py`
- Test: `tests/test_validation_diagnostics.py`

**Step 1: Write the failing test**

```python
def test_group_diagnostics_aggregates_rows_by_cluster(sample_validation_service):
    rows = [
        {"cluster": "small_cap", "absolute_return": -0.05, "relative_return": -0.02, "max_drawdown": -0.11},
        {"cluster": "small_cap", "absolute_return": -0.03, "relative_return": -0.01, "max_drawdown": -0.08},
        {"cluster": "broad_beta", "absolute_return": 0.01, "relative_return": 0.00, "max_drawdown": -0.03},
    ]

    report = sample_validation_service._aggregate_diagnostics(rows, group_by="cluster")

    assert report["groups"][0]["key"] == "small_cap"
    assert report["groups"][0]["sample_count"] == 2
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: FAIL because aggregation helper does not exist

**Step 3: Write minimal implementation**

Implement aggregation that:

- groups by requested dimension
- calculates sample count
- calculates average absolute return
- calculates average relative return
- calculates average max drawdown
- sorts worst groups first for diagnosis readability

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py tests/test_validation_diagnostics.py
git commit -m "feat: add grouped strategy diagnostics"
```

### Task 4: Generate investor-facing diagnosis summary

**Files:**
- Modify: `src/service/validation_service.py`
- Test: `tests/test_validation_diagnostics.py`

**Step 1: Write the failing test**

```python
def test_build_diagnosis_summary_calls_out_top_drag(sample_validation_service):
    summary = sample_validation_service._build_diagnosis_summary(
        group_by="cluster",
        primary_window=20,
        groups=[
            {"key": "small_cap", "sample_count": 18, "avg_absolute_return": -0.046, "avg_relative_return": -0.019, "avg_max_drawdown": -0.112},
            {"key": "broad_beta", "sample_count": 12, "avg_absolute_return": -0.005, "avg_relative_return": 0.001, "avg_max_drawdown": -0.032},
        ],
    )

    assert "small_cap" in summary or "小盘" in summary
    assert "拖累" in summary
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: FAIL because summary helper does not exist

**Step 3: Write minimal implementation**

Create a plain-language summary that highlights:

- worst group
- strongest group
- whether the issue looks offensive or defensive

Keep the first version deterministic and concise.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_diagnostics.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py tests/test_validation_diagnostics.py
git commit -m "feat: add diagnosis summary text"
```

### Task 5: Expose diagnostics through `validate` and `experiment`

**Files:**
- Modify: `src/main.py`
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/validation_service.py`
- Test: `tests/test_main_validate_command.py`

**Step 1: Write the failing test**

```python
def test_validate_command_outputs_diagnostics_when_group_by_is_set(cli_runner):
    result = cli_runner([
        "validate",
        "--mode",
        "swing",
        "--days",
        "60",
        "--group-by",
        "action",
        "--output",
        "json",
    ])

    assert result.returncode == 0
    assert '"diagnostics"' in result.stdout
    assert '"group_by": "action"' in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_validate_command.py -q`
Expected: FAIL because `--group-by` is unsupported

**Step 3: Write minimal implementation**

Add CLI support for `--group-by` and thread it through:

- `validate`
- `experiment`
- `build_validation_result`

If `--group-by` is omitted, keep current output unchanged.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_validate_command.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/service/analysis_service.py src/service/validation_service.py tests/test_main_validate_command.py
git commit -m "feat: expose grouped diagnostics in validation commands"
```

### Task 6: Document the diagnosis workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-26-strategy-diagnosis-design.md`
- Modify: `docs/plans/2026-03-26-strategy-diagnosis-implementation.md`
- Test: `tests/test_main_validate_command.py`

**Step 1: Write the failing test**

```python
def test_readme_mentions_grouped_diagnostics():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "--group-by action" in text
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_validate_command.py -q`
Expected: FAIL until README and examples are updated

**Step 3: Write minimal implementation**

Document:

- grouped diagnostics command examples
- what each group dimension means
- how to use diagnosis output to drive rule tuning

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_validate_command.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-26-strategy-diagnosis-design.md docs/plans/2026-03-26-strategy-diagnosis-implementation.md tests/test_main_validate_command.py
git commit -m "docs: add grouped diagnosis workflow"
```
