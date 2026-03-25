# Validation Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a compact swing validation snapshot, expose it through WebUI, and surface concise validation counters in push/report outputs.

**Architecture:** Keep one validation source of truth in `AnalysisService.build_validation_snapshot("swing")`, but reshape it into a compact payload suitable for CLI JSON, WebUI, and reporter hint lines. Extend the current WebUI with a lightweight validation card rather than introducing a new page or framework.

**Tech Stack:** Python 3, pytest, existing WebUI router/templates, existing Feishu/Telegram renderers

---

### Task 1: Add failing tests for compact validation snapshot

**Files:**
- Modify: `tests/test_main_validation_report.py`
- Modify: `tests/test_analysis_service_swing_mode.py`

**Step 1: Write the failing test**

Add tests proving:

```python
def test_build_validation_snapshot_returns_compact_payload_without_heavy_evaluations():
    ...

def test_entry_point_validation_report_json_uses_compact_snapshot():
    ...
```

The assertions should verify:

1. snapshot contains `compact`
2. `compact` includes verdict, sample counts, and offensive permission
3. default JSON does not contain heavy `evaluations`

**Step 2: Run test to verify it fails**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py
```

Expected: FAIL because the snapshot is still heavy and does not expose a compact structure.

**Step 3: Write minimal implementation**

Implement compact snapshot shaping in `src/service/analysis_service.py` and keep CLI JSON output bound to that compact result.

**Step 4: Run test to verify it passes**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/service/analysis_service.py src/main.py tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py
git commit -m "feat: compact validation snapshot output"
```

### Task 2: Add failing tests for WebUI validation panel

**Files:**
- Modify: `src/web/api.py`
- Modify: `src/web/templates.py`
- Create: `tests/test_web_validation_api.py`

**Step 1: Write the failing test**

Add tests proving:

```python
def test_validation_api_returns_compact_snapshot(...):
    ...

def test_dashboard_template_contains_validation_panel():
    ...
```

The assertions should verify:

1. `/api/validation` returns a compact snapshot
2. HTML contains a validation panel container and fetch logic

**Step 2: Run test to verify it fails**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_web_validation_api.py
```

Expected: FAIL because the route and UI panel do not exist yet.

**Step 3: Write minimal implementation**

Implement:

1. `GET /api/validation?mode=swing`
2. lightweight card in dashboard HTML
3. client-side fetch to render compact snapshot

**Step 4: Run test to verify it passes**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_web_validation_api.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/web/api.py src/web/templates.py tests/test_web_validation_api.py
git commit -m "feat: add validation panel to web dashboard"
```

### Task 3: Add failing tests for reporter hint lines

**Files:**
- Modify: `tests/test_swing_rendering.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`

**Step 1: Write the failing test**

Extend rendering tests so they verify:

1. Feishu and Telegram show sample counts
2. they show offensive permission in plain language

**Step 2: Run test to verify it fails**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_swing_rendering.py
```

Expected: FAIL because reporters do not yet render the compact validation hint.

**Step 3: Write minimal implementation**

Render one concise line such as:

`真实样本: 0 | 历史样本: 20日189笔 | 进攻权限: 关闭（样本不足）`

**Step 4: Run test to verify it passes**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_swing_rendering.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/reporter/feishu_client.py src/reporter/telegram_client.py tests/test_swing_rendering.py
git commit -m "feat: add validation hint lines to swing outputs"
```

### Task 4: Update docs and run final verification

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-25-validation-panel-design.md`
- Modify: `docs/plans/2026-03-25-validation-panel.md`

**Step 1: Update docs**

Document:

1. compact JSON behavior
2. WebUI validation panel
3. how to use it for acceptance

**Step 2: Run focused verification**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py tests/test_web_validation_api.py tests/test_swing_rendering.py
```

Expected: PASS

**Step 3: Run full verification**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m pytest -q tests
```

Expected: PASS

**Step 4: Run manual verification**

Run:

```bash
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m src.main --mode swing --validation-report
/Users/lan/Desktop/code/ai_sentiney/.venv/bin/python -m src.main --mode swing --validation-report --output json
```

Expected:

1. text output readable
2. JSON output compact and parseable
3. WebUI can fetch `/api/validation`

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-25-validation-panel-design.md docs/plans/2026-03-25-validation-panel.md src/service/analysis_service.py src/web/api.py src/web/templates.py src/reporter/feishu_client.py src/reporter/telegram_client.py tests/test_analysis_service_swing_mode.py tests/test_main_validation_report.py tests/test_web_validation_api.py tests/test_swing_rendering.py
git commit -m "feat: add validation panel and compact snapshot"
```
