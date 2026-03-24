# Swing Aggressive Profile Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `swing` keep an aggressive medium-term posture by default, preserve non-zero weights for stronger holdings during normal stress, and reserve near-full retreat for confirmed breakdown regimes.

**Architecture:** Introduce a configurable `risk_profile` for `strategy.swing`, then thread that profile through scoring, risk overlays, and position sizing. Keep the report deterministic: aggressive mode should soften downgrades in `均衡` and `防守`, preserve leaders, and only allow near-full exit when retreat confirmation is strong.

**Tech Stack:** Python 3.11, pytest, existing deterministic `swing` strategy helpers, YAML config

---

### Task 1: Add Failing Regression Tests For Aggressive Balanced Regimes

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- aggressive `均衡` regime does not produce `cash_target = 100%`
- broad-beta or relative-strength leaders keep non-zero `target_weight`
- current-position rebalance text is not all forced sells

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k aggressive`

Expected: FAIL because the strategy does not yet support an aggressive profile.

**Step 3: Write minimal implementation**

Implement:
- `risk_profile` resolution
- profile-aware exposure templates
- aggressive leader-retention behavior

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k aggressive`

Expected: PASS

### Task 2: Add Failing Regression Tests For Confirmed Retreat

**Files:**
- Modify: `tests/test_swing_strategy.py`
- Modify: `src/service/swing_strategy.py`

**Step 1: Write the failing test**

Cover:
- aggressive profile still cuts close to cash when retreat confirmation is strong
- weak leaders do not survive true breakdown regimes

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k retreat`

Expected: FAIL if the new aggressive profile weakens the emergency retreat rules too much.

**Step 3: Write minimal implementation**

Implement:
- profile-aware retreat confirmation thresholds
- exposure floor bypass when confirmed retreat is active

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py -k retreat`

Expected: PASS

### Task 3: Wire Config And Strategy

**Files:**
- Modify: `config.yaml`
- Modify: `src/service/swing_strategy.py`

**Step 1: Update config**

Add:
- `strategy.swing.risk_profile: aggressive`

**Step 2: Implement profile plumbing**

Thread `risk_profile` into:
- scoring
- cluster overlay
- emergency retreat overlay
- position-plan template selection

**Step 3: Run targeted tests**

Run: `.venv/bin/python -m pytest -q tests/test_swing_strategy.py`

Expected: PASS

### Task 4: Verify Real Swing Output

**Files:**
- No new files required unless regression fixes are needed

**Step 1: Run service-level verification**

Run a local `AnalysisService().run_analysis(mode="swing", dry_run=True)` check and inspect:
- market regime
- total exposure target
- cash target
- per-holding rebalance actions

**Step 2: Confirm behavioral change**

Expected:
- `均衡` no longer maps to `0%` total exposure
- at least the stronger / core holdings retain weight
- add / hold language appears where justified

### Task 5: Final Verification And Ship

**Files:**
- Modify as required by regressions

**Step 1: Run full suite**

Run: `.venv/bin/python -m pytest -q tests`

**Step 2: Commit**

```bash
git add docs/plans/2026-03-24-swing-aggressive-profile-design.md docs/plans/2026-03-24-swing-aggressive-profile-implementation.md config.yaml src/service/swing_strategy.py tests/test_swing_strategy.py
git commit -m "feat: add aggressive swing risk profile"
git push origin main
```
