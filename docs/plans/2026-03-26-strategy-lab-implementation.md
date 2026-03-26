# Strategy Lab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new `lab` workflow that compares baseline vs candidate strategy variants for rule, parameter, and portfolio experiments on top of the existing swing validation stack.

**Architecture:** Keep `validate` as the current-state audit path and build a dedicated `lab` command with its own request/result models and service. Reuse the current synthetic records, scorecard, deterministic backtest, walk-forward, and grouped diagnostics pipeline. Apply candidate changes through a deterministic mutation layer so experiments stay explainable and low-risk.

**Tech Stack:** Python, pytest, argparse, existing `ValidationService`, current backtest/diagnostics modules

---

### Task 1: Add lab request/result models

**Files:**
- Create: `src/lab/models.py`
- Modify: `src/lab/__init__.py`
- Test: `tests/test_lab_models.py`

**Step 1: Write the failing test**

```python
from src.lab.models import LabRequest, LabResult


def test_lab_request_normalizes_override_text():
    request = LabRequest(
        mode="swing",
        preset="aggressive_midterm",
        overrides=["confidence_min=高", "cluster_blocklist=small_cap,ai"],
    )

    assert request.override_map["confidence_min"] == "高"
    assert request.override_map["cluster_blocklist"] == "small_cap,ai"


def test_lab_result_serializes_baseline_candidate_and_diff():
    result = LabResult(
        mode="swing",
        preset="aggressive_midterm",
        baseline={"summary_text": "baseline"},
        candidate={"summary_text": "candidate"},
        diff={"total_return_delta": 0.024},
        winner="candidate",
        summary_text="candidate 更优",
    )

    payload = result.to_dict()
    assert payload["winner"] == "candidate"
    assert payload["diff"]["total_return_delta"] == 0.024
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_lab_models.py -q`
Expected: FAIL because lab models do not exist

**Step 3: Write minimal implementation**

Create simple dataclasses for:

- `LabRequest`
- `LabResult`
- optional helper parsing for `overrides -> override_map`

Keep them JSON-friendly and small.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_lab_models.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/lab/models.py src/lab/__init__.py tests/test_lab_models.py
git commit -m "feat: add strategy lab models"
```

### Task 2: Add preset registry and override parsing

**Files:**
- Create: `src/lab/presets.py`
- Test: `tests/test_lab_presets.py`

**Step 1: Write the failing test**

```python
from src.lab.presets import resolve_lab_preset


def test_resolve_lab_preset_returns_candidate_defaults():
    preset = resolve_lab_preset("defensive_exit_fix")

    assert preset["name"] == "defensive_exit_fix"
    assert preset["rule_overrides"]["hold_in_defense"] == "degrade"


def test_resolve_lab_preset_rejects_unknown_name():
    try:
        resolve_lab_preset("missing")
    except ValueError as exc:
        assert "unknown preset" in str(exc)
    else:
        raise AssertionError("expected unknown preset to fail")
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_lab_presets.py -q`
Expected: FAIL because preset registry does not exist

**Step 3: Write minimal implementation**

Implement a small preset registry with first-wave presets:

- `aggressive_midterm`
- `defensive_exit_fix`
- `high_conf_only`
- `broad_beta_core`
- `risk_cluster_filter`

Each preset must expose:

- `name`
- `description`
- `rule_overrides`
- `parameter_overrides`
- `portfolio_overrides`

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_lab_presets.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/lab/presets.py tests/test_lab_presets.py
git commit -m "feat: add strategy lab preset registry"
```

### Task 3: Build candidate mutation layer

**Files:**
- Create: `src/lab/mutations.py`
- Test: `tests/test_lab_mutations.py`

**Step 1: Write the failing test**

```python
from src.lab.mutations import apply_candidate_mutations


def test_apply_candidate_mutations_degrades_holds_in_defense():
    actions = [
        {"code": "512480", "action_label": "持有", "market_regime": "防守", "cluster": "semiconductor", "confidence": "高"},
        {"code": "510300", "action_label": "持有", "market_regime": "进攻", "cluster": "broad_beta", "confidence": "高"},
    ]

    mutated = apply_candidate_mutations(
        actions,
        rule_overrides={"hold_in_defense": "degrade"},
        parameter_overrides={},
        portfolio_overrides={},
    )

    assert mutated[0]["action_label"] == "减配"
    assert mutated[1]["action_label"] == "持有"
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_lab_mutations.py -q`
Expected: FAIL because mutation layer does not exist

**Step 3: Write minimal implementation**

Implement deterministic mutation helpers for first-wave overrides:

- `hold_in_defense=degrade`
- `confidence_min=高`
- `cluster_blocklist=*`
- `core_only=broad_beta`

Keep this layer post-processing only. Do not modify main strategy code yet.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_lab_mutations.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/lab/mutations.py tests/test_lab_mutations.py
git commit -m "feat: add strategy lab mutation layer"
```

### Task 4: Add reusable validation comparison helper

**Files:**
- Modify: `src/service/validation_service.py`
- Test: `tests/test_validation_service_lab_compare.py`

**Step 1: Write the failing test**

```python
from src.service.validation_service import ValidationService


def test_build_comparison_diff_reports_return_drawdown_and_trade_deltas():
    service = ValidationService(db=None, config={})

    diff = service._build_comparison_diff(
        baseline={"backtest": {"total_return": 0.08, "max_drawdown": -0.10, "trade_count": 4}},
        candidate={"backtest": {"total_return": 0.11, "max_drawdown": -0.07, "trade_count": 10}},
    )

    assert diff["total_return_delta"] == 0.03
    assert diff["max_drawdown_delta"] == 0.03
    assert diff["trade_count_delta"] == 6
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_service_lab_compare.py -q`
Expected: FAIL because comparison helper does not exist

**Step 3: Write minimal implementation**

Add thin helpers for:

- baseline/candidate diff
- comparison score
- winner selection

Do not embed preset logic here; this layer only compares already-built reports.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_validation_service_lab_compare.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py tests/test_validation_service_lab_compare.py
git commit -m "feat: add validation comparison helpers"
```

### Task 5: Build `StrategyLabService`

**Files:**
- Create: `src/service/strategy_lab_service.py`
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_strategy_lab_service.py`

**Step 1: Write the failing test**

```python
from src.service.strategy_lab_service import StrategyLabService


def test_strategy_lab_service_returns_baseline_candidate_and_winner(monkeypatch):
    service = StrategyLabService(db=None, config={})

    monkeypatch.setattr(service, "_build_variant_reports", lambda request: {
        "baseline": {"summary_text": "baseline", "backtest": {"total_return": 0.08, "max_drawdown": -0.10, "trade_count": 4}},
        "candidate": {"summary_text": "candidate", "backtest": {"total_return": 0.11, "max_drawdown": -0.07, "trade_count": 10}},
    })

    result = service.build_lab_result(mode="swing", preset="aggressive_midterm")

    assert result.winner == "candidate"
    assert "candidate" in result.summary_text
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_strategy_lab_service.py -q`
Expected: FAIL because service does not exist

**Step 3: Write minimal implementation**

Create `StrategyLabService` that:

- resolves preset
- parses overrides
- builds baseline report
- applies mutations to synthetic actions
- builds candidate report
- computes diff, score, winner, summary text

Expose it via `AnalysisService.build_lab_result(...)`.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_strategy_lab_service.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/strategy_lab_service.py src/service/analysis_service.py tests/test_strategy_lab_service.py
git commit -m "feat: add strategy lab service"
```

### Task 6: Expose `lab` through CLI

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main_lab_command.py`

**Step 1: Write the failing test**

```python
import json
import src.main as main_module


def test_entry_point_lab_command_outputs_json(monkeypatch, capsys):
    class FakeResult:
        def to_dict(self):
            return {
                "mode": "swing",
                "preset": "aggressive_midterm",
                "winner": "candidate",
                "summary_text": "candidate 更优",
            }

    class FakeService:
        def build_lab_result(self, **kwargs):
            assert kwargs["preset"] == "aggressive_midterm"
            assert kwargs["overrides"] == ["confidence_min=高"]
            return FakeResult()

    monkeypatch.setattr(main_module, "setup_proxy", lambda: None)
    monkeypatch.setattr(main_module, "AnalysisService", lambda: FakeService())
    monkeypatch.setattr(
        main_module.sys,
        "argv",
        ["sentinel", "lab", "--mode", "swing", "--preset", "aggressive_midterm", "--override", "confidence_min=高", "--output", "json"],
    )

    main_module.entry_point()

    out = json.loads(capsys.readouterr().out)
    assert out["winner"] == "candidate"
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_lab_command.py -q`
Expected: FAIL because `lab` command is unsupported

**Step 3: Write minimal implementation**

Add `lab` to CLI command choices with:

- `--preset`
- repeatable `--override key=value`
- `--group-by`
- `--output`

Route to `AnalysisService.build_lab_result(...)`.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_lab_command.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py tests/test_main_lab_command.py
git commit -m "feat: expose strategy lab command"
```

### Task 7: Add diagnostics diff to lab output

**Files:**
- Modify: `src/service/strategy_lab_service.py`
- Test: `tests/test_strategy_lab_service.py`

**Step 1: Write the failing test**

```python
def test_strategy_lab_service_reports_diagnostic_improvement(monkeypatch):
    service = StrategyLabService(db=None, config={})

    monkeypatch.setattr(service, "_build_variant_reports", lambda request: {
        "baseline": {"diagnostics": {"top_drag": {"key": "持有"}}},
        "candidate": {"diagnostics": {"top_drag": {"key": "减配"}}},
    })

    result = service.build_lab_result(mode="swing", preset="defensive_exit_fix")

    assert result.diff["diagnostic_shift"]["baseline_top_drag"] == "持有"
    assert result.diff["diagnostic_shift"]["candidate_top_drag"] == "减配"
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_strategy_lab_service.py -q`
Expected: FAIL because diagnostic shift is missing

**Step 3: Write minimal implementation**

Extend lab diff with:

- `baseline_top_drag`
- `candidate_top_drag`
- whether drag source changed

Keep it deterministic and small.

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_strategy_lab_service.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/strategy_lab_service.py tests/test_strategy_lab_service.py
git commit -m "feat: add lab diagnostic diff"
```

### Task 8: Document the strategy lab workflow

**Files:**
- Modify: `README.md`
- Test: `tests/test_main_lab_command.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_readme_mentions_lab_command():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "python -m src.main lab --preset aggressive_midterm" in text
```

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_lab_command.py -q`
Expected: FAIL because README has no lab docs

**Step 3: Write minimal implementation**

Document:

- when to use `lab`
- example presets
- example `--override`
- how to interpret baseline/candidate/diff

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_main_lab_command.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_main_lab_command.py
git commit -m "docs: add strategy lab usage"
```

### Task 9: Run full regression

**Files:**
- Modify: none expected
- Test: full suite

**Step 1: Run focused strategy lab suite**

Run:

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest \
  tests/test_lab_models.py \
  tests/test_lab_presets.py \
  tests/test_lab_mutations.py \
  tests/test_validation_service_lab_compare.py \
  tests/test_strategy_lab_service.py \
  tests/test_main_lab_command.py -q
```

Expected: PASS

**Step 2: Run full suite**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q`
Expected: PASS

**Step 3: Commit final integrated state**

```bash
git add .
git commit -m "feat: add strategy lab workflow"
```
