# Swing Benchmark And Retreat Upgrade

**Date:** 2026-03-23

## Context

The current `swing` mode already moved the project away from short-term hit-rate framing, but two weak spots remain:

- symbol evaluation still depends too much on local indicator state and not enough on benchmark-relative strength
- the emergency exit layer is too soft during sharp selloffs, bad-news shocks, or cluster-wide breakdowns

This creates the wrong failure mode: the report becomes easier to read, but not sufficiently better at deciding when to stay in strong assets and when to leave broken ones.

## Goal

Upgrade `swing` from a plain-language rule report into a medium-term allocation engine with:

- cluster-aware benchmark mapping
- benchmark-relative strength and drawdown scoring
- staged retreat rules for sharp downside and bad-news confirmation
- clearer scorecard output that explains why a direction stays in the portfolio

## Design Principles

### 1. Relative Strength Must Affect Decisions, Not Just Evaluation

The project already computes medium-term evaluation windows. The next step is to use the same philosophy in the decision engine itself.

Each holding should be judged against an appropriate benchmark, not only against its own moving-average position:

- broad beta vs broad market benchmark
- small-cap risk vs small-cap benchmark with large-cap fallback
- AI / semiconductor risk vs thematic benchmark with broad-market fallback
- precious metals and generic sector ETFs vs broad beta fallback when no better proxy exists

This follows mature trend / dual-momentum practice: first decide whether the market allows risk, then allocate within the relative winners.

### 2. Exit Faster Than Entry

The system should still enter with medium-term confirmation, but exits should accelerate when multiple bad conditions align.

The retreat layer should watch four trigger families:

- market shock: broad index selloff and breadth collapse
- cluster shock: AI / semis / small caps weakening together
- structure break: below `MA20`, negative day move, weak relative return, or deep recent drawdown
- news confirmation: negative news only matters when price and relative strength already deteriorate

This keeps the core strategy medium-term while making defense more practical in real drawdowns.

### 3. One Benchmark Vocabulary Across Decision And Evaluation

Benchmark routing should not live as ad-hoc `if/else` logic in one service and a different interpretation in another.

The upgrade should centralize:

- cluster inference
- benchmark candidate lists
- benchmark resolution against available history
- relative-strength calculation

`build_swing_report()` and the scorecard should use the same routing logic so the report and the backtest speak the same language.

## Options Considered

### Option A: Keep Current Scoring, Only Improve Output

Pros:

- fastest to ship
- zero behavioral risk

Cons:

- does not improve actual decision quality
- leaves the main accuracy bottleneck untouched

### Option B: Add Benchmark-Relative Scoring And Hard Retreat Rules

Pros:

- highest impact per line of code
- stays deterministic and testable
- directly improves user-facing allocation and de-risking decisions

Cons:

- requires careful tuning to avoid over-downgrading risk assets

### Option C: Reintroduce LLM As Primary Decision Layer

Pros:

- flexible narrative
- may absorb more context in one pass

Cons:

- harder to verify
- higher variance and lower reproducibility
- does not solve benchmark routing rigor

## Recommendation

Choose **Option B**.

It keeps the current deterministic `swing` design, improves the actual investment decision layer, and preserves the user's stated preference: medium-term, readable, and able to retreat quickly when the tape breaks.

## Proposed Architecture

### Benchmark Profiles

Add a shared benchmark profile layer in the swing strategy flow:

- `broad_beta` -> `510300`, `159338`, `510980`
- `small_cap` -> `510500`, `563300`, then broad beta fallback
- `ai` -> `159819`, `588760`, then broad beta fallback
- `semiconductor` -> `512480`, `560780`, then broad beta fallback
- `precious_metals` -> `159934`, then broad beta fallback
- `sector_etf` / unknown -> broad beta fallback

Resolution rule:

- prefer same-cluster benchmark if available in the recent history
- never benchmark a symbol against itself
- if no thematic proxy exists in the dataset, fall back to broad beta

### Relative-Strength Snapshot

For each holding, build a deterministic snapshot from the recent price matrix:

- `10/20/40` day asset return
- matched benchmark return
- `20/40` day relative return
- recent maximum drawdown
- whether the asset is above or below its reference benchmark trend

This snapshot becomes a scoring input and a reason generator.

### Emergency Retreat Overlay

Add a second-stage overlay after base scoring.

The overlay should downgrade actions when any of these patterns appear:

- `撤退` regime plus high-beta cluster exposure
- same-cluster breakdown across at least two risk clusters
- single holding with structure break plus weak relative return
- negative news plus structure break plus weak relative return

Downgrades remain staged:

- `增配 -> 持有`
- `持有 -> 观察`
- `观察 -> 减配`
- `减配 -> 回避`

For severe breakdowns, allow skipping one extra level for risk clusters.

## User-Facing Output Changes

The report should stay plain-language, but reasons should become more decision-oriented:

- mention whether the holding is stronger or weaker than its matched benchmark
- mention whether recent drawdown is still acceptable
- mention whether the retreat rule is being triggered by market, cluster, or news confirmation

The user should be able to answer three questions from one glance:

1. Is this still stronger than the alternatives?
2. Is the market still allowing this kind of risk?
3. If not, what exact line forces reduction?

## Testing Strategy

The upgrade should be implemented with TDD:

- test benchmark resolution with clustered proxies and fallbacks
- test relative-strength promotion and demotion
- test retreat overlay for sharp downside and bad-news confirmation
- test the analysis service scorecard uses the same benchmark routing

## Expected Outcome

After this change, `swing` should behave closer to a disciplined medium-term allocation process:

- stronger assets survive because they outperform the right benchmark
- weak but noisy assets are not mistaken for opportunities
- sharp deteriorations produce faster, more consistent reductions

That should improve practical decision quality more than any further model switch.
