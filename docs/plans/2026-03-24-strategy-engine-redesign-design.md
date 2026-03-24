# Strategy Engine Redesign

**Date:** 2026-03-24

## Goal

Rebuild Sentinel into a rule-first investment execution system where:

- accuracy is the primary optimization target
- false-positive buy signals are reduced sharply
- the system prefers "do nothing" over low-quality action
- LLM output becomes explanatory instead of decision-making
- each report is easier to execute as an investor

This redesign also fixes the persistence bug that currently makes recent runs appear saved in logs while not actually being committed to SQLite.

## Current Problems

### 1. Persistence bug is real, not just "no official run yet"

GitHub Actions has already run this workflow many times, so "no production execution" is not the main explanation for missing records.

The root cause is in `SentinelDB.save_record()`:

- insert succeeds inside a connection context
- no explicit `commit()` is called
- SQLite changes are rolled back when the connection closes
- logs incorrectly report success

This breaks:

- replay confidence
- historical analysis
- swing/performance tracking credibility

### 2. Decision authority is split and noisy

Current behavior mixes:

- rule-engine signals from `DataProcessor`
- ad-hoc strategy logic in `swing_strategy.py`
- LLM-generated actions for `midday/preclose/close`

That makes accuracy hard to improve because the final action is not produced by one testable decision chain.

### 3. Output is harder to execute than to read

The current reports often contain:

- too many internal labels
- too much explanatory text relative to actionable instruction
- ambiguous phrasing like "观望/持有观察" without enough execution context
- swing text that can conflict with current position state

### 4. Statistics do not separate defensive quality from offensive quality

Current scorecards bundle signals together too much.

For this user, the key questions are:

- when the system says reduce risk, did that avoid damage?
- when the system says add, did that actually create excess return?
- when the system says hold, did that avoid meaningful underperformance?

Those are different behaviors and must be measured separately.

## Product Direction

The redesigned product should behave like a disciplined execution assistant, not a generic AI commentator.

The system should:

- use deterministic rules to decide action
- use historical performance gates to suppress weak offensive setups
- expose only a small number of investor-facing action labels
- generate concise execution plans by mode

The system should not:

- chase every intraday move
- generate discretionary buy/sell decisions from the LLM alone
- overfit to tiny sample sizes

## Recommended Architecture

### 1. Strategy Engine

Add a unified decision pipeline:

- `market_regime.py`
- `setup_classifier.py`
- `execution_gate.py`
- `performance_gate.py`
- `strategy_engine.py`

This engine becomes the single source of truth for action generation.

### 2. Standard Decision Object

All non-morning modes should first produce a normalized strategy payload containing:

- `market_regime`
- `action_bias`
- `target_exposure`
- `holdings[]`

Each holding should include:

- `final_action`
- `setup_type`
- `confidence`
- `evidence`
- `invalid_condition`
- `execution_window`
- `target_weight_range`
- `rebalance_instruction`

This allows each mode to render different views from the same decision state.

### 3. Rule-first, LLM-second

The LLM should no longer decide whether to buy or sell.

Instead:

- rules decide the action
- historical gates decide whether offensive setups are currently allowed
- the LLM only translates the already-decided action set into readable summaries where helpful

For some paths, deterministic rendering may be preferable to LLM explanation if it is clearer and more reliable.

## Mode Redesign

### `midday`

Purpose:

- intraday diagnosis only
- risk warning and hold confirmation

Allowed outcomes:

- hold
- reduce-risk warning
- re-check at preclose

Not allowed:

- proactive intraday buy recommendations

### `preclose`

Purpose:

- only intraday execution mode

Allowed outcomes:

- trim today
- hold today
- rarely add a small amount today

An intraday add is only allowed if:

- regime is not `撤退`
- setup is offensive and validated
- relative strength beats benchmark
- price/volume confirms
- recent same-setup offensive stats remain healthy

### `close`

Purpose:

- post-close review
- next-day conditional plan generation

Output style:

- what worked today
- what failed today
- what condition tomorrow would trigger action

### `swing`

Purpose:

- primary strategy layer
- next-trading-day execution plan

Output must include:

- total target exposure
- core holdings to keep
- names to reduce
- names allowed for new trial allocation
- execution order for the next session

## Signal System Redesign

Investor-facing labels should collapse to four actions:

- `增配`
- `持有`
- `减配`
- `回避`

Internal setup labels should become:

- `trend_follow`
- `pullback_resume`
- `breakdown`
- `rebound_trap`
- `conflict`

This keeps internal logic expressive while making the report legible.

## Statistical Redesign

Replace one blended "accuracy" concept with separate scorecards:

### Defensive Quality

Measure whether `减配/回避` reduced future drawdown or relative underperformance across forward windows.

### Offensive Quality

Measure whether `增配` produced forward absolute and benchmark-relative outperformance with acceptable drawdown.

### Hold Quality

Measure whether `持有` avoided material underperformance versus benchmark.

### Restraint Rate

Measure how often the engine correctly chooses no action.

This is intentional signal discipline, not inactivity failure.

### Dynamic Performance Gate

Offensive setups should lose permission automatically when recent same-setup results weaken.

For example:

- low sample count -> no aggressive permission
- poor recent relative return -> downgrade offensive action
- excessive drawdown -> downgrade offensive action

## Rollout Plan

Use phased integration:

1. fix persistence and land the new engine foundation
2. connect `swing`
3. connect `preclose`
4. align `midday` and `close`
5. update statistics and rendering

This minimizes rollout risk while improving the highest-value paths first.

## Files To Add

- `src/service/strategy_engine.py`
- `src/service/market_regime.py`
- `src/service/setup_classifier.py`
- `src/service/execution_gate.py`
- `src/service/performance_gate.py`

## Files To Modify

- `src/storage/database.py`
- `src/service/analysis_service.py`
- `src/service/swing_strategy.py`
- `src/service/structured_report.py`
- `src/processor/swing_tracker.py`
- `src/main.py`
- `src/reporter/telegram_client.py`
- `src/reporter/feishu_client.py`
- relevant test files

## Non-Goals

This redesign does not include:

- machine-learning prediction models
- external paid factor feeds
- market-wide stock selection
- auto-order placement
- minute-level quantitative execution

The scope is accuracy and usability for the current holdings-driven workflow.
