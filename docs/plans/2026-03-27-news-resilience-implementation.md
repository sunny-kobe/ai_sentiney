# News Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make report news inputs more stable by merging public macro-news backups instead of stopping at the first source, and stop wasting work on ETF/fund stock-news fetches that add little signal and produce noisy failures.

**Architecture:** Keep the current macro-news primary source (`news_cctv`) unchanged, but improve the backup path so it aggregates unique headlines across public feeds and returns a cleaner merged set. For per-symbol news, recognize fund-like securities early and skip stock-news fetching entirely, returning a clear skipped status so ETF-heavy runs stay quiet.

**Tech Stack:** Python 3, pandas, AkShare, pytest

---

### Implemented

- `_fetch_macro_news_backup()` now merges unique headlines across `cls`, `sina`, `futu`, `ths` instead of returning the first non-empty list
- ETF / LOF / fund-like symbols now skip `fetch_news` in `_fetch_individual_stock_extras()`
- added regressions for:
  - merged and deduplicated macro-news backups
  - skipping stock-news fetches for fund-like securities

### Verification

Run:

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run
```

Expected:

- full suite passes
- ETF-heavy `swing` dry-run no longer logs repeated `All sources failed for fetch_news`
- macro-news backup can still produce a non-empty merged headline list when the primary source is unavailable
