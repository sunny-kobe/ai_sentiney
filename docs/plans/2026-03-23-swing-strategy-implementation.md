# Swing Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new medium-term `swing` mode with plain-language portfolio guidance, forward `10/20/40` evaluation, and faster de-risking logic without depending on short-term hit-rate framing.

**Architecture:** Keep `midday` / `close` as tactical diagnostics, but add a deterministic `swing` engine that ranks holdings by trend, relative strength, and risk. Evaluate the system on forward holding windows and benchmark-relative outcomes rather than `T+1` price changes. Use rule-based output as the primary decision layer; reserve LLM usage for optional narrative only in later phases.

**Tech Stack:** Python 3, pytest, existing sqlite daily records, existing data processor pipeline, deterministic service modules, CLI/Feishu/Telegram renderers

---

### Task 1: Add Medium-Term Evaluation Engine

**Files:**
- Create: `src/processor/swing_tracker.py`
- Test: `tests/test_swing_tracker.py`

**Step 1: Write the failing tests**

Cover:
- forward `10/20/40` trading-day return calculation by matching symbol prices across historical records
- benchmark-relative return calculation
- max drawdown calculation between signal day and evaluation horizon
- grouped statistics for decision labels such as `增配` / `回避`

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_swing_tracker.py`

Expected: FAIL because the module and functions do not exist.

**Step 3: Write minimal implementation**

Implement pure functions such as:
- `build_price_matrix(records)`
- `evaluate_forward_windows(actions, future_records, benchmark_map)`
- `calculate_swing_stats(records, windows=(10, 20, 40))`
- `build_swing_scorecard(...)`

Behavior:
- ignore symbols with insufficient forward data
- compute forward absolute return, benchmark-relative return, and max drawdown
- aggregate by action label and confidence bucket

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_swing_tracker.py`

Expected: PASS

### Task 2: Build Deterministic Swing Decision Engine

**Files:**
- Create: `src/service/swing_strategy.py`
- Test: `tests/test_swing_strategy.py`

**Step 1: Write the failing tests**

Cover:
- market regime classification: `进攻` / `均衡` / `防守` / `撤退`
- per-holding recommendation mapping to `增配` / `持有` / `减配` / `回避` / `观察`
- cluster-aware downgrade when small-cap / AI / semiconductor exposures break together
- plain-language reason / plan / risk-line output

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_swing_strategy.py`

Expected: FAIL because the module and functions do not exist.

**Step 3: Write minimal implementation**

Implement deterministic scoring helpers such as:
- `classify_market_regime(ai_input, historical_records)`
- `score_holding(stock, benchmark_context)`
- `apply_cluster_risk_overlay(decisions)`
- `build_swing_report(ai_input, historical_records, analysis_date)`

Report requirements:
- market conclusion
- portfolio action buckets
- per-holding `结论` / `原因` / `计划` / `风险线`
- optional technical evidence block separated from the main body

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_swing_strategy.py`

Expected: PASS

### Task 3: Integrate `swing` Mode Into Analysis Flow

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/main.py`
- Modify: `src/utils/trading_calendar.py` if mode gating needs extension
- Test: `tests/test_analysis_service_swing_mode.py`

**Step 1: Write the failing tests**

Cover:
- `run_analysis(mode="swing")` returns deterministic swing report without Gemini dependency
- historical records are loaded and used for medium-term scorecard construction
- swing mode output includes regime, grouped actions, and medium-term scorecard
- accuracy queries use new medium-term stats instead of short-term-only framing

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py`

Expected: FAIL because `swing` mode is not implemented.

**Step 3: Write minimal implementation**

Implement:
- `--mode swing` support in CLI
- analysis-service branch for `swing`
- load recent `close` records for evaluation context
- deterministic swing-report generation
- medium-term accuracy-report helper using `swing_tracker`

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py`

Expected: PASS

### Task 4: Redesign Output Into Plain Language

**Files:**
- Modify: `src/main.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`
- Test: `tests/test_swing_rendering.py`

**Step 1: Write the failing tests**

Cover:
- CLI swing report renders `市场结论` / `组合动作` / `持仓清单`
- jargon-heavy technical tags are moved out of the headline action line
- Feishu and Telegram swing summaries show plain-language action buckets and risk lines

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_swing_rendering.py`

Expected: FAIL because renderers do not know about `swing` mode.

**Step 3: Write minimal implementation**

Implement:
- dedicated CLI text rendering for swing mode
- Feishu sections for regime, grouped actions, and top risks
- Telegram compact swing summary

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_swing_rendering.py`

Expected: PASS

### Task 5: Update Prompt / Config Surface For New Positioning Language

**Files:**
- Modify: `config.yaml`
- Modify: `README.md`
- Test: `tests/test_project_docs_swing_mode.py`

**Step 1: Write the failing tests**

Cover:
- config and docs mention `swing` mode
- short-term accuracy framing is no longer presented as the primary KPI
- portfolio outputs mention plain-language labels and medium-term windows

**Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest -q tests/test_project_docs_swing_mode.py`

Expected: FAIL because docs/config have not been updated.

**Step 3: Write minimal implementation**

Implement:
- `swing` mode prompt / configuration text if needed
- README updates for new mode and evaluation philosophy
- remove or down-rank short-term “prediction” framing in user-facing docs

**Step 4: Run test to verify it passes**

Run: `../../.venv/bin/python -m pytest -q tests/test_project_docs_swing_mode.py`

Expected: PASS

### Task 6: Full Regression And Verification

**Files:**
- Modify as needed based on regressions

**Step 1: Run targeted swing suites**

Run:
- `../../.venv/bin/python -m pytest -q tests/test_swing_tracker.py tests/test_swing_strategy.py tests/test_analysis_service_swing_mode.py tests/test_swing_rendering.py tests/test_project_docs_swing_mode.py`

**Step 2: Run existing report-related suites**

Run:
- `../../.venv/bin/python -m pytest -q tests/test_report_quality.py tests/test_structured_report.py tests/test_analysis_service_quality_flow.py tests/test_report_rendering_quality.py tests/test_analysis_service_replay.py tests/test_publish_target.py`

**Step 3: Run full test suite**

Run:
- `../../.venv/bin/python -m pytest -q tests`

**Step 4: Run CLI verification**

Run:
- `../../.venv/bin/python -m src.main --mode swing --dry-run`
- `../../.venv/bin/python -m src.main --ask "最近一个月中期方向如何" --mode swing`

Expected:
- exit code `0`
- swing report shows plain-language recommendations and medium-term framing

**Step 5: Commit**

```bash
git add docs/plans/2026-03-23-swing-strategy-implementation.md src/processor/swing_tracker.py src/service/swing_strategy.py src/service/analysis_service.py src/main.py src/reporter/feishu_client.py src/reporter/telegram_client.py config.yaml README.md tests/test_swing_tracker.py tests/test_swing_strategy.py tests/test_analysis_service_swing_mode.py tests/test_swing_rendering.py tests/test_project_docs_swing_mode.py
git commit -m "feat: add swing strategy mode"
```
