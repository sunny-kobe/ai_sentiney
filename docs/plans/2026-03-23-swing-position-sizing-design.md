# Swing Position Sizing Design

**Date:** 2026-03-23

## Goal

Extend `swing` from direction guidance into actionable portfolio sizing.

The report should no longer stop at:

- `增配`
- `持有`
- `减配`
- `回避`
- `观察`

It should also answer:

1. This week, how much total market exposure should the user keep?
2. How much belongs in `核心仓`, `卫星仓`, and `现金`?
3. Within those buckets, which holdings deserve the weight?
4. What changes only once a week, and what can be cut daily for risk control?

## Why This Is The Right Next Step

The recent work already improved medium-term direction:

- benchmark-relative strength is in the scoring path
- retreat rules are stronger during sharp selloffs
- the report is readable enough for real use

The missing layer is execution discipline.

Without explicit sizing, the user still has to translate a report into portfolio action by feel. That is exactly where medium-term systems degrade into inconsistent behavior.

## Strategy Frame

The sizing layer should stay consistent with the product's current philosophy:

- medium-term entry
- faster exit
- portfolio-first decisions
- deterministic and testable rules

It should not become a mini optimizer or a daily trading engine.

## Recommended Approach

Use a **three-layer portfolio model**:

- `核心仓`
- `卫星仓`
- `现金`

And combine it with **weekly rebalancing plus daily risk-only reductions**.

### Why This Approach

It captures the right balance:

- more actionable than plain-language recommendations
- simpler and more robust than full optimization
- aligned with the user's preference for medium-term positioning rather than daily tactical trading

## Regime Templates

Each market regime maps to a target exposure template.

### `进攻`

- total exposure: `90%-100%`
- core: `50%-60%`
- satellite: `30%-40%`
- cash: `0%-10%`

### `均衡`

- total exposure: `65%-80%`
- core: `40%-50%`
- satellite: `15%-25%`
- cash: `20%-35%`

### `防守`

- total exposure: `35%-55%`
- core: `20%-35%`
- satellite: `0%-10%`
- cash: `45%-65%`

### `撤退`

- total exposure: `0%-20%`
- core: `0%-15%`
- satellite: `0%`
- cash: `80%-100%`

These are templates, not obligations. If there are not enough qualified holdings, the remaining budget stays in `现金`.

## Bucket Assignment

### Core Bucket

`核心仓` should hold the most stable and reliable exposures:

- broad-beta ETFs
- non-high-beta sector ETFs with stable relative strength
- optional defensive asset proxies if they remain strong

Core candidates must usually be:

- `增配` or `持有`
- not in a stressed high-beta cluster
- not showing deep drawdown or structural breakdown

### Satellite Bucket

`卫星仓` should hold aggressive or more fragile exposures:

- AI
- semiconductor
- small-cap
- single-name equity risk
- lower-conviction observations

Satellite gets the first cut when risk rises.

### Cash

`现金` is not a leftover. It is the main safety valve.

If the system cannot find enough qualified candidates, cash rises automatically.
If the regime flips weaker, satellite is cut first and cash rises.

## Weight Assignment

Within `核心仓` and `卫星仓`, allocation should be deterministic:

1. start from regime bucket budgets
2. rank holdings by existing `swing` score and action label
3. allocate more to `增配`, then `持有`
4. cap `观察` and `减配` at small weights
5. `回避` gets `0%`

This preserves relative-strength information while preventing weak positions from consuming real portfolio budget.

### Practical Caps

- `核心仓` strong names can carry larger weights
- `卫星仓` names are smaller by design
- `观察` stays as a probe position only
- `减配` becomes a residual position only

Unused budget rolls back into `现金`.

## Execution Rules

### Weekly Rebalance

Main sizing changes happen once a week:

- generate the plan after Friday close
- execute on the next trading day
- resize positions in batches, not all at once

This is the main anti-short-term safeguard.

### Daily Risk Control

Daily changes are allowed only on the defensive side:

- cut satellite when risk lines break
- reduce or exit weak positions on structure breaks
- do not add new risk intraday or on non-rebalance days

The system should explicitly say:

- `本周主调仓`
- `日级只减不加`

## Report Changes

The `swing` report should add a dedicated `仓位计划` section.

It should show:

- target total exposure
- core / satellite / cash ranges
- weekly execution rhythm
- daily risk rule

Each holding line should also show:

- bucket: `核心仓` or `卫星仓`
- target weight range

This makes the report immediately executable.

## Files To Extend

- `src/service/swing_strategy.py`
  add position templates, bucket assignment, weight allocation, plan summary
- `src/main.py`
  print `仓位计划` and per-holding target weights in CLI
- `src/reporter/feishu_client.py`
  add position-plan section to Feishu card
- `src/reporter/telegram_client.py`
  add compact position-plan section to Telegram text
- tests for strategy and rendering

## Review Notes

This design deliberately avoids:

- mean-variance optimization
- covariance estimation
- daily full rebalancing
- overfitted numeric precision

That is intentional.

For the current project, the main value is consistency and execution clarity, not theoretical optimality.
