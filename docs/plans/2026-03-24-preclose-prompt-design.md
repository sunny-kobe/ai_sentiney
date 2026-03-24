# Preclose Prompt Design

**Date:** 2026-03-24

## Goal

Make `preclose` produce a true tail-end execution checklist instead of reusing the generic `midday` intraday analysis.

The report should stay concise and action-first:

- who to trim first
- who to keep through the close
- who not to touch today
- what add/trim ratio is suggested
- what condition invalidates the plan

## Current Failure

`preclose` is already wired in workflow, CLI rendering, Telegram, and Feishu, but the analysis behavior is still not independent.

Current code path:

1. `AnalysisService.run_analysis(mode="preclose")` routes into the same branch as `midday`
2. `GeminiClient.analyze()` always uses `prompts.midday_focus`
3. both modes therefore share the same prompt and same reasoning style

This means the output is often still a midday-style explanation instead of a late-session execution plan.

## Constraints

- keep existing `MiddayAnalysis` schema
- do not add a new renderer unless behavior proves insufficient
- keep current `preclose` publishing, scheduling, and report quality flow intact
- make the change minimal and regression-safe

## Recommended Approach

Add a dedicated `prompts.preclose_focus` and a dedicated `GeminiClient.analyze_preclose()` method.

The new method should:

- reuse the same structured `MiddayAnalysis` response schema
- reuse the same context construction and response validation
- change only the system prompt and the service routing

`AnalysisService.run_analysis()` should then split `midday` and `preclose` into separate branches:

- `midday` keeps calling `analyze()`
- `preclose` calls `analyze_preclose()`

## Why This Approach

This is the smallest change that fixes the real problem.

It avoids:

- duplicating post-processing
- introducing a new report format
- expanding renderer complexity
- breaking existing `preclose` cards and text templates

The behavior changes where it should change: prompt intent and analysis entrypoint.

## Prompt Direction

`preclose_focus` should explicitly force late-session execution language.

Core guidance:

- do not write a broad midday market essay
- prioritize executable instructions over terminology
- every action must include suggested ratio or "不动"
- every directional call must include an invalidation condition
- classify holdings into keep / trim / avoid touching / optional add
- treat the report as a last 10-15 minute action list before the close

## Testing Strategy

Add regression coverage for both layers:

1. `GeminiClient`
   - `analyze()` still uses `midday_focus` + `MiddayAnalysis`
   - `analyze_preclose()` uses `preclose_focus` + `MiddayAnalysis`

2. `AnalysisService`
   - `mode="preclose"` calls the dedicated preclose analysis path
   - `mode="midday"` still uses the midday path
   - structured report and quality flow remain unchanged

## Files To Modify

- `config.yaml`
- `src/analyst/gemini_client.py`
- `src/service/analysis_service.py`
- `tests/test_gemini_client_genai.py`
- `tests/test_analysis_service_quality_flow.py`

## Non-Goals

This design does not:

- create a new `PrecloseAnalysis` schema
- redesign Feishu or Telegram rendering
- change `close` or `midday` behavior beyond routing separation
- solve all report-style issues in one pass

It is specifically a prompt-intent refactor for `preclose`.
