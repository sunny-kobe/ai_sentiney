# Market Breadth Backup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce false `market breadth unavailable` degradation by adding a lightweight backup path when the primary breadth sources fail or return non-breadth placeholders.

**Architecture:** Keep the existing source fallback chain, but tighten breadth validation so fake index-summary strings do not count as breadth. When all primary breadth sources fail, call a lightweight `legu` backup (`ak.stock_market_activity_legu`) and normalize its table output into the existing `涨 / 跌 / 平` summary format.

**Tech Stack:** Python 3, pandas, AkShare, pytest

---

### Implemented

- reject non-breadth strings in `DataCollector._is_invalid_fallback_result()` for `fetch_market_breadth`
- add `legu` backup parsing in `DataCollector.get_market_breadth()`
- downgrade `Efinance.fetch_market_breadth()` to an explicit placeholder so fallback continues
- add regression tests for:
  - skipping fake breadth strings
  - restoring breadth from `legu`
  - preserving `Unknown` when backup is also unavailable

### Verification

Run:

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run
```

Expected:

- full suite passes
- local dry-run logs `Market breadth restored from legu backup.`
- report no longer shows `market breadth unavailable` in the common fallback-success path
