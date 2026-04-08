# Swing Watchlist Fast-Track Design

**Goal:** Let clearly strong watchlist names enter the `试仓区` earlier so the `swing` strategy misses fewer offensive opportunities, without weakening existing validation or execution guards.

## Problem

The current watchlist promotion path is conservative:

- it relies heavily on `final_action`
- it only promotes a narrow set of `增配/持有` cases
- strong watchlist ideas can stay in `继续观察` even when the setup is already actionable

This creates the specific failure mode we want to fix: the strategy sees strength, but the watchlist still enters too slowly.

## Scope

Included:
- watchlist candidate promotion rules in `src/service/watchlist_engine.py`
- regression tests for fast-track promotion and guard preservation

Excluded:
- held-position action logic
- global validation policy
- trade guard policy
- position sizing
- candidate limit / daily add quota

## Recommended Approach

Add a narrow `setup-aware fast-track` only for watchlist candidates.

The existing promotion path remains unchanged. The new path is additive and only applies when a candidate shows a strong offensive setup but has not yet been lifted far enough by the current `final_action` gate.

## Fast-Track Rules

Promote a watchlist candidate to `进入试仓区` when all of the following are true:

- `market_regime` is `进攻` or `均衡`
- `setup_type` is `trend_follow` or `pullback_resume`
- `confidence` is `高`
- one of these signal conditions is true:
  - `signal == OPPORTUNITY`
  - `signal == ACCUMULATE`

Keep the existing hard stops:

- `撤退` regime still blocks promotion
- validation weakness still pushes the candidate back to `继续观察`
- global offensive gate still pushes the candidate back to `继续观察`
- `trade_guard.allow_new_entries == False` still pushes the candidate back to `继续观察`
- candidate count limits still apply after promotion

## Why This Approach

This is the best trade-off for the stated goal.

- It directly addresses slow watchlist entry.
- It does not loosen the strategy everywhere.
- It preserves the current defense layers.
- It is easy to test and easy to reason about.

## Risks

- If the fast-track is too broad, the watchlist becomes noisy and over-eager.
- If it bypasses validation or trade guard, the system will feel more aggressive but lower quality.

We avoid both by keeping the eligibility rules narrow and leaving downstream blockers untouched.

## Testing

Add focused tests for:

- `ACCUMULATE + 高 + trend_follow + 进攻/均衡` enters `进入试仓区`
- `OPPORTUNITY + 高 + pullback_resume + 进攻/均衡` enters `进入试仓区`
- `ACCUMULATE + 中` stays `继续观察`
- `OPPORTUNITY + 高 + 撤退` stays `继续观察`
- fast-tracked candidates are still blocked by validation and trade guard when those layers say no
