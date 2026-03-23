# Swing Benchmark And Retreat Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade `swing` with cluster-aware benchmark routing, benchmark-relative strength scoring, and staged retreat rules for sharp downside and bad-news confirmation.

**Architecture:** Keep the current deterministic `swing` report structure, but centralize benchmark routing and add a relative-strength snapshot derived from historical price records. Apply a second-stage retreat overlay after base scoring so the engine can reduce risk faster during market, cluster, and structure breakdowns without turning back into a short-term predictor.

**Tech Stack:** Python 3, pytest, existing sqlite daily records, deterministic swing strategy service, existing CLI/Feishu/Telegram renderers

---

### Task 1: Define Benchmark Profiles And Resolution Tests

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- AI / semiconductor / small-cap assets resolve to cluster-appropriate benchmark candidates
- fallback uses broad beta when no thematic proxy exists
- the symbol is never benchmarked against itself

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k benchmark`

Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

Implement helpers such as:
- `resolve_benchmark_code(stock, available_codes)`
- `build_benchmark_context(stocks, historical_records)`

Behavior:
- centralize benchmark candidate lists
- prefer same-cluster proxy when available
- fall back to broad beta when needed

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k benchmark`

Expected: PASS

### Task 2: Add Relative-Strength Scoring

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- a holding with strong `20/40` day relative return is promoted vs the same raw signal on a weak peer
- negative relative return and deeper drawdown reduce the action label
- plain-language reason mentions benchmark-relative leadership or lagging

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k relative`

Expected: FAIL because scoring does not use benchmark-relative history yet.

**Step 3: Write minimal implementation**

Implement:
- historical price snapshot extraction from recent records
- `20/40` day relative return and drawdown scoring
- reason text additions such as “强于对照基准” / “弱于对照基准”

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k relative`

Expected: PASS

### Task 3: Add Emergency Retreat Overlay

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- `撤退` regime plus sharp downside in a risk cluster forces faster downgrade
- negative news only triggers when paired with structure break and weak relative return
- downgrade reason explains whether the trigger is market, cluster, or news confirmation

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k retreat`

Expected: FAIL because no emergency overlay helper exists.

**Step 3: Write minimal implementation**

Implement helpers such as:
- `detect_emergency_flags(stock, regime_info, benchmark_snapshot, ai_input)`
- `apply_emergency_retreat_overlay(decisions, ai_input, regime_info, benchmark_context)`

Behavior:
- stage downgrades by one level normally
- allow one extra downgrade for severe risk-cluster breakdowns
- append plain-language explanation and tighten `risk_line`

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k retreat`

Expected: PASS

### Task 4: Unify Analysis-Service Scorecard Benchmark Routing

**Files:**
- Modify: `tests/test_analysis_service_swing_mode.py`
- Modify: `src/service/analysis_service.py`

**Step 1: Write the failing test**

Cover:
- scorecard benchmark routing reuses the shared swing benchmark helpers
- benchmark map output matches themed proxies and broad fallback

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py -k benchmark`

Expected: FAIL because analysis service still owns separate routing logic.

**Step 3: Write minimal implementation**

Implement:
- service-level benchmark map construction by delegating to shared swing helpers
- no duplicate hard-coded benchmark routing in analysis service

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py -k benchmark`

Expected: PASS

### Task 5: Regression Verification

**Files:**
- Modify as needed based on regressions

**Step 1: Run swing suites**

Run:
- `.venv/bin/python -m pytest -q tests/test_swing_strategy.py tests/test_analysis_service_swing_mode.py tests/test_swing_tracker.py tests/test_swing_rendering.py`

**Step 2: Run the full suite**

Run:
- `.venv/bin/python -m pytest -q tests`

**Step 3: Run CLI verification**

Run:
- `.venv/bin/python -m src.main --mode swing --dry-run`
- `.venv/bin/python -m src.main --ask "最近一个月中期方向如何" --mode swing`

**Step 4: Commit**

```bash
git add docs/plans/2026-03-23-swing-benchmark-retreat-design.md docs/plans/2026-03-23-swing-benchmark-retreat-implementation.md src/service/analysis_service.py src/service/swing_strategy.py tests/test_analysis_service_swing_mode.py tests/test_swing_strategy.py
git commit -m "feat: strengthen swing benchmark and retreat rules"
git push origin main
```
