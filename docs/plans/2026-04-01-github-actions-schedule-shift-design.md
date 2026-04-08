# GitHub Actions Schedule Shift Design

**Goal:** Adjust only the formal GitHub Actions delivery times for `morning`, `midday`, `preclose`, and `close` without changing runtime behavior outside the workflow.

## Scope

This change is intentionally narrow. It updates the scheduled trigger times in the GitHub Actions workflow and keeps the workflow's schedule-to-mode routing aligned with those new cron expressions.

Included:
- `.github/workflows/daily_sentinel.yml` cron entries
- `.github/workflows/daily_sentinel.yml` `SCHEDULE_EXPR` to `TARGET_MODE` mapping
- workflow regression tests that assert the cron strings

Excluded:
- local cron helper scripts
- Python runtime logic
- fallback current-time routing thresholds
- report content or publish channels

## Target Beijing Times

- `morning`: delay by 3 hours, `04:10` -> `07:10`
- `midday`: move earlier by 1.5 hours, `11:20` -> `09:50`
- `preclose`: move earlier by 1.5 hours, `14:35` -> `13:05`
- `close`: move earlier by 0.5 hour, `15:05` -> `14:35`
- `swing`: unchanged at `20:00`

## UTC Conversion

GitHub Actions cron uses UTC. With `Asia/Shanghai` fixed at UTC+8:

- `morning` `07:10 CST` -> `23:10 UTC` on the previous day
- `midday` `09:50 CST` -> `01:50 UTC`
- `preclose` `13:05 CST` -> `05:05 UTC`
- `close` `14:35 CST` -> `06:35 UTC`
- `swing` `20:00 CST` -> `12:00 UTC`

## Recommended Approach

Update both layers in the workflow:

1. The `on.schedule` cron definitions
2. The explicit `case "$SCHEDULE_EXPR"` routing table

This is the safest approach because scheduled runs depend on an exact string match. Changing only the cron list would cause scheduled runs to resolve to the wrong mode.

## Testing

Use existing workflow regression tests as the primary safety net:

- update cron string assertions first
- run the workflow test file and confirm it fails before production edits
- update the workflow file minimally
- rerun the same tests and confirm green

## Risks

- If the cron strings and the `case` strings diverge, scheduled runs will misroute.
- The fallback current-time logic will remain inconsistent with the new schedule windows, but that path is intentionally out of scope for this change.

## Decision

Implement the narrow workflow-only change and leave fallback time heuristics untouched.
