# Data Stability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve all-mode data collection so reports are generated on time with explicit degradation signals when non-core data is slow or missing.

**Architecture:** Add a shared collection-status layer in `DataCollector`, assign different timeout/degradation behavior to core vs supporting fetches, then propagate that state through `AnalysisService`, quality evaluation, and structured-report output. Keep strategy and rendering logic unchanged unless they already consume quality metadata.

**Tech Stack:** Python, asyncio, pandas, pytest

---

### Task 1: Add failing collector tests for degradation-aware collection

**Files:**
- Modify: `tests/test_data_fetcher.py`
- Modify: `src/collector/data_fetcher.py`

**Step 1: Write the failing test**

Add tests proving:

- `collect_all()` returns `collection_status` and `data_issues`
- when bulk spot fails but single-quote fallback succeeds, stocks are still collected and bulk spot is marked degraded/missing
- supporting-data failures degrade state without removing valid stocks
- `collect_morning_data()` also returns collection-state metadata

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 3: Write minimal implementation**

- add collection-status helpers
- wire collection-state into `collect_all()` and `collect_morning_data()`
- classify data blocks and issues

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 5: Commit**

```bash
git add src/collector/data_fetcher.py tests/test_data_fetcher.py
git commit -m "feat: track degradation in data collection"
```

### Task 2: Add failing service-quality tests for propagated collection state

**Files:**
- Modify: `tests/test_analysis_service_quality_flow.py`
- Modify: `tests/test_structured_report.py`
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/report_quality.py`
- Modify: `src/service/structured_report.py`

**Step 1: Write the failing test**

Add tests proving:

- collected `data_issues` and `collection_status` flow into AI input / structured report
- degraded supporting-data state downgrades quality even when stocks exist
- structured report exposes collection issues/source labels for downstream renderers

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_analysis_service_quality_flow.py tests/test_structured_report.py -q`

**Step 3: Write minimal implementation**

- propagate collector metadata in `AnalysisService`
- teach `evaluate_input_quality()` to use collection-state hints
- include collection metadata in `build_structured_report()`

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_analysis_service_quality_flow.py tests/test_structured_report.py -q`

**Step 5: Commit**

```bash
git add src/service/analysis_service.py src/service/report_quality.py src/service/structured_report.py tests/test_analysis_service_quality_flow.py tests/test_structured_report.py
git commit -m "feat: propagate collection degradation to report quality"
```

### Task 3: Verify full integration

**Files:**
- No code change required

**Step 1: Run focused suites**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py tests/test_analysis_service_quality_flow.py tests/test_structured_report.py -q
```

**Step 2: Run full suite**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q
```

**Step 3: Run runtime smoke checks**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run --output json | tail -n 1 | jq '{quality_status, data_issues}'
```

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode morning --dry-run --output json | tail -n 1 | jq '{quality_status, data_issues}'
```

Confirm:

- both commands produce output
- degraded collection shows up as structured metadata instead of silent failure

**Step 4: Commit docs**

```bash
git add docs/plans/2026-03-27-data-stability-design.md docs/plans/2026-03-27-data-stability-implementation.md
git commit -m "docs: add data stability design and plan"
```
