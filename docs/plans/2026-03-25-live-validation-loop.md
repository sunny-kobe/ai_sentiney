# Live Validation Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a real swing recommendation validation loop that prioritizes actual past `swing` advice outcomes, exposes a direct CLI verification command, and feeds the new live evidence into report wording and offensive gating.

**Architecture:** Reuse the existing `daily_records` persistence instead of introducing a new ledger table. Build a merged date timeline from historical `swing` recommendations and subsequent `close` price records, run it through the existing swing forward-window tracker, then aggregate that result together with the existing synthetic scorecard, deterministic backtest, and walk-forward report.

**Tech Stack:** Python 3, sqlite/sqlite3, pytest, existing `swing_tracker`, existing CLI/reporter pipeline

---

### Task 1: Write failing tests for live validation aggregation

**Files:**
- Modify: `tests/test_analysis_service_swing_mode.py`

**Step 1: Write the failing tests**

Add tests that verify:

```python
def test_compute_live_swing_validation_report_merges_swing_and_close_records():
    ...

def test_compute_swing_validation_report_prefers_live_summary_when_samples_are_ready():
    ...

def test_build_validation_performance_context_prefers_live_add_signals():
    ...
```

The assertions should prove:

1. `swing` recommendation actions are evaluated against later `close` data.
2. `validation_report["live"]` exists and contains a summary.
3. `summary_text` starts from live evidence when live samples are sufficient.
4. offensive gating uses live `增配` stats before synthetic stats.

**Step 2: Run test to verify it fails**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py
```

Expected: FAIL because live validation helpers and summary prioritization do not exist yet.

**Step 3: Write minimal implementation**

Implement only the helpers needed to make these tests pass:

1. load recent `swing` report records
2. merge them with `close` price records
3. build a live swing scorecard
4. feed live stats into validation aggregation and performance context

**Step 4: Run test to verify it passes**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_analysis_service_swing_mode.py src/service/analysis_service.py
git commit -m "feat: add live swing validation aggregation"
```

### Task 2: Add a direct CLI validation-report entry point

**Files:**
- Modify: `src/main.py`
- Modify: `src/service/analysis_service.py`
- Create: `tests/test_main_validation_report.py`

**Step 1: Write the failing test**

Add tests that verify:

```python
def test_entry_point_validation_report_prints_swing_validation(monkeypatch, capsys):
    ...
```

The test should prove `python -m src.main --mode swing --validation-report` prints validation output without running the full push pipeline.

**Step 2: Run test to verify it fails**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_main_validation_report.py
```

Expected: FAIL because the flag and code path do not exist yet.

**Step 3: Write minimal implementation**

Add:

1. `--validation-report` CLI flag
2. a service method that returns a swing validation snapshot/text
3. JSON output support if `--output json` is requested

**Step 4: Run test to verify it passes**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_main_validation_report.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/service/analysis_service.py tests/test_main_validation_report.py
git commit -m "feat: add validation report cli entry point"
```

### Task 3: Update swing report wording and renderer coverage

**Files:**
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`
- Modify: `src/main.py`
- Modify: `tests/test_swing_rendering.py`

**Step 1: Write the failing test**

Extend renderer tests so the swing validation section proves:

1. live validation wording can surface in CLI / Telegram / Feishu
2. the rendered text stays plain-language and action-first

**Step 2: Run test to verify it fails**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_swing_rendering.py
```

Expected: FAIL if renderers do not show the new validation wording or snapshot fields correctly.

**Step 3: Write minimal implementation**

Keep renderers simple:

1. continue showing a single `验证摘要`
2. ensure it now reflects live-first validation wording
3. avoid leaking internal tracker jargon

**Step 4: Run test to verify it passes**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_swing_rendering.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/reporter/feishu_client.py src/reporter/telegram_client.py src/main.py tests/test_swing_rendering.py
git commit -m "feat: surface live validation summary in swing outputs"
```

### Task 4: Update docs and run final verification

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-25-live-validation-loop-design.md`
- Modify: `docs/plans/2026-03-25-live-validation-loop.md`

**Step 1: Update docs**

Document:

1. the new `--validation-report` command
2. what “真实建议跟踪” means
3. how to use it for acceptance

**Step 2: Run focused verification**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py tests/test_swing_rendering.py
```

Expected: PASS

**Step 3: Run full verification**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests
```

Expected: PASS

**Step 4: Run manual CLI verification**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m src.main --mode swing --validation-report
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m src.main --mode swing --validation-report --output json
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m src.main --mode swing --dry-run
```

Expected:

1. validation report prints without crashing
2. JSON output is parseable
3. swing dry-run still works

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-25-live-validation-loop-design.md docs/plans/2026-03-25-live-validation-loop.md src/main.py src/service/analysis_service.py src/reporter/feishu_client.py src/reporter/telegram_client.py tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py tests/test_swing_rendering.py
git commit -m "feat: add live validation loop for swing reports"
```
