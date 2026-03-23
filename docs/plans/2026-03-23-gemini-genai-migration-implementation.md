# Gemini GenAI Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the deprecated Gemini SDK with `google.genai`, enforce structured output at the API layer, and keep existing report generation behavior stable.

**Architecture:** Preserve `GeminiClient`'s public surface while replacing the internal transport with `google.genai.Client`. Midday, close, and morning analysis calls will use JSON structured output with Pydantic schemas; Q&A remains free-form text. Prompt JSON skeletons will be reduced to avoid conflicting with API-level schema enforcement.

**Tech Stack:** Python 3, pytest, pydantic v2, google-genai SDK, existing AnalysisService/report-quality pipeline

---

### Task 1: Add Gemini SDK Migration Tests

**Files:**
- Create: `tests/test_gemini_client_genai.py`

**Step 1: Write the failing tests**

Cover:
- client initialization uses `google.genai.Client`
- midday analysis passes JSON response config and returns parsed structured data
- fallback path still parses JSON text when parsed payload is unavailable
- Q&A returns plain text

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_gemini_client_genai.py`

Expected: FAIL because the SDK and call flow have not been migrated yet.

### Task 2: Migrate Gemini Client To google.genai

**Files:**
- Modify: `src/analyst/gemini_client.py`
- Modify: `requirements.txt`
- Modify: `requirements.lock`

**Step 1: Write minimal implementation**

Implement:
- `from google import genai`
- `from google.genai import types`
- client initialization via `genai.Client(api_key=...)`
- helper for schema-based `generate_content`
- helper for text-only `generate_content`
- retain local Pydantic validation and fallback JSON extraction

**Step 2: Run tests**

Run: `../../.venv/bin/python -m pytest -q tests/test_gemini_client_genai.py`

Expected: PASS

### Task 3: Trim Prompt JSON Skeletons

**Files:**
- Modify: `config.yaml`

**Step 1: Update prompts**

Reduce verbose JSON template sections in:
- `midday_focus`
- `close_review`
- `morning_brief`

Keep semantic field guidance, but remove full schema duplication and code-block-style JSON examples.

**Step 2: Run focused regression**

Run: `../../.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py tests/test_report_rendering_quality.py tests/test_analysis_service_replay.py`

Expected: PASS

### Task 4: Full Regression And CLI Verification

**Files:**
- Modify as needed based on regressions

**Step 1: Run report-related targeted suites**

Run:
- `../../.venv/bin/python -m pytest -q tests/test_gemini_client_genai.py tests/test_report_quality.py tests/test_structured_report.py tests/test_analysis_service_quality_flow.py tests/test_report_rendering_quality.py tests/test_project_skill_files.py tests/test_analysis_service_replay.py tests/test_publish_target.py`

**Step 2: Run full test suite**

Run:
- `../../.venv/bin/python -m pytest -q tests`

**Step 3: Run CLI verification**

Run:
- `../../.venv/bin/python -m src.main --mode midday --replay --dry-run`

Expected:
- exit code 0
- no deprecated Gemini SDK warning

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-gemini-genai-migration-design.md docs/plans/2026-03-23-gemini-genai-migration-implementation.md requirements.txt requirements.lock config.yaml src/analyst/gemini_client.py tests/test_gemini_client_genai.py
git commit -m "refactor: migrate gemini client to google genai"
```
