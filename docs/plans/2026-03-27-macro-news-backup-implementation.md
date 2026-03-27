# Macro News Backup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a fast free backup chain for macro news so morning reports no longer degrade just because `news_cctv` is slow or empty.

**Architecture:** Keep `news_cctv` as the first-choice source, then fall back through a narrow sequence of already-available public news feeds exposed by AkShare. Normalize all successful feeds into the existing `telegraph` and `ai_tech` structure so downstream services remain unchanged.

**Tech Stack:** Python, AkShare, pandas, asyncio, pytest

---

### Task 1: Add failing tests for macro-news backup behavior

**Files:**
- Modify: `tests/test_data_fetcher.py`
- Modify: `src/collector/data_fetcher.py`

**Step 1: Write the failing test**

Add tests proving:

- `get_macro_news()` falls back from CCTV timeout to backup public feeds
- backup-feed rows normalize to headline strings correctly
- `ai_tech` extraction still works on backup headlines
- `collect_morning_data()` stays `fresh` for `macro_news` when backup feeds succeed

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 3: Write minimal implementation**

- add backup-source fetch helper(s) for public feeds
- add normalization helper for differing DataFrame schemas
- wire backup chain into `get_macro_news()`

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py -q`

**Step 5: Commit**

```bash
git add tests/test_data_fetcher.py src/collector/data_fetcher.py
git commit -m "feat: add macro news backup chain"
```

### Task 2: Verify morning integration and docs

**Files:**
- Create: `docs/plans/2026-03-27-macro-news-backup-design.md`
- Create: `docs/plans/2026-03-27-macro-news-backup-implementation.md`

**Step 1: Run focused suites**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_data_fetcher.py tests/test_analysis_service_quality_flow.py tests/test_structured_report.py -q`

**Step 2: Run full suite**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q`

**Step 3: Run morning smoke check**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode morning --dry-run --output json | tail -n 1`

Confirm:

- `macro_news` more often returns headlines
- morning degradation is no longer dominated by CCTV timeout
- `quality_status` remains aligned with actual backup success/failure

**Step 4: Commit docs**

```bash
git add docs/plans/2026-03-27-macro-news-backup-design.md docs/plans/2026-03-27-macro-news-backup-implementation.md
git commit -m "docs: add macro news backup design and plan"
```
