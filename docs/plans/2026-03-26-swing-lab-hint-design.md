# Swing Lab Hint Design

**Goal:** Surface a concise strategy-lab recommendation inside `swing` reports and push channels so the investor can see which experimental preset currently looks more useful without running `lab` manually.

## Scope

- Only touch the `swing` path.
- Reuse the existing `lab` compact output; do not make reporters understand full lab internals.
- Show one best preset at a time, not a ranked list.

## Recommended Approach

Inject a single `lab_hint` payload during `AnalysisService.run_analysis(mode="swing")`, then let Telegram and Feishu render it as a compact "实验提示" block.

Why this is the right boundary:

- `AnalysisService` already owns validation injection for `swing`.
- `StrategyLabService` already knows how to compare baseline vs candidate.
- Reporters should stay presentation-only.

## Candidate Selection

Run a fixed preset shortlist aligned to the user's aggressive medium-term style:

- `aggressive_trend_guard`
- `aggressive_leader_focus`
- `aggressive_core_rotation`

Pick the best preset by:

1. highest `candidate_score - baseline_score`
2. tie-break with lower `candidate_trade_count`

If no preset beats baseline, still surface the best-tested preset, but mark it as "当前没有跑赢基线".

## Payload Shape

`analysis_result["lab_hint"]` should be a small dict:

- `preset`
- `winner`
- `summary_text`
- `score_delta`
- `trade_count_delta`
- `total_return_delta`
- `max_drawdown_delta`
- `candidate_trade_count`

This keeps reporter coupling low and preserves machine-readable reuse later.

## Rendering

Telegram / Feishu / CLI swing text should render:

- title: `实验提示`
- one summary sentence
- one metrics line

Keep it short enough to scan in push notifications.

## Risks

- Running multiple presets adds latency.
- The best preset may still lose to baseline in a weak market.

These are acceptable because the hint is advisory, not a hard execution instruction.
