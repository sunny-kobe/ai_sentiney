# Swing Lab Hint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a compact strategy-lab hint to `swing` analysis and push outputs so reports recommend the most relevant aggressive midterm preset automatically.

**Architecture:** Build the hint inside `AnalysisService` from a fixed preset shortlist using existing compact `lab` results, then render that payload in Telegram / Feishu / CLI swing outputs. Keep reporters presentation-only and avoid exposing full lab details outside explicit `lab --detail full`.

**Tech Stack:** Python, pytest, existing `AnalysisService`, `StrategyLabService`, Telegram / Feishu reporters

---

### Task 1: Add failing tests for swing lab hint selection

**Files:**
- Modify: `tests/test_analysis_service_swing_mode.py`
- Modify: `src/service/analysis_service.py`

**Step 1: Write the failing test**

Add tests proving:

- `run_analysis(mode="swing")` injects `lab_hint`
- hint picks the preset with the best positive score delta
- if all presets lose, hint still picks the least-bad preset

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_analysis_service_swing_mode.py -q`

**Step 3: Write minimal implementation**

- add preset shortlist constant
- add helper to build `lab_hint`
- inject into swing analysis result

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_analysis_service_swing_mode.py -q`

**Step 5: Commit**

```bash
git add src/service/analysis_service.py tests/test_analysis_service_swing_mode.py
git commit -m "feat: add swing lab hint selection"
```

### Task 2: Add failing tests for swing rendering

**Files:**
- Modify: `tests/test_swing_rendering.py`
- Modify: `src/reporter/telegram_client.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/main.py`

**Step 1: Write the failing test**

Add tests proving:

- CLI swing text shows `实验提示`
- Telegram swing text shows `实验提示`
- Feishu swing card shows `实验提示`

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_swing_rendering.py -q`

**Step 3: Write minimal implementation**

- render a small lab hint block in all swing surfaces
- keep the text short and deterministic

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_swing_rendering.py -q`

**Step 5: Commit**

```bash
git add src/main.py src/reporter/telegram_client.py src/reporter/feishu_client.py tests/test_swing_rendering.py
git commit -m "feat: render swing lab hint"
```

### Task 3: Verify integrated swing push flow

**Files:**
- Modify: `tests/test_publish_target.py`
- Modify: `README.md`

**Step 1: Write the failing test**

Add a publish-flow test proving `swing` push result includes `lab_hint`.

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_publish_target.py -q`

**Step 3: Write minimal implementation**

- keep push flow unchanged except for richer `analysis_result`
- update README if needed

**Step 4: Run test to verify it passes**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_publish_target.py -q`

**Step 5: Commit**

```bash
git add README.md tests/test_publish_target.py
git commit -m "feat: document swing lab hint output"
```

### Task 4: Full verification

**Files:**
- No code change required

**Step 1: Run focused suites**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest tests/test_analysis_service_swing_mode.py tests/test_swing_rendering.py tests/test_publish_target.py -q
```

**Step 2: Run full suite**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q
```

**Step 3: Manual sanity checks**

```bash
source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run
```

Confirm:

- `lab_hint` exists in the JSON payload
- swing text and push surfaces show the experiment hint

**Step 4: Commit**

```bash
git add docs/plans/2026-03-26-swing-lab-hint-design.md docs/plans/2026-03-26-swing-lab-hint-implementation.md
git commit -m "docs: add swing lab hint design and plan"
```
