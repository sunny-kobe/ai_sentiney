# Data Stability Design

**Goal:** Make all report modes (`morning`, `midday`, `preclose`, `close`, `swing`) produce timely output even when some market-data sources are slow or failing, while exposing clear freshness/degradation signals to downstream quality checks and reports.

## Problem

The current collector treats many data fetches similarly even though their value and urgency differ:

- bulk spot data can block before per-symbol quotes start
- macro news / north funds / breadth can consume the same event-loop budget as core holdings data
- fallback success is not captured as structured state
- downstream quality logic only sees coarse symptoms like missing stocks or missing evidence

This creates two bad outcomes:

1. report generation can be delayed by low-priority sources
2. reports may look "normal" even when key inputs were partially degraded

## Product Principle

**Timeliness wins over completeness.**

If the system can produce a useful report with degraded non-core data, it should do that and surface the degradation explicitly. It should not block the whole report waiting for low-priority enrichment.

## Recommended Approach

Introduce a shared collection-state layer inside `DataCollector`:

- classify fetches into `core`, `supporting`, and `optional`
- assign per-operation time budgets
- track structured status for each data block: `fresh`, `degraded`, `missing`
- let bulk spot fail fast and immediately continue with per-symbol quote fallback
- propagate collection issues into the AI input payload so all modes share the same quality semantics

This keeps the current architecture intact while adding a scheduling and observability layer around it.

## Data Priorities

### Core

Needed for the report to remain actionable:

- per-symbol real-time quotes for portfolio / universe
- historical prices for indicator calculation
- minimal stock list

If these fail badly, intraday modes may need to downgrade to `blocked`.

### Supporting

Useful for confidence and context, but not worth blocking the report:

- market breadth
- major indices
- northbound funds
- macro news
- overnight global/commodity/treasury data for morning mode

These should degrade independently without preventing report output.

### Optional

High-latency enrichment that can be skipped without breaking actionability:

- stock news when already enough technical context exists
- bulk spot fetch when single-quote fallback can cover the portfolio

## Design Details

### 1. Structured Collection Status

Return `collection_status` from collector entrypoints:

- `overall_status`
- `blocks`
  - `bulk_spot`
  - `market_breadth`
  - `north_funds`
  - `indices`
  - `macro_news`
  - `global_indices`
  - `commodities`
  - `us_treasury`
  - `stock_quotes`
  - `stock_history`
  - `stock_news`
- `issues`
- `source_labels`

Each block includes:

- `status`: `fresh | degraded | missing`
- `source`
- `detail`

### 2. Per-Operation Time Budgets

Use smaller budgets for blocking operations that have cheaper fallback paths:

- bulk spot: short timeout
- single quote: short timeout, high priority
- history: moderate timeout
- macro / global context: medium timeout, degradable

This replaces the accidental "one size fits all" behavior.

### 3. Fast Degradation Path

If bulk spot fails:

- mark `bulk_spot=missing`
- immediately continue to per-symbol quotes
- mark `stock_quotes=fresh` if quote fallback fills enough names

If macro/news fails:

- keep the report moving
- mark the corresponding block degraded
- push issue text into `data_issues`

### 4. Quality Propagation

Collector outputs feed downstream quality checks:

- `AnalysisService.collect_and_process_data()` and `collect_and_process_morning_data()` copy `data_issues`, `collection_status`, `source_labels`
- `evaluate_input_quality()` uses collection-state hints, not just missing stocks/news
- `build_structured_report()` includes top-level collection issues and source labels

### 5. Morning Mode

Morning mode must use the same stability model:

- global indices, commodities, treasury, macro news are all degradable
- stock historical context remains core

This avoids morning mode drifting into a separate reliability model.

## Testing Strategy

Add tests for:

- bulk spot failure with successful single-quote fallback still yields usable stocks
- supporting data failures mark degraded state without blocking collection
- morning mode returns `collection_status` and `data_issues`
- quality evaluation downgrades appropriately when supporting data is degraded

## Risks

- More status plumbing increases payload size slightly
- Quality rules may need tuning to avoid over-degrading reports

These are acceptable because reliability and explicitness are more important than keeping the payload minimal.

## Out of Scope

- Replacing third-party data providers
- Adding persistent cache infrastructure
- Rewriting report-generation prompts or strategy logic
