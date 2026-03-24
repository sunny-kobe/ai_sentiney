# Swing Automation And Delivery Design

**Date:** 2026-03-24

## Goal

Make `swing` usable as the default delivery surface without requiring manual CLI usage.

The user should be able to:

- receive scheduled `swing` pushes automatically
- manually trigger a GitHub Action run and choose `swing`
- keep the repository test suite green

## Scope

This change should cover three things only:

1. add scheduled `swing` delivery to GitHub Actions
2. add manual workflow inputs so `swing` can be selected from the Actions UI
3. fix the currently failing quality-flow regression so full verification is green again

## Delivery Model

The project already knows how to publish `swing` to:

- Feishu
- Telegram

The missing layer is scheduling. The existing workflow only auto-runs `morning`, `midday`, and `close`.

## Recommended Workflow Shape

Use one workflow with:

- existing fallback schedules for `morning`, `midday`, `close`
- one additional close-adjacent schedule for `swing`
- manual `workflow_dispatch` input for `mode`
- manual `workflow_dispatch` input for `publish_target`

This keeps operations simple and avoids splitting delivery logic across multiple workflows.

## Manual Trigger Behavior

Recommended manual options:

- `swing`
- `morning`
- `midday`
- `close`
- `auto`

Default manual mode should be `swing`, because it is now the main user-facing strategy report.

## Scheduled Behavior

Scheduled runs should stay deterministic:

- if the cron matches the `swing` slot, run `swing`
- otherwise keep existing morning / midday / close mapping

Do not depend on vague current-hour logic alone once `swing` is added, because `close` and `swing` are both near the same UTC window.

## Test Fix

The current failing regression is not a product bug in `midday`; it is a stale test assumption.

The test hardcodes a `context_date` that no longer matches the current day, so input quality now correctly marks it as `degraded`.

The fix should make the test date dynamic rather than weakening production quality checks.
