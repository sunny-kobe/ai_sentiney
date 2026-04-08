# Swing Watchlist Trial Messaging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make watchlist candidate messaging explain the setup type behind a trial-entry recommendation so users can tell whether the candidate is a breakout try or a pullback-resume try.

**Architecture:** Keep the change local to watchlist candidate field generation. Add tests first for setup-specific `plan` text, then implement a small helper in `src/service/watchlist_engine.py` that returns concise setup-aware messaging while leaving the renderer interfaces unchanged.

**Tech Stack:** Python 3, pytest, existing watchlist engine and swing rendering code

---

### Task 1: Add failing tests for setup-aware watchlist plan text

**Files:**
- Modify: `tests/test_watchlist_engine.py`
- Modify: `tests/test_swing_rendering.py`

**Step 1: Write the failing test**

Add tests that assert:

```python
def test_build_watchlist_candidates_uses_setup_specific_trial_plan_text():
    ...

def test_cli_swing_summary_shows_setup_specific_watchlist_trial_plan():
    ...
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_watchlist_engine.py tests/test_swing_rendering.py -q`

Expected: FAIL because the watchlist candidate copy is still generic.

### Task 2: Implement setup-aware watchlist plan generation

**Files:**
- Modify: `src/service/watchlist_engine.py`
- Test: `tests/test_watchlist_engine.py`
- Test: `tests/test_swing_rendering.py`

**Step 1: Write minimal implementation**

- Add a helper that maps `setup_type + action_label` to short plan text.
- Cover:
  - `进入试仓区 + trend_follow`
  - `进入试仓区 + pullback_resume`
  - `继续观察 + trend_follow`
  - `继续观察 + pullback_resume`
- Keep validation and trade-guard override copy stronger than the generic setup copy.

**Step 2: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_watchlist_engine.py tests/test_swing_rendering.py -q`

Expected: PASS

### Task 3: Run focused regression verification

**Files:**
- Test: `tests/test_watchlist_engine.py`
- Test: `tests/test_swing_rendering.py`
- Optionally verify: `tests/test_swing_strategy.py`

**Step 1: Run focused regression**

Run: `./.venv/bin/pytest tests/test_watchlist_engine.py tests/test_swing_rendering.py tests/test_swing_strategy.py -q`

Expected: PASS

**Step 2: Review diff**

Run: `git diff -- src/service/watchlist_engine.py tests/test_watchlist_engine.py tests/test_swing_rendering.py docs/plans/2026-04-01-swing-watchlist-trial-messaging-design.md docs/plans/2026-04-01-swing-watchlist-trial-messaging-implementation.md`

Expected: only the watchlist engine, the targeted tests, and the two plan docs changed.
