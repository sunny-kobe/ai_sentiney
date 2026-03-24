# Preclose Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give `preclose` an independent prompt and analysis path so the report becomes a tail-end execution checklist while keeping the existing `MiddayAnalysis` schema and report pipeline.

**Architecture:** Add `prompts.preclose_focus` in config, implement `GeminiClient.analyze_preclose()` that reuses the current structured intraday schema, then route `AnalysisService.run_analysis(mode="preclose")` through that method. Keep post-processing, quality evaluation, and publishing unchanged.

**Tech Stack:** Python 3.11, pytest, Google GenAI SDK, YAML config, existing structured report pipeline

---

### Task 1: Add Failing Gemini Prompt Routing Tests

**Files:**
- Modify: `tests/test_gemini_client_genai.py`
- Modify: `src/analyst/gemini_client.py`

**Step 1: Write the failing test**

Add a regression test that:

- calls `analyze_preclose()`
- captures the prompt and schema passed into `generate_content`
- asserts schema is still `MiddayAnalysis`
- asserts prompt is `preclose_focus`, not `midday_focus`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_gemini_client_genai.py -k preclose`

Expected: FAIL because `analyze_preclose()` does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- a small shared helper for structured intraday analysis if useful
- `analyze_preclose()` using `prompts.preclose_focus`
- keep `analyze()` behavior unchanged

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_gemini_client_genai.py -k preclose`

Expected: PASS

### Task 2: Add Failing Service Routing Tests

**Files:**
- Modify: `tests/test_analysis_service_quality_flow.py`
- Modify: `src/service/analysis_service.py`

**Step 1: Write the failing test**

Add a regression test that:

- runs `AnalysisService.run_analysis(mode="preclose")`
- verifies `GeminiClient.analyze_preclose()` is called
- verifies `GeminiClient.analyze()` is not used for preclose
- confirms the structured report still reaches the analyst path

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py -k preclose`

Expected: FAIL because the service still routes `preclose` through `analyze()`.

**Step 3: Write minimal implementation**

Change the service branch to:

- keep `midday` on `analyze()`
- route `preclose` to `analyze_preclose()`
- keep `yesterday_context` injection for both

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_quality_flow.py -k preclose`

Expected: PASS

### Task 3: Add Preclose Prompt Config

**Files:**
- Modify: `config.yaml`

**Step 1: Add config entry**

Add `prompts.preclose_focus`.

Prompt requirements:

- action-first wording
- classify holdings by tail-end execution decision
- require ratio ranges or explicit no-action
- require invalidation conditions
- reduce jargon and avoid verbose midday commentary

**Step 2: Verify config usage**

Run: `rg -n "preclose_focus" config.yaml src/analyst/gemini_client.py src/service/analysis_service.py tests`

Expected: prompt key is referenced by config, client, and tests.

### Task 4: Run Targeted Verification

**Files:**
- Modify as needed by regressions

**Step 1: Run targeted tests**

Run: `.venv/bin/python -m pytest -q tests/test_gemini_client_genai.py tests/test_analysis_service_quality_flow.py`

Expected: PASS

**Step 2: Run a local preclose replay**

Run: `.venv/bin/python -m src.main --mode preclose --replay --dry-run`

Expected:

- command exits successfully
- output includes `=== 收盘前执行 ===`
- no prompt-routing errors appear

### Task 5: Final Verification And Ship

**Files:**
- Modify as required by regressions

**Step 1: Run full suite**

Run: `.venv/bin/python -m pytest -q tests`

Expected: PASS

**Step 2: Commit and push**

```bash
git add docs/plans/2026-03-24-preclose-prompt-design.md docs/plans/2026-03-24-preclose-prompt-implementation.md config.yaml src/analyst/gemini_client.py src/service/analysis_service.py tests/test_gemini_client_genai.py tests/test_analysis_service_quality_flow.py
git commit -m "feat: add dedicated preclose prompt"
git push origin main
```
