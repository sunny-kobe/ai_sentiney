# Source Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce false report degradation and speed up morning global-index collection by hardening collector fallbacks and optional-block handling.

**Architecture:** Extend `DataCollector` with placeholder-aware fallback validation and optional block semantics, then replace the slow morning global-index path with a fast spot-then-history fallback. Keep downstream quality and rendering interfaces intact.

**Tech Stack:** Python, asyncio, pandas, pytest

---

### Task 1: Lock in failing tests for real collector failure modes

**Files:**
- Modify: `tests/test_data_fetcher.py`

**Step 1: Write the failing test**

Add tests proving:

- `fetch_market_breadth` skips placeholder strings like `N/A (Tencent)`
- `fetch_news` skips empty strings and continues to later sources
- ETF-heavy portfolios stay `fresh` when only optional enrichment is missing
- `get_global_indices()` falls back to `index_global_hist_em()` when the snapshot table times out

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 3: Write minimal implementation**

- add result-validation helper inside `DataCollector`
- add optional-block handling to collection-state finalization
- add ETF-heavy stock-news policy
- add fast global-index history fallback

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 5: Commit**

```bash
git add tests/test_data_fetcher.py src/collector/data_fetcher.py
git commit -m "feat: harden collector source fallbacks"
```

### Task 2: Verify cross-service compatibility

**Files:**
- No code change expected

**Step 1: Run focused suites**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py tests/test_analysis_service_quality_flow.py tests/test_analysis_service_swing_mode.py tests/test_structured_report.py -q`

**Step 2: Run full suite**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q`

**Step 3: Run runtime smoke checks**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run --output json | tail -n 1`

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode morning --dry-run --output json | tail -n 1`

Confirm:

- `swing` no longer degrades just because `bulk_spot` is unavailable
- ETF-heavy portfolios no longer degrade purely on missing `stock_news`
- `morning` usually returns global index context through the fast fallback path

**Step 4: Commit docs**

```bash
git add docs/plans/2026-03-27-source-resilience-design.md docs/plans/2026-03-27-source-resilience-implementation.md
git commit -m "docs: add source resilience design and plan"
```
