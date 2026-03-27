# Global Index Backup Design

**Goal:** Make morning reports more likely to receive usable overnight global-index context by adding an independent free public backup source for the six indices the report actually uses.

## Problem

The current morning global-index path depends on Eastmoney/AkShare endpoints:

- `ak.index_global_spot_em()` often times out or gets disconnected
- `ak.index_global_hist_em()` uses the same upstream family and can fail the same way
- after the previous resilience work, the system now reports this honestly as `degraded`, but data completeness is still too weak

This means the system is now semantically correct but still operationally fragile.

## Product Principle

**Prefer independent source diversity over repeated retries against the same failing upstream.**

If the primary source is unstable, the next fallback should use a different public provider rather than another wrapper around the same endpoint family.

## Options

### Option 1: Keep tuning Eastmoney-only timeouts and retries

Rejected. It improves symptoms at the margin but does not change the single-upstream failure pattern.

### Option 2: Add a Yahoo Finance backup for only the six required indices

Recommended. It is free, directly reachable from the current runtime, narrow in scope, and independent from Eastmoney.

### Option 3: Introduce a paid market-data API

Rejected for now. Better long-term stability, but it adds cost and credential management the user did not ask for in this iteration.

## Recommended Design

Extend `DataCollector.get_global_indices()` with a targeted merge strategy:

1. try `ak.index_global_spot_em()` first
2. normalize any indices returned by the primary source
3. detect which required targets are still missing
4. fetch only the missing targets from Yahoo Finance chart API
5. merge both result sets
6. let downstream quality logic decide:
   - `fresh` if 4 or more targets are present
   - `degraded` if 1 to 3 targets are present
   - `missing` if none are present

## Target Coverage

Only these indices matter for the morning report:

- `标普500` -> `^GSPC`
- `纳斯达克` -> `^IXIC`
- `道琼斯` -> `^DJI`
- `恒生指数` -> `^HSI`
- `美元指数` -> `DX-Y.NYB`
- `日经225` -> `^N225`

No generic global-index framework is needed in this step.

## Data Contract

Each normalized item remains:

- `name`
- `current`
- `change_pct`
- `change_amount`

Yahoo parsing should derive these from the latest two valid daily closes. If only one valid close exists, the item should be discarded.

## Error Handling

- primary-source failure should not block backup-source fetches
- backup-source failure for one symbol should not abort the rest
- logs should identify which symbols failed on backup
- merged results should preserve deterministic order matching the six target names

## Testing Strategy

Add tests proving:

- partial primary results are filled by Yahoo backup
- empty primary results can still produce complete Yahoo-backed output
- partial merged output still downgrades morning collection to `degraded`
- full merged output restores `global_indices` to `fresh`

## Risks

- Yahoo response schema could change
- some symbols may occasionally rate-limit or return sparse bars

These are acceptable because the backup is narrow and independent, and failure remains explicitly surfaced instead of hidden.
