# Report Schedule Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a true `preclose` execution report, keep `close` as pure post-market review, and move the automation schedule to time slots that match actual A-share execution windows.

**Architecture:** Treat `preclose` as a new first-class mode that reuses the existing intraday data and midday-style AI schema, but has its own schedule, mode routing, CLI label, and push titles. Keep `close` on the existing post-close review schema and reporters. Update GitHub Actions cron schedules and mode resolution so automated runs line up with practical user action windows.

**Tech Stack:** Python 3.11, pytest, existing `AnalysisService`, CLI renderers, Feishu/Telegram reporters, GitHub Actions workflow YAML

---

### Task 1: Add failing tests for `preclose` mode acceptance and routing

**Files:**
- Modify: `tests/test_publish_target.py`
- Modify: `tests/test_report_quality.py`
- Modify: `tests/test_report_rendering_quality.py`
- Modify: `tests/test_structured_report.py`

**Step 1: Write the failing tests**

Cover:
- `run_analysis(mode="preclose")` can route to Telegram / Feishu preclose senders
- input quality rules treat `preclose` like an intraday report
- CLI / Telegram rendering uses `收盘前执行` wording rather than `午盘` or `收盘复盘`
- structured report accepts `preclose` mode

**Step 2: Run tests to verify they fail**

Run:
- `.venv/bin/python -m pytest -q tests/test_publish_target.py -k preclose`
- `.venv/bin/python -m pytest -q tests/test_report_quality.py tests/test_report_rendering_quality.py tests/test_structured_report.py -k preclose`

Expected: FAIL because `preclose` mode does not exist yet.

**Step 3: Write minimal implementation**

Implement:
- new `preclose` mode branches
- rendering helpers / titles
- quality and structured-report mode support

**Step 4: Run tests to verify they pass**

Run the same commands and confirm PASS.

### Task 2: Add failing tests for workflow schedule refactor

**Files:**
- Modify: `tests/test_workflow_swing_automation.py`
- Modify: `.github/workflows/daily_sentinel.yml`

**Step 1: Write the failing tests**

Cover:
- workflow contains new `preclose` manual option
- cron slots are moved to `08:45`, `11:40`, `14:48`, `15:20`, `20:30` CST equivalents
- schedule resolver maps the new cron to `preclose`

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_workflow_swing_automation.py`

Expected: FAIL because the workflow still uses the old schedule and has no `preclose`.

**Step 3: Write minimal implementation**

Update:
- workflow cron expressions
- dispatch options
- mode resolution shell block

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_workflow_swing_automation.py`

Expected: PASS.

### Task 3: Wire `preclose` through application mode handling

**Files:**
- Modify: `src/main.py`
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/report_quality.py`
- Modify: `src/service/structured_report.py`
- Modify: `src/utils/trading_calendar.py`
- Modify: `src/reporter/telegram_client.py`
- Modify: `src/reporter/feishu_client.py`

**Step 1: Implement mode plumbing**

Add `preclose` to:
- CLI mode choices
- trading-calendar CLI choices
- analysis-service mode branches
- publish routing
- text/card rendering

**Step 2: Keep behavior scoped**

Rules:
- `preclose` reuses midday-style AI analysis
- `close` remains post-market review
- `swing` schedule moves to evening only in workflow, not strategy logic

**Step 3: Run targeted tests**

Run:
- `.venv/bin/python -m pytest -q tests/test_publish_target.py tests/test_report_quality.py tests/test_report_rendering_quality.py tests/test_structured_report.py tests/test_workflow_swing_automation.py`

Expected: PASS.

### Task 4: Final verification

**Files:**
- Modify as needed from regressions

**Step 1: Run the full suite**

Run: `.venv/bin/python -m pytest -q tests`

**Step 2: Inspect preclose CLI output**

Run:
- `.venv/bin/python -m src.main --mode preclose --dry-run`

Expected:
- mode accepted
- no parser error
- output title uses `收盘前执行` semantics

**Step 3: Commit**

```bash
git add .github/workflows/daily_sentinel.yml config.yaml docs/plans/2026-03-24-report-schedule-refactor-implementation.md src/main.py src/reporter/feishu_client.py src/reporter/telegram_client.py src/service/analysis_service.py src/service/report_quality.py src/service/structured_report.py src/utils/trading_calendar.py tests/test_publish_target.py tests/test_report_quality.py tests/test_report_rendering_quality.py tests/test_structured_report.py tests/test_workflow_swing_automation.py
git commit -m "feat: add preclose execution workflow"
git push origin main
```
