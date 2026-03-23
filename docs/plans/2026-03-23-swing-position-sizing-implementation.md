# Swing Position Sizing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add actionable `核心仓 / 卫星仓 / 现金` sizing guidance to `swing`, with weekly rebalance plans and daily risk-only reductions.

**Architecture:** Keep the current deterministic `swing` scoring and retreat engine, then add a second-layer sizing planner that maps regime budgets into core and satellite allocations. The planner should assign per-holding weight ranges, keep weak positions small, and roll unused budget into cash. Render this plan consistently in CLI, Feishu, and Telegram.

**Tech Stack:** Python 3, pytest, deterministic strategy helpers, existing `swing` analysis service, CLI/Feishu/Telegram renderers

---

### Task 1: Add Position-Sizing Strategy Tests

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- `build_swing_report()` returns `position_plan`
- regime templates map to expected core / satellite / cash ranges
- strong broad-beta holdings become `核心仓`
- AI / semiconductor / small-cap become `卫星仓`
- `回避` gets `0%`

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k position`

Expected: FAIL because the sizing planner does not exist yet.

**Step 3: Write minimal implementation**

Implement helpers such as:
- `assign_position_bucket(decision)`
- `build_position_plan(decisions, regime)`
- `format_weight_range(min_weight, max_weight)`

Behavior:
- map regimes to sizing templates
- allocate weights across core and satellite buckets
- roll unused budget into cash

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k position`

Expected: PASS

### Task 2: Add Weekly And Daily Execution Rules

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- `position_plan` contains weekly rebalance rhythm
- plan states `日级只减不加`
- `观察` and `减配` positions get small target ranges

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k rebalance`

Expected: FAIL because execution-plan text is missing.

**Step 3: Write minimal implementation**

Implement:
- weekly execution summary text
- daily risk-only reduction rule
- small-weight caps for `观察` / `减配`

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k rebalance`

Expected: PASS

### Task 3: Render Position Plan In User-Facing Outputs

**Files:**
- Modify: `tests/test_swing_rendering.py`
- Modify: `src/main.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`

**Step 1: Write the failing test**

Cover:
- CLI shows `仓位计划`
- CLI holding lines show bucket and target weight
- Feishu and Telegram include total exposure and cash guidance

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_rendering.py -k position`

Expected: FAIL because renderers do not show the sizing layer yet.

**Step 3: Write minimal implementation**

Implement:
- CLI `仓位计划` section
- Feishu card section for total exposure, core, satellite, cash
- Telegram compact position-plan lines

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_rendering.py -k position`

Expected: PASS

### Task 4: Verify Swing Analysis Integration

**Files:**
- Modify: `tests/test_analysis_service_swing_mode.py`
- Modify: `src/service/analysis_service.py` if needed

**Step 1: Write the failing test**

Cover:
- `run_analysis(mode="swing")` preserves `position_plan`
- `--ask ... --mode swing` can surface sizing guidance

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py -k position`

Expected: FAIL if the result shape or Q&A text drops the sizing layer.

**Step 3: Write minimal implementation**

Implement:
- pass-through of `position_plan`
- brief sizing lines in swing Q&A summary

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py -k position`

Expected: PASS

### Task 5: Regression Verification

**Files:**
- Modify as needed based on regressions

**Step 1: Run targeted tests**

Run:
- `.venv/bin/python -m pytest -q tests/test_swing_strategy.py tests/test_swing_rendering.py tests/test_analysis_service_swing_mode.py`

**Step 2: Run full suite**

Run:
- `.venv/bin/python -m pytest -q tests`

**Step 3: Run CLI verification**

Run:
- `.venv/bin/python -m src.main --mode swing --dry-run`
- `.venv/bin/python -m src.main --ask "本周仓位怎么配" --mode swing`

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-swing-position-sizing-design.md docs/plans/2026-03-23-swing-position-sizing-implementation.md src/main.py src/reporter/feishu_client.py src/reporter/telegram_client.py src/service/analysis_service.py src/service/swing_strategy.py tests/test_analysis_service_swing_mode.py tests/test_swing_rendering.py tests/test_swing_strategy.py
git commit -m "feat: add swing position sizing plan"
git push origin main
```
