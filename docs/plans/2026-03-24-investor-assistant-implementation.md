# Investor Assistant Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the swing workflow into a medium-term investor assistant centered on holdings, a small watchlist, and formal validation.

**Architecture:** Keep the existing collection and delivery pipeline, add normalized account and watchlist inputs, add a formal backtest and validation layer, and refactor swing output into an action-first report. Deterministic rules remain the source of truth; LLM narration stays secondary.

**Tech Stack:** Python, pytest, SQLite, existing Project Sentinel services, new internal backtest module

---

### Task 1: Add watchlist and swing account controls to configuration

**Files:**
- Modify: `config.yaml`
- Modify: `src/utils/config_loader.py`
- Modify: `tests/test_config_loader.py`

**Step 1: Write the failing tests**

Add tests proving:

- `ConfigLoader` exposes `watchlist`
- `ConfigLoader` exposes swing account controls under `strategy.swing`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_loader.py -q`
Expected: FAIL because watchlist getters or config fields are missing.

**Step 3: Write minimal implementation**

- Add `watchlist` sample config
- Add getters for `watchlist` and `strategy.swing`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_loader.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add config.yaml src/utils/config_loader.py tests/test_config_loader.py
git commit -m "feat: add watchlist and swing account config"
```

### Task 2: Introduce normalized investor assistant models

**Files:**
- Create: `src/service/portfolio_advisor.py`
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_portfolio_advisor.py`

**Step 1: Write the failing tests**

Add tests proving:

- holdings and watchlist are normalized into a single snapshot
- portfolio cash and lot size are carried through
- watchlist candidates are marked as non-held assets

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_portfolio_advisor.py -q`
Expected: FAIL because module does not exist.

**Step 3: Write minimal implementation**

- Build a snapshot helper that combines holdings, watchlist, strategy preferences, and account constraints
- Wire `AnalysisService` to include watchlist and swing controls in `ai_input`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_portfolio_advisor.py tests/test_analysis_service_swing_mode.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/portfolio_advisor.py src/service/analysis_service.py tests/test_portfolio_advisor.py tests/test_analysis_service_swing_mode.py
git commit -m "feat: normalize holdings and watchlist snapshot"
```

### Task 3: Add watchlist opportunity engine to swing strategy

**Files:**
- Create: `src/service/watchlist_engine.py`
- Modify: `src/service/swing_strategy.py`
- Modify: `src/service/strategy_engine.py`
- Test: `tests/test_watchlist_engine.py`
- Test: `tests/test_swing_strategy.py`

**Step 1: Write the failing tests**

Add tests proving:

- watchlist assets can be scored separately from holdings
- only top candidates become `进入试仓区`
- candidate count is capped
- weak or duplicate assets stay in `继续观察`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watchlist_engine.py -q`
Expected: FAIL because module and fields do not exist.

**Step 3: Write minimal implementation**

- Add watchlist scoring and candidate ranking
- Add account-aware candidate limits
- Extend swing report output with `watchlist_actions` and `watchlist_candidates`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_watchlist_engine.py tests/test_swing_strategy.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/watchlist_engine.py src/service/swing_strategy.py src/service/strategy_engine.py tests/test_watchlist_engine.py tests/test_swing_strategy.py
git commit -m "feat: add watchlist opportunity engine"
```

### Task 4: Implement formal backtest primitives

**Files:**
- Create: `src/backtest/engine.py`
- Create: `src/backtest/adapter.py`
- Create: `src/backtest/report.py`
- Create: `src/backtest/walkforward.py`
- Test: `tests/test_backtest_engine.py`
- Test: `tests/test_backtest_walkforward.py`

**Step 1: Write the failing tests**

Add tests proving:

- `T` close signal becomes `T+1` open execution
- cash is reduced on buy and increased on sell
- lot size rounding applies
- fees and taxes are applied
- walk-forward windows aggregate multiple periods

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_backtest_engine.py tests/test_backtest_walkforward.py -q`
Expected: FAIL because modules do not exist.

**Step 3: Write minimal implementation**

- Add deterministic backtest engine
- Add adapter from swing actions to backtest orders
- Add report metrics and walk-forward runner

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_backtest_engine.py tests/test_backtest_walkforward.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/backtest tests/test_backtest_engine.py tests/test_backtest_walkforward.py
git commit -m "feat: add deterministic swing backtest layer"
```

### Task 5: Feed validation results back into swing decisions

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/service/swing_strategy.py`
- Modify: `src/processor/swing_tracker.py`
- Test: `tests/test_analysis_service_swing_mode.py`
- Test: `tests/test_swing_strategy.py`

**Step 1: Write the failing tests**

Add tests proving:

- swing report includes validation summary
- insufficient samples degrade confidence instead of fabricating conviction
- historical weak setups are downgraded

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analysis_service_swing_mode.py tests/test_swing_strategy.py -q`
Expected: FAIL because validation feedback is absent.

**Step 3: Write minimal implementation**

- Add validation summary to swing report
- Inject event-study/backtest quality into action ranking
- Surface sample sufficiency markers

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analysis_service_swing_mode.py tests/test_swing_strategy.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/service/analysis_service.py src/service/swing_strategy.py src/processor/swing_tracker.py tests/test_analysis_service_swing_mode.py tests/test_swing_strategy.py
git commit -m "feat: feed validation results into swing decisions"
```

### Task 6: Rebuild the swing report format for execution clarity

**Files:**
- Modify: `src/main.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`
- Test: `tests/test_swing_rendering.py`

**Step 1: Write the failing tests**

Add tests proving:

- swing CLI output uses new 5-section layout
- reports show watchlist opportunities
- reports show concise action wording instead of indicator-heavy text

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_swing_rendering.py -q`
Expected: FAIL because current layout does not match.

**Step 3: Write minimal implementation**

- Refactor CLI summary
- Refactor Feishu card and Telegram text
- Keep fields deterministic and plain-language

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_swing_rendering.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/reporter/feishu_client.py src/reporter/telegram_client.py tests/test_swing_rendering.py
git commit -m "feat: rebuild swing report for investor execution"
```

### Task 7: Add validation entry points and documentation updates

**Files:**
- Modify: `src/main.py`
- Modify: `README.md`
- Modify: `.github/workflows/daily_sentinel.yml`
- Test: `tests/test_project_docs_swing_mode.py`
- Test: `tests/test_workflow_swing_automation.py`

**Step 1: Write the failing tests**

Add tests proving:

- README documents watchlist and validation workflow
- workflow still supports swing automation after report changes
- CLI can expose validation or backtest results where appropriate

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_docs_swing_mode.py tests/test_workflow_swing_automation.py -q`
Expected: FAIL because docs and workflow wording are outdated.

**Step 3: Write minimal implementation**

- Update README positioning and examples
- Keep automation compatible
- Add CLI hooks for validation report if implemented

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_docs_swing_mode.py tests/test_workflow_swing_automation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py README.md .github/workflows/daily_sentinel.yml tests/test_project_docs_swing_mode.py tests/test_workflow_swing_automation.py
git commit -m "docs: document investor assistant workflow"
```

### Task 8: Full verification and release integration

**Files:**
- Verify all touched files

**Step 1: Run targeted verification**

Run:

```bash
pytest -q tests/test_config_loader.py tests/test_portfolio_advisor.py tests/test_watchlist_engine.py tests/test_backtest_engine.py tests/test_backtest_walkforward.py tests/test_swing_strategy.py tests/test_analysis_service_swing_mode.py tests/test_swing_rendering.py
```

Expected: PASS

**Step 2: Run full verification**

Run:

```bash
pytest -q tests
python -m src.main --mode swing --replay --dry-run --output json
python -m src.main --mode close --replay --dry-run --output json
```

Expected: PASS and action-oriented JSON output

**Step 3: Merge and push**

```bash
git checkout main
git merge --ff-only feature/investor-assistant
git push origin main
```
