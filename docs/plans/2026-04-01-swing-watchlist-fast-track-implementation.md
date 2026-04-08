# Swing Watchlist Fast-Track Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a narrow fast-track so strong watchlist setups can enter the `试仓区` earlier without weakening validation or execution safeguards.

**Architecture:** Keep the change local to the watchlist promotion layer. Update tests first to describe the new eligibility rules, then implement the smallest logic change in `build_watchlist_candidates()` so setup-aware candidates can be promoted before the existing downstream validation, quality, and quota filters run.

**Tech Stack:** Python 3, pytest, existing swing/watchlist services

---

### Task 1: Add failing tests for fast-track promotion

**Files:**
- Modify: `tests/test_watchlist_engine.py`
- Test: `tests/test_watchlist_engine.py`

**Step 1: Write the failing test**

Add focused tests that assert:

```python
def test_build_watchlist_candidates_fast_tracks_strong_setup_candidates():
    ...

def test_build_watchlist_candidates_keeps_medium_confidence_fast_track_candidates_observed():
    ...

def test_build_watchlist_candidates_does_not_fast_track_in_retreat_regime():
    ...
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_watchlist_engine.py -q`

Expected: FAIL because the engine does not yet promote `ACCUMULATE` high-confidence setup-driven names into `进入试仓区`.

### Task 2: Implement fast-track eligibility in watchlist engine

**Files:**
- Modify: `src/service/watchlist_engine.py`
- Test: `tests/test_watchlist_engine.py`

**Step 1: Write minimal implementation**

- Add a helper for setup-aware fast-track eligibility.
- Keep it limited to:
  - `trend_follow`
  - `pullback_resume`
  - `signal in {OPPORTUNITY, ACCUMULATE}`
  - `confidence == 高`
  - `market_regime in {进攻, 均衡}`
- Preserve the current downstream validation, trade guard, and candidate limit behavior.

**Step 2: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_watchlist_engine.py -q`

Expected: PASS

### Task 3: Run focused regression verification

**Files:**
- Test: `tests/test_watchlist_engine.py`
- Optionally verify integration with: `tests/test_swing_strategy.py`

**Step 1: Run focused tests**

Run: `./.venv/bin/pytest tests/test_watchlist_engine.py tests/test_swing_strategy.py -q`

Expected: PASS

**Step 2: Review diff**

Run: `git diff -- src/service/watchlist_engine.py tests/test_watchlist_engine.py docs/plans/2026-04-01-swing-watchlist-fast-track-design.md docs/plans/2026-04-01-swing-watchlist-fast-track-implementation.md`

Expected: only the watchlist engine, related tests, and the two plan docs changed.
