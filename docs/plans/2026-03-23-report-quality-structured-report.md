# Report Quality And Structured Report Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **Follow-up alignment (2026-04-09):**
> The quality/rendering flow now treats quote freshness as part of the display contract for intraday reports. `midday` / `preclose` suppress `pct_change_str` and realtime price when `quote_status != fresh`, and signal scorecards skip those symbols instead of counting them as `0.0%`.

**Goal:** Build quality gates and a structured, evidence-backed report flow for `midday` and `close`, plus add a project skill that standardizes daily report generation.

**Architecture:** Add a pre/post quality-gate layer around the existing analysis pipeline and generate a deterministic `structured_report` from processor outputs and collected evidence before any LLM narration. Keep Gemini only for narrative enrichment in `normal` mode, degrade to a structured technical brief when gates fail or AI output is incomplete, and preserve quote freshness metadata so downstream intraday renderers can avoid fake realtime display.

**Tech Stack:** Python 3, pytest, sqlite3, existing AkShare/Gemini pipeline, Feishu/Telegram renderers, Markdown skill docs

---

### Task 1: Add Report Quality Gate Module

**Files:**
- Create: `src/service/report_quality.py`
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_report_quality.py`

**Step 1: Write the failing test**

Cover:
- `blocked` for missing critical market/stock data
- `degraded` for missing evidence / stale context
- `normal` when required fields are present

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_report_quality.py`

Expected: FAIL because module/functions do not exist.

**Step 3: Write minimal implementation**

Implement:
- `evaluate_input_quality(ai_input, mode)`
- `evaluate_output_quality(analysis_result, structured_report, mode)`
- stable status enum values: `normal`, `degraded`, `blocked`

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_report_quality.py`

Expected: PASS

### Task 2: Build Structured Report Layer

**Files:**
- Create: `src/service/structured_report.py`
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_structured_report.py`

**Step 1: Write the failing test**

Cover:
- `structured_report` includes market section, stock entries, source labels, timestamps
- per-stock entry uses processor `signal/confidence/tech_summary`
- `midday` and `close` both produce deterministic stock payloads

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_structured_report.py`

Expected: FAIL because module/functions do not exist.

**Step 3: Write minimal implementation**

Implement:
- `build_structured_report(ai_input, mode, quality_status)`
- deterministic `operation` mapping from signal
- light evidence fields: `tech_evidence`, `news_evidence`, `source_labels`, `data_timestamp`

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_structured_report.py`

Expected: PASS

### Task 3: Route Analysis Through Quality Gates

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/analyst/gemini_client.py`
- Test: `tests/test_analysis_service_quality_flow.py`

**Step 1: Write the failing test**

Cover:
- blocked input returns skip/error-style response without AI call
- degraded input returns structured report without AI call
- normal input calls Gemini and preserves structured report + quality metadata

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py`

Expected: FAIL because flow is not implemented.

**Step 3: Write minimal implementation**

Implement:
- input gate before AI call
- `structured_report` generation for all `midday/close`
- AI reads `structured_report` instead of raw free-form context for normal mode
- degraded mode bypasses Gemini and emits structured brief

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py`

Expected: PASS

### Task 4: Render Quality Metadata In Channels

**Files:**
- Modify: `src/main.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`
- Test: `tests/test_report_rendering_quality.py`

**Step 1: Write the failing test**

Cover:
- degraded reports show degradation label
- structured evidence/source labels appear in rendered content
- timestamps/quality status are visible in text output and Feishu card

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_report_rendering_quality.py`

Expected: FAIL because renderers do not display new metadata yet.

**Step 3: Write minimal implementation**

Implement:
- CLI text summary support for quality state and evidence labels
- Feishu/Telegram sections for `quality_status`, `data_timestamp`, `source_labels`
- degraded footer/title treatment

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_report_rendering_quality.py`

Expected: PASS

### Task 5: Add Project Skill For Daily Report Generation

**Files:**
- Create: `skills/sentinel-daily-report/SKILL.md`
- Test: `tests/test_project_skill_files.py`

**Step 1: Write the failing test**

Cover:
- skill file exists
- skill content mentions preflight checks, degraded fallback, verification commands

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_project_skill_files.py`

Expected: FAIL because skill file does not exist.

**Step 3: Write minimal implementation**

Implement a project-local skill describing:
- when to generate/publish
- required preflight checks
- structured report expectations
- degraded/blocked handling
- verification commands

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_project_skill_files.py`

Expected: PASS

### Task 6: Full Regression And CLI Verification

**Files:**
- Modify as needed based on regressions

**Step 1: Run targeted suites**

Run:
- `../../.venv/bin/python -m pytest -q tests/test_report_quality.py tests/test_structured_report.py tests/test_analysis_service_quality_flow.py tests/test_report_rendering_quality.py tests/test_project_skill_files.py`

**Step 2: Run broader regression**

Run:
- `../../.venv/bin/python -m pytest -q tests`

**Step 3: Run CLI verification**

Run:
- `../../.venv/bin/python -m src.main --mode midday --replay --dry-run`

Expected:
- exit code 0
- visible quality metadata or degraded structured output

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-report-quality-structured-report.md src/service/report_quality.py src/service/structured_report.py src/service/analysis_service.py src/analyst/gemini_client.py src/main.py src/reporter/feishu_client.py src/reporter/telegram_client.py skills/sentinel-daily-report/SKILL.md tests/test_report_quality.py tests/test_structured_report.py tests/test_analysis_service_quality_flow.py tests/test_report_rendering_quality.py tests/test_project_skill_files.py
git commit -m "feat: add quality-gated structured report flow"
```
