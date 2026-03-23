# Gemini GenAI Migration Design

**Context**

The project currently uses `google.generativeai`, which now emits an official deprecation warning during test runs and CLI execution. The report-quality work introduced deterministic `structured_report` payloads, but the Gemini client still relies on free-form prompt text plus best-effort JSON extraction.

**Goal**

Migrate the Gemini integration to the official `google.genai` SDK, reduce output-format fragility with API-level structured output, and preserve the existing report-generation flow and external interfaces.

**Chosen Approach**

Use a narrow migration:

1. Replace `google.generativeai` with `google.genai`.
2. Keep the current `GeminiClient` public methods unchanged.
3. For `midday`, `close`, and `morning`, call `client.models.generate_content(...)` with:
   - `response_mime_type="application/json"`
   - `response_schema=<existing Pydantic output model>`
4. Continue to validate locally with the existing Pydantic models so downstream behavior remains stable.
5. Keep Q&A as plain-text output without JSON schema.

**Why This Approach**

- Lowest-risk migration path: the rest of the pipeline does not need to know the SDK changed.
- Better accuracy: SDK-enforced structured output is more reliable than prompt-only JSON instructions.
- Better maintainability: removes dependency on a deprecated SDK and aligns code with current Google documentation.

**Prompt Strategy**

Once schema enforcement moves into the API config, prompt sections that restate full JSON skeletons become redundant and can degrade quality. The migration therefore trims the verbose JSON templates from the prompts and replaces them with concise output guidance.

**Testing Strategy**

- Add unit tests for the new SDK adapter behavior in `GeminiClient`.
- Verify schema path and fallback parsing path.
- Re-run existing report-quality and analysis service tests to ensure integration behavior is unchanged.
- Run full `pytest` and CLI `--replay --dry-run`.

**Non-Goals**

- No business-logic change to report quality gates.
- No redesign of prompt domain logic.
- No migration of trend/Q&A flows to tools or search grounding in this step.
