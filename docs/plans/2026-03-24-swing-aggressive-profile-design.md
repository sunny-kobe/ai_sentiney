# Swing Aggressive Profile Design

**Date:** 2026-03-24

## Goal

Make `swing` match an aggressive medium-term user:

- default to staying invested
- keep strongest holdings through normal pullbacks
- use add-on guidance when relative leaders stabilize
- reserve near-full exit for confirmed medium-term breakdowns

## Current Failure

The current engine is too defensive for this user profile.

On the live `2026-03-24` cached context:

- market regime is only `均衡`
- current exposure is `68.7%`
- target exposure collapses to `0%`
- all 8 holdings are forced to `回避`

This happens because three defensive layers stack without a user-style override:

1. `DANGER` starts from a low base score
2. stressed-cluster overlay downgrades entire high-beta groups together
3. emergency retreat overlay can push already weak holdings all the way to `回避`

The result is a balanced tape behaving like a liquidation regime.

## Product Direction

The user preference is explicit:

- style is aggressive, not conservative
- time horizon is medium-term, not short-term trading
- unless the market is truly broken mid-term, the report should prefer holding or adding
- only when the system has real confirmation should it recommend near-full retreat

So the strategy should become profile-aware rather than globally defensive.

## Recommended Approach

Add an `aggressive` risk profile for `strategy.swing`.

This profile changes three layers:

1. scoring tolerance
2. overlay downgrade behavior
3. regime exposure templates

### Why This Approach

It keeps the strategy deterministic and testable.

It also avoids bolting on ad-hoc exceptions inside rendering or report copy. The decision logic itself becomes aligned with the user.

## Profile Rules

### 1. Aggressive exposure templates

Use higher default exposure floors:

- `进攻`: `95%-100%`
- `均衡`: `75%-90%`
- `防守`: `45%-65%`
- `撤退`: `10%-25%`

`撤退` still keeps a small residual probe unless the system has severe confirmation to exit fully.

### 2. Aggressive score mapping

For aggressive mode:

- `broad_beta` gets extra tolerance outside `撤退`
- relative-strength leaders get extra support
- a normal pullback should usually land in `持有` or `减配`, not automatic `回避`
- `回避` should be reserved for deep weakness with confirmation

### 3. Smarter cluster overlay

When high-beta clusters weaken together:

- do not downgrade every member blindly
- keep the relative leader or strongest score in each stressed cluster
- downgrade laggards first

This prevents the system from liquidating the entire AI / semiconductor / small-cap sleeve when one ETF is still outperforming its benchmark.

### 4. Stricter retreat confirmation

Allow near-full retreat only when multiple conditions align:

- market regime is `撤退`, or
- structure breaks, and
- relative strength is weak, and
- either negative-news confirmation or cluster-wide failure is present

Outside `撤退`, severe drop alone should usually mean `减配`, not full exit.

### 5. Strong-name retention floor

In `均衡` and `防守`, if a holding is:

- `broad_beta`, or
- strongest inside a stressed cluster, or
- clearly strong versus benchmark

then it should retain non-zero target weight unless the retreat-confirmation rules fire.

## Config Changes

Add profile selection in `config.yaml`:

- `strategy.swing.risk_profile: aggressive`

This keeps the behavior explicit and makes future profiles possible without rewiring the whole strategy.

## Testing Strategy

Add regression tests for:

1. aggressive `均衡` regime does not collapse to `100%` cash
2. strongest holdings in a stressed tape still retain weight
3. retreat-confirmed scenarios can still drive exposure near zero
4. live-position rebalance text shifts from all-sell toward hold / add where appropriate

## Files To Modify

- `config.yaml`
- `src/service/swing_strategy.py`
- `tests/test_swing_strategy.py`

## Review Notes

This design intentionally does not:

- predict bottoms
- average down automatically
- turn daily pullbacks into forced buys

The strategy remains medium-term and confirmation-based.

The change is only that the default posture becomes attack-first, with liquidation reserved for true regime failure.
