# Global Index Backup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Yahoo Finance backup path for morning global indices so reports more often receive complete or partial overseas index context.

**Architecture:** Keep Eastmoney/AkShare as the primary morning source, then fill missing required indices from Yahoo Finance chart API using a narrow six-symbol map. Merge normalized results before collection-status evaluation.

**Tech Stack:** Python, requests, asyncio, pytest

---

### Task 1: Add failing tests for merged primary-plus-backup global index collection

**Files:**
- Modify: `tests/test_data_fetcher.py`
- Modify: `src/collector/data_fetcher.py`

**Step 1: Write the failing test**

Add tests proving:

- `get_global_indices()` fills missing targets from Yahoo backup
- `get_global_indices()` can succeed from Yahoo when the primary source is empty
- `collect_morning_data()` marks `global_indices=fresh` when merged coverage reaches threshold

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 3: Write minimal implementation**

- add a six-symbol Yahoo map
- add a Yahoo chart fetch helper
- merge primary and backup results inside `get_global_indices()`
- preserve deterministic ordering

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 5: Commit**

```bash
git add tests/test_data_fetcher.py src/collector/data_fetcher.py
git commit -m "feat: add yahoo backup for morning global indices"
```

### Task 2: Verify runtime behavior and docs

**Files:**
- Create: `docs/plans/2026-03-27-global-index-backup-design.md`
- Create: `docs/plans/2026-03-27-global-index-backup-implementation.md`

**Step 1: Run focused integration suites**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py tests/test_analysis_service_quality_flow.py tests/test_structured_report.py -q`

**Step 2: Run full suite**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q`

**Step 3: Run morning smoke check**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode morning --dry-run --output json | tail -n 1`

Confirm:

- morning output more often includes `global_indices_info`
- `quality_status` stays aligned with actual coverage

**Step 4: Commit docs**

```bash
git add docs/plans/2026-03-27-global-index-backup-design.md docs/plans/2026-03-27-global-index-backup-implementation.md
git commit -m "docs: add global index backup design and plan"
```
