# Source Resilience Design

**Goal:** Reduce real-world report degradation frequency without sacrificing timeliness by fixing known collector failure patterns instead of only surfacing degradation more clearly.

## Problem

After the earlier degradation-state work, dry-run output showed the next bottleneck clearly:

- `fetch_market_breadth` often stopped at Tencent's placeholder string `N/A (Tencent)` and never reached later sources
- `fetch_news` stopped at empty strings from Tencent/Efinance, so ETF-heavy portfolios almost always showed `stock_news unavailable`
- `get_global_indices()` depended on a large global snapshot table that frequently timed out around 20 seconds
- `bulk_spot` was treated as quality-relevant even when per-symbol quotes succeeded and the report remained actionable

This produced too many `degraded` reports for reasons that were either false negatives or optional enrichment gaps.

## Product Principle

**Only degrade the report for missing data that materially reduces actionability.**

Missing optional enrichment should stay visible in block metadata, but it should not automatically poison overall quality.

## Recommended Approach

Keep the existing collector architecture, but harden the weak points:

1. Teach source fallback to skip placeholder results, not just `None`
2. Treat `bulk_spot` as optional once per-symbol quotes are available
3. Treat `stock_news` as optional for ETF-heavy portfolios
4. Replace morning global-index collection with a fast fallback chain:
   - try `ak.index_global_spot_em()` with a short timeout
   - fall back to per-index `ak.index_global_hist_em()` snapshots for the handful of indices actually used

## Why This Approach

### Option 1: Just increase timeouts

Rejected. It improves completeness a little but directly harms the user's stated preference: timely output.

### Option 2: Fix root-cause failure modes inside the collector

Recommended. It keeps the current design, improves real data yield, and reduces false degradation without hiding risk.

### Option 3: Replace data providers entirely

Rejected for now. Too much surface area for one iteration, and the collector already has enough structure to absorb targeted fixes.

## Design Details

### 1. Placeholder-Aware Fallback

`_fetch_with_fallback()` should continue past:

- empty strings
- empty dict/list values
- known placeholder strings such as `N/A (Tencent)` or `Market Breadth: N/A`

This preserves source priority while avoiding fake success.

### 2. Optional Block Semantics

`collection_status` should track optional blocks explicitly so `overall_status` only reflects non-optional failures.

Initial optional blocks:

- `bulk_spot`
- `stock_news` when the portfolio is ETF-heavy

These blocks still remain visible under `collection_status.blocks`.

### 3. ETF-Aware News Policy

For portfolios made entirely of ETF/fund-like symbols, per-symbol stock news is weak evidence and often unavailable. In that case:

- keep `stock_news` block metadata
- mark it missing if unavailable
- do not add a top-level issue
- do not let it degrade `overall_status`

### 4. Fast Global Index Fallback

For morning mode:

- try the big snapshot API first with a small timeout
- if it fails, fetch only the required indices:
  - `标普500`
  - `纳斯达克`
  - `道琼斯`
  - `恒生指数`
  - `美元指数`
  - `日经225`

`index_global_hist_em()` is fast enough for this targeted use and gives an overnight close suitable for morning context.

## Testing Strategy

Add coverage for:

- skipping placeholder market-breadth values
- skipping empty news values
- ETF-heavy portfolios staying `fresh` when only optional blocks are missing
- `get_global_indices()` falling back to per-index history snapshots

## Risks

- Optional-block rules could become too lenient if expanded carelessly
- ETF detection is heuristic and should stay narrow

These are acceptable because this iteration targets the current user workflow, which is dominated by ETF holdings.
