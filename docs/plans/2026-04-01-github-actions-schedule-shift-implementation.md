# GitHub Actions Schedule Shift Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Shift the formal GitHub Actions schedule for `morning`, `midday`, `preclose`, and `close` to the newly agreed Beijing times while keeping scheduled mode routing correct.

**Architecture:** Keep the implementation limited to the GitHub Actions workflow and the existing workflow regression test file. Update test expectations first, verify they fail against the old cron values, then update the workflow comments, cron entries, and `SCHEDULE_EXPR` mapping strings to match exactly.

**Tech Stack:** GitHub Actions YAML, pytest, existing repository workflow regression tests

---

### Task 1: Update workflow regression tests first

**Files:**
- Modify: `tests/test_workflow_swing_automation.py`
- Test: `tests/test_workflow_swing_automation.py`

**Step 1: Write the failing test**

Update the cron assertions to:

```python
assert 'cron: "10 23 * * 0-4"' in content
assert 'cron: "50 1 * * 1-5"' in content
assert 'cron: "5 5 * * 1-5"' in content
assert 'cron: "35 6 * * 1-5"' in content
assert '"10 23 * * 0-4")' in content
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_workflow_swing_automation.py -q`

Expected: FAIL because the workflow file still contains the old schedule strings.

### Task 2: Update the GitHub Actions workflow

**Files:**
- Modify: `.github/workflows/daily_sentinel.yml`
- Test: `tests/test_workflow_swing_automation.py`

**Step 1: Write minimal implementation**

Update:

- comment block with the new CST/UTC mapping
- `on.schedule` cron entries
- `case "$SCHEDULE_EXPR"` values for `morning`, `midday`, `preclose`, and `close`

Keep:

- `swing` schedule unchanged
- fallback current-time logic unchanged
- manual dispatch behavior unchanged

**Step 2: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_workflow_swing_automation.py -q`

Expected: PASS

### Task 3: Run narrow regression verification

**Files:**
- Test: `tests/test_workflow_swing_automation.py`

**Step 1: Re-run focused verification**

Run: `./.venv/bin/pytest tests/test_workflow_swing_automation.py -q`

Expected: PASS with all workflow assertions green.

**Step 2: Review git diff**

Run: `git diff -- .github/workflows/daily_sentinel.yml tests/test_workflow_swing_automation.py docs/plans/2026-04-01-github-actions-schedule-shift-design.md docs/plans/2026-04-01-github-actions-schedule-shift-implementation.md`

Expected: only the workflow, one test file, and the two plan docs changed.
