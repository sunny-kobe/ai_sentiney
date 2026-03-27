# Validation-Driven Swing Actions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `swing` actions explicitly consume historical validation evidence so today's add/hold/reduce decisions are constrained by recent real and synthetic results, not just market-state heuristics.

**Architecture:** Extend the existing validation pipeline with a compact decision-evidence snapshot keyed by action, cluster, and regime. Feed that snapshot into `build_swing_report()` so each holding can attach a plain-language validation note and weak offensive setups can be downgraded automatically. Surface the resulting evidence in investor-facing swing renderers so the report explains both the action and the proof.

**Tech Stack:** Python 3.11+, pytest, existing `ValidationService`, `build_swing_report`, CLI/Feishu/Telegram renderers

---

### Task 1: Build validation decision evidence snapshot

**Files:**
- Modify: `src/service/validation_service.py`
- Test: `tests/test_validation_service_decision_evidence.py`

**Step 1: Write the failing test**

```python
def test_build_validation_decision_evidence_surfaces_action_cluster_and_regime_groups():
    ...
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest -q tests/test_validation_service_decision_evidence.py`
Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

- Add a helper that derives a `decision_evidence` payload from existing scorecard/diagnostic structures.
- Include:
  - primary window
  - live offensive gate
  - action evidence
  - cluster evidence
  - regime evidence

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest -q tests/test_validation_service_decision_evidence.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/validation_service.py tests/test_validation_service_decision_evidence.py
git commit -m "feat: add swing decision evidence snapshot"
```

### Task 2: Make swing actions consume validation evidence

**Files:**
- Modify: `src/service/swing_strategy.py`
- Modify: `tests/test_swing_strategy.py`

**Step 1: Write the failing test**

```python
def test_build_swing_report_downgrades_offensive_action_when_cluster_evidence_is_weak():
    ...

def test_build_swing_report_attaches_validation_evidence_summary_to_actions():
    ...
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest -q tests/test_swing_strategy.py -k "validation_evidence or cluster_evidence"`
Expected: FAIL because no per-action validation evidence is attached and no cluster-based downgrade exists.

**Step 3: Write minimal implementation**

- Read `validation_report["decision_evidence"]`.
- Attach one compact `validation_note` / `validation_evidence` per action.
- Downgrade offensive actions when matched cluster/regime evidence has enough samples and clearly negative relative performance or excessive drawdown.
- Preserve existing global offensive gate behavior.

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest -q tests/test_swing_strategy.py -k "validation_evidence or cluster_evidence"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/swing_strategy.py tests/test_swing_strategy.py
git commit -m "feat: drive swing actions from validation evidence"
```

### Task 3: Surface validation evidence in swing reports

**Files:**
- Modify: `src/main.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`
- Modify: `tests/test_swing_rendering.py`

**Step 1: Write the failing test**

```python
def test_cli_swing_summary_shows_per_position_validation_note():
    ...
```

**Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest -q tests/test_swing_rendering.py -k validation`
Expected: FAIL because the swing renderers do not show per-position validation evidence.

**Step 3: Write minimal implementation**

- Add one short `验证:` line under each swing holding/candidate when evidence is present.
- Keep wording investor-facing, not quantitative-jargon-heavy.

**Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest -q tests/test_swing_rendering.py -k validation`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/reporter/feishu_client.py src/reporter/telegram_client.py tests/test_swing_rendering.py
git commit -m "feat: show validation evidence in swing reports"
```

### Task 4: Full verification

**Files:**
- Verify only

**Step 1: Run targeted regression**

Run: `source .venv/bin/activate && pytest -q tests/test_validation_service_decision_evidence.py tests/test_swing_strategy.py tests/test_swing_rendering.py`
Expected: PASS

**Step 2: Run full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-27-validation-driven-swing-actions.md
git commit -m "docs: add validation-driven swing actions plan"
```
