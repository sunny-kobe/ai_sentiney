# Swing Automation And Delivery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add scheduled/manual GitHub Action support for `swing` delivery and restore a fully green test suite.

**Architecture:** Keep one workflow file, but extend it with explicit `workflow_dispatch` inputs and schedule-aware mode selection. Fix the unstable regression test by making its date dynamic instead of changing production quality logic.

**Tech Stack:** GitHub Actions YAML, Python 3, pytest, existing Feishu/Telegram publish pipeline

---

### Task 1: Stabilize The Quality-Flow Regression Test

**Files:**
- Modify: `tests/test_analysis_service_quality_flow.py`

**Step 1: Write the failing test**

Use the existing failing full-suite test as the red state:
- `test_run_analysis_normal_mode_passes_structured_report_to_gemini`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py::test_run_analysis_normal_mode_passes_structured_report_to_gemini`

Expected: FAIL because the hardcoded `context_date` is now stale.

**Step 3: Write minimal implementation**

Update the test to derive `context_date` from the current date so the intended `normal` path remains valid.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py::test_run_analysis_normal_mode_passes_structured_report_to_gemini`

Expected: PASS

### Task 2: Add Workflow Tests For Swing Automation

**Files:**
- Create: `tests/test_workflow_swing_automation.py`
- Modify: `.github/workflows/daily_sentinel.yml`

**Step 1: Write the failing test**

Cover:
- workflow has a scheduled `swing` cron
- `workflow_dispatch` supports `mode`
- `workflow_dispatch` supports `publish_target`
- run script explicitly routes `swing`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_workflow_swing_automation.py`

Expected: FAIL because the workflow has no manual inputs and no swing schedule.

**Step 3: Write minimal implementation**

Extend the workflow with:
- a new `swing` cron
- manual `mode` input
- manual `publish_target` input
- schedule-aware mode selection logic

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_workflow_swing_automation.py`

Expected: PASS

### Task 3: Verify Automation End-To-End

**Files:**
- Modify: `README.md` if needed

**Step 1: Run focused tests**

Run:
- `.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py tests/test_workflow_swing_automation.py`

**Step 2: Run full suite**

Run:
- `.venv/bin/python -m pytest -q tests`

**Step 3: Commit**

```bash
git add .github/workflows/daily_sentinel.yml docs/plans/2026-03-24-swing-automation-design.md docs/plans/2026-03-24-swing-automation-implementation.md tests/test_analysis_service_quality_flow.py tests/test_workflow_swing_automation.py
git commit -m "feat: automate swing delivery workflow"
git push origin main
```
