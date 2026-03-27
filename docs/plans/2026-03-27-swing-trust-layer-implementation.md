# Swing Trust Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `swing` reports distinguish between "core market data incomplete" and "supporting context incomplete", then turn that judgment into plain-language execution guidance and hard guards on risky actions.

**Architecture:** Add a small trust-layer helper in `report_quality.py` that reads collector block status and classifies `swing` output into `high / medium / low` trust. Feed that guard through `AnalysisService` into `build_swing_report()` and `build_watchlist_candidates()`, where it can block new entries or offensive adds when data quality is not good enough. Surface the result in CLI, Telegram, and Feishu using direct investor-facing language.

**Tech Stack:** Python 3, pytest, existing collector quality metadata, deterministic swing strategy/rendering pipeline

---

### Task 1: Lock trust-layer behavior with failing tests

**Files:**
- Modify: `tests/test_report_quality.py`
- Modify: `tests/test_analysis_service_swing_mode.py`
- Modify: `tests/test_watchlist_engine.py`
- Modify: `tests/test_swing_strategy.py`
- Modify: `tests/test_swing_rendering.py`

**Step 1: Write the failing tests**

Add tests for:
- supporting-data-only degradation -> `谨慎执行`
- core-data degradation -> `仅供参考`
- `AnalysisService.run_analysis(mode="swing")` exposes `execution_readiness`, `quality_summary`, `trade_guard`
- `build_swing_report()` downgrades offensive held actions when trust is low
- watchlist trial ideas are blocked when trust says no new entries
- swing renderers show `执行提示`

**Step 2: Run test to verify it fails**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q tests/test_report_quality.py tests/test_analysis_service_swing_mode.py tests/test_watchlist_engine.py tests/test_swing_strategy.py tests/test_swing_rendering.py -k "trade_guard or execution_readiness or quality_guard or supporting_blocks or core_blocks"`

Expected: FAIL because `build_swing_quality_guard` and trust-layer wiring do not exist yet.

### Task 2: Implement the swing trust-layer helper

**Files:**
- Modify: `src/service/report_quality.py`
- Test: `tests/test_report_quality.py`

**Step 1: Write minimal implementation**

Add:
- block-label mapping for investor-facing text
- `build_swing_quality_guard(ai_input)`
- trust outputs:
  - `high` -> `可执行`
  - `medium` -> `谨慎执行`
  - `low` -> `仅供参考`
- booleans:
  - `allow_offensive`
  - `allow_new_entries`

**Step 2: Run focused tests**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q tests/test_report_quality.py -k "quality_guard or supporting_blocks or core_blocks"`

Expected: PASS

### Task 3: Wire trust-layer into swing service and strategy

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/swing_strategy.py`
- Modify: `src/service/watchlist_engine.py`
- Test: `tests/test_analysis_service_swing_mode.py`
- Test: `tests/test_watchlist_engine.py`
- Test: `tests/test_swing_strategy.py`

**Step 1: Feed guard into swing analysis**

Add:
- `ai_input["swing_quality_guard"]`
- result fields:
  - `execution_readiness`
  - `quality_summary`
  - `trade_guard`

**Step 2: Apply the guard**

Rules:
- if `allow_offensive` is `False`, held `增配` downgrades to `持有`
- if `allow_new_entries` is `False`, watchlist `进入试仓区` downgrades to `继续观察`

**Step 3: Run focused tests**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q tests/test_analysis_service_swing_mode.py tests/test_watchlist_engine.py tests/test_swing_strategy.py -k "trade_guard or execution_readiness"`

Expected: PASS

### Task 4: Render trust-layer in plain language

**Files:**
- Modify: `src/main.py`
- Modify: `src/reporter/telegram_client.py`
- Modify: `src/reporter/feishu_client.py`
- Test: `tests/test_swing_rendering.py`

**Step 1: Add plain-language execution section**

Add `执行提示` with:
- `可执行度`
- a one-line explanation

**Step 2: Run rendering tests**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q tests/test_swing_rendering.py`

Expected: PASS

### Task 5: Verify end-to-end and commit

**Files:**
- Modify: `docs/plans/2026-03-27-swing-trust-layer-implementation.md`

**Step 1: Run full verification**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && pytest -q`

Expected: PASS

**Step 2: Run swing dry-run**

Run: `source /Users/lan/Desktop/code/ai_sentiney/.venv/bin/activate && python -m src.main --mode swing --dry-run`

Expected: report includes `执行提示` and shows a differentiated trust message instead of only raw degraded metadata.

**Step 3: Commit**

```bash
git add docs/plans/2026-03-27-swing-trust-layer-implementation.md src/service/report_quality.py src/service/analysis_service.py src/service/swing_strategy.py src/service/watchlist_engine.py src/main.py src/reporter/telegram_client.py src/reporter/feishu_client.py tests/test_report_quality.py tests/test_analysis_service_swing_mode.py tests/test_watchlist_engine.py tests/test_swing_strategy.py tests/test_swing_rendering.py
git commit -m "feat: add swing execution trust layer"
```
