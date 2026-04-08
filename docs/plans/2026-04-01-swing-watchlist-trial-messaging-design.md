# Swing Watchlist Trial Messaging Design

**Goal:** Make `swing` watchlist trial-entry candidates explain what kind of opportunity they are, so the report distinguishes breakout-style trials from pullback-resume trials.

## Problem

After adding faster watchlist entry, the current candidate copy is still generic:

- `reason` often just repeats raw evidence text
- `plan` does not clearly tell the user whether this is a breakout try or a pullback-resume try

That weakens the value of the earlier entry because the report still does not explain the execution style clearly enough.

## Scope

Included:
- watchlist candidate `plan` generation
- optional light normalization of watchlist `reason`
- focused rendering regression tests that consume the watchlist candidate fields

Excluded:
- held-position action plans
- validation policy
- trade guard policy
- position sizing
- watchlist eligibility logic

## Recommended Approach

Keep the current data shape and make the watchlist copy setup-aware.

For `进入试仓区` candidates:

- `trend_follow` should read like a breakout continuation trial
- `pullback_resume` should read like a pullback-confirmation trial

For `继续观察` candidates:

- keep the tone more cautious
- tell the user what confirmation is still missing for that setup type

This keeps rendering unchanged while improving what the existing renderers already show.

## Copy Direction

### Trial entry

- `trend_follow`
  - emphasize small initial entry
  - emphasize watching for post-breakout continuation
- `pullback_resume`
  - emphasize small initial entry
  - emphasize watching whether pullback support keeps holding

### Continue observing

- `trend_follow`
  - emphasize waiting for stronger breakout follow-through
- `pullback_resume`
  - emphasize waiting for stronger pullback confirmation and support

## Risks

- If the wording is too detailed, reports become noisy.
- If the wording does not match the actual setup type, the extra copy reduces trust.

We avoid both by keeping the copy short and mapping only a small number of known setup types.

## Testing

Add focused tests for:

- `进入试仓区 + trend_follow` yields breakout-style plan text
- `进入试仓区 + pullback_resume` yields pullback-style plan text
- `继续观察 + trend_follow` yields cautious breakout-watch text
- existing swing text rendering surfaces the updated candidate plan
