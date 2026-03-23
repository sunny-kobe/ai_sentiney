# Swing Strategy Redesign

**Date:** 2026-03-23

## Why This Redesign

The current system is optimized around short-horizon follow-up:

- signal evaluation is dominated by `T+1` price change
- the scorecard focuses on `7-day` / `30-day` hit rate
- midday and close reports still read like short-term trading diagnostics
- output is heavy on indicator jargon and light on portfolio-level action

This is misaligned with the user's actual edge. The user does not want to compete with intraday or ultra-short-term quantitative strategies. The product should instead optimize for medium-term holding decisions and timely risk reduction when the market environment breaks.

## Design Goal

Add a new `swing` mode that becomes the primary decision surface for `2-8 week` positioning, while keeping `midday` / `close` as tactical market diagnostics.

The redesigned system must answer four portfolio questions clearly:

1. Is the market environment suitable for risk-on exposure?
2. Which directions are strongest on a medium-term basis?
3. Which holdings should be increased, held, reduced, or avoided?
4. When should the system exit early because the market or structure has broken?

## Principles

### 1. Medium-Term Entry, Faster Exit

The new system should enter slowly and exit faster.

- entry decisions should rely on medium-term trend and relative strength confirmation
- exit decisions may use daily risk triggers and structural breakdown confirmation

This avoids turning the system into a short-term predictor while preserving timely defense in sharp drawdowns.

### 2. Strategy Layering

The system should separate:

- **strategic layer**: medium-term trend and rotation
- **tactical layer**: daily deterioration / repair diagnostics
- **risk layer**: emergency de-risking rules

This is the key design change. The old system lets one short-horizon signal structure do everything. The new system assigns different jobs to different layers.

### 3. Portfolio First, Single-Name Second

The output should optimize the portfolio, not just classify each symbol independently.

- ETF and broad-beta exposures should drive the core decision
- high-volatility single names should be treated as satellite risk
- the system should detect clustered exposure, not just per-symbol weakness

## Research-Informed Strategy Frame

The strategy frame combines three external schools:

### A. Medium-Term Trend / Dual Momentum

Use the core ideas from trend-following and dual momentum:

- only take risk when the broad market regime is supportive
- among investable assets, prefer the strongest relative performers
- keep rebalancing low frequency (weekly / bi-weekly), not intraday

This is the main engine because it matches ETF rotation and personal-investor execution constraints.

### B. Quality / Low-Volatility Constraint

Use factor-style constraints to stop the portfolio from overconcentrating in high-beta themes:

- avoid concentrating entirely in small caps, AI, semis, or precious metals
- penalize excessive recent volatility and unstable drawdown profiles
- keep a core-risk framework around broad ETFs and more stable exposures

This prevents the strategy from becoming disguised short-term speculation.

### C. Chan-Theory-Inspired Tactical Exit Overlay

Use Chan-style concepts selectively, especially for exit confirmation:

- structural breakdown
- failed rebound / weak retrace
- divergence as a caution signal, not as a stand-alone buy trigger

Chan theory should not become the primary signal engine. It is most useful here as a tactical override and structural warning layer.

## New Strategy Architecture

### 1. Primary Mode: `swing`

Add a new analysis mode: `swing`.

This becomes the default decision report for the user.

It should produce medium-term portfolio guidance:

- `增配`
- `持有`
- `减配`
- `回避`
- `观察`

These labels are intentionally plain-language and portfolio-oriented.

### 2. Secondary Modes: `midday` / `close`

Keep existing intraday and close workflows, but narrow their purpose:

- diagnose whether the market is worsening or repairing
- detect tactical pressure or relief
- provide same-day context to support risk overlays

These modes should stop pretending to be the primary forecasting surface.

## Core Decision Engine

Each symbol or ETF should receive a medium-term composite score from four buckets.

### A. Trend Score

Questions:

- is price above key medium-term references such as `MA20` and `MA60`?
- are medium-term moving averages sloping up or down?
- is the symbol making higher lows / higher highs over the recent `20-40` trading days?

### B. Relative Strength Score

Questions:

- is the symbol outperforming its relevant benchmark over `20` and `40` trading days?
- is it strengthening relative to broad market alternatives?
- within the ETF pool, is it in the top strength cluster or bottom cluster?

This should become a major ranking input because medium-term outperformance is more useful than next-day prediction.

### C. Risk Score

Questions:

- what is the recent `20-day` maximum drawdown?
- did the symbol break a medium-term trend line or support area with volume?
- is realized volatility rising sharply?

This score should heavily influence exit and position sizing.

### D. Catalyst / News Adjustment

News should no longer dominate signals.

Instead, news should:

- upgrade or downgrade confidence
- confirm or question existing direction
- trigger faster review when paired with technical deterioration

The system should not turn one headline into a full directional flip.

## Market Regime Filter

The market layer should determine whether the strategy is allowed to take aggressive exposure at all.

Suggested states:

- `进攻`
- `均衡`
- `防守`
- `撤退`

These states should depend on:

- broad index medium-term trend
- market breadth deterioration / repair
- concentration of weakness in small caps / growth / thematic clusters

This regime filter should gate portfolio recommendations.

## Emergency Risk Overlay

This is the most important addition for the user's actual need: timely withdrawal during sharp market deterioration.

The overlay should support de-risking even when the medium-term engine has not yet fully flipped.

### Trigger Families

#### 1. Market Trigger

- broad index breaks medium-term structure
- breadth collapses
- correlated risk assets fall together

#### 2. Cluster Trigger

Group holdings by risk cluster:

- broad beta
- small caps
- AI / semiconductors
- precious metals / miners
- individual high-volatility names

If one cluster breaks together, reduce the whole cluster instead of waiting for each symbol individually.

#### 3. Price / Structure Trigger

- accelerated downside with volume
- failed rebound
- repeated weakness vs benchmark

#### 4. News Confirmation Trigger

Bad news alone is not enough.

But `bad news + price breakdown + relative weakness` should force faster reduction.

### Exit Style

Exits should be staged, not binary:

- reduce one-third
- reduce to half
- leave observation position only

This gives flexibility without requiring perfect timing.

## New Evaluation Framework

The old `T+1 hit rate` should no longer be the main KPI.

### New Forward Windows

Track forward outcomes at:

- `10 trading days`
- `20 trading days`
- `40 trading days`

### New Scorecard Dimensions

For each decision class:

- directional correctness
- positive-return rate
- benchmark-relative outperformance
- maximum drawdown
- high-confidence subset performance

### What To Emphasize

The best system report should answer:

- do `增配` names outperform over `20/40` days?
- do `回避` names underperform or suffer larger drawdowns?
- does the system help the portfolio lose less in bad regimes?

This is more meaningful than whether it guessed tomorrow correctly.

## Output Redesign

The current output is too close to a quant desk diagnostic dump.

The new `swing` report should be human-readable and action-first.

### Report Structure

1. **市场结论**
   - Is the environment risk-on or defensive?

2. **组合动作**
   - Which groups to increase, hold, reduce, avoid?

3. **持仓清单**
   - for each holding:
     - `结论`
     - `原因`
     - `计划`
     - `风险线`

4. **技术证据**
   - optional / last section
   - translate indicator bundles into plain language summaries

### Language Rules

- no dense jargon in the main body
- indicator tags belong in evidence, not in the headline recommendation
- every recommendation must include:
  - what to do
  - why
  - what would invalidate the view

## Portfolio Construction Guidance

The system should encourage a three-bucket structure:

- **核心仓**: broad ETFs, lower-volatility trend exposures
- **卫星仓**: higher-beta thematic ETFs and selective names
- **回避仓 / 观察仓**: broken or unstable exposures

This directly supports the user's need to survive fast drawdowns without trying to trade every intraday fluctuation.

## Migration Strategy

### Phase 1

- add `swing` mode
- add medium-term score model
- add forward `10/20/40` evaluation
- add plain-language output template

### Phase 2

- add cluster-aware de-risk overlay
- add core / satellite / avoid grouping
- add benchmark-relative statistics

### Phase 3

- refine tactical structure logic with Chan-style breakdown / failed-rebound checks
- consider weekly rebalancing summaries and regime dashboard

## Expected Outcome

After redesign, the project should no longer behave like a weak short-term predictor.

It should behave like a medium-term portfolio management assistant:

- slower to add risk
- faster to cut broken exposure
- clearer in communication
- judged by medium-term portfolio outcomes rather than next-day noise
