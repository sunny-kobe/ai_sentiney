# Reporting Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复交易日报告链路中的交易日判定、统计窗口、scorecard 口径和权威信号字段问题，并恢复本地可运行测试。

**Architecture:** 在现有架构上做定点修复，不重做分析流程。新增交易日工具模块，收紧数据库“最近 N 日”语义，拆分午盘/收盘 scorecard 口径，并在后处理阶段以规则引擎输出覆盖 AI 信号字段。

**Tech Stack:** Python 3, sqlite3, akshare, unittest/pytest-style tests, GitHub Actions, shell cron

---

### Task 1: Add Trading Day Guard

**Files:**
- Create: `src/utils/trading_calendar.py`
- Modify: `src/service/analysis_service.py`
- Modify: `.github/workflows/daily_sentinel.yml`
- Modify: `scripts/setup_cron.sh`
- Test: `tests/test_trading_calendar.py`

**Step 1: Write the failing test**

写测试覆盖：
- 接口返回交易日时应允许执行
- 接口返回非交易日时应跳过执行
- 接口异常时退化为工作日判断

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_trading_calendar`

Expected: FAIL because module/function does not exist yet.

**Step 3: Write minimal implementation**

实现：
- `is_trading_day(target_date=None) -> dict`
- `should_run_market_report(mode, publish, target_date=None) -> dict`
- 在 `AnalysisService.run_analysis()` 中使用守卫并返回清晰 skip 结果
- 工作流和 cron 改为显式调用交易日检查

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_trading_calendar`

Expected: PASS

### Task 2: Fix Unique Trading-Day Query Semantics

**Files:**
- Modify: `src/storage/database.py`
- Test: `tests/test_database_records.py`

**Step 1: Write the failing test**

写测试覆盖：
- 同一天多条记录时，`get_records_range(..., days=2)` 只返回两个唯一日期
- 每个日期返回该日期最新一条记录

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_database_records`

Expected: FAIL because current SQL returns raw latest N rows.

**Step 3: Write minimal implementation**

实现按日期分组选最新记录的查询逻辑，并保持现有返回结构兼容。

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_database_records`

Expected: PASS

### Task 3: Split Scorecard Modes

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/processor/signal_tracker.py`
- Test: `tests/test_signal_scorecard_modes.py`

**Step 1: Write the failing test**

写测试覆盖：
- `midday` 报告使用“昨日午盘 -> 今日午盘”
- `close` 报告使用“今日午盘 -> 今日收盘”
- 展示文案与 scorecard mode 一致

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_signal_scorecard_modes`

Expected: FAIL because current implementation always pulls latest midday as “yesterday”.

**Step 3: Write minimal implementation**

实现：
- scorecard mode 参数
- 取指定日期/上一个交易日的记录
- 构建不同标题和 summary 文案

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_signal_scorecard_modes`

Expected: PASS

### Task 4: Make Processor Signal Authoritative in Reports

**Files:**
- Modify: `src/service/analysis_service.py`
- Modify: `src/reporter/feishu_client.py`
- Modify: `src/reporter/telegram_client.py`
- Test: `tests/test_report_enhancement.py`

**Step 1: Write the failing test**

写测试覆盖：
- 后处理会覆盖 AI action 中的 `signal/confidence/tech_summary/current_price/pct_change_str`
- Feishu/Telegram 按覆盖后的 signal 分组或展示

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_report_enhancement`

Expected: FAIL because current test imports stale symbol and code does not fully override signal fields.

**Step 3: Write minimal implementation**

让 `post_process_result()` 始终以 processor 结果覆盖同 code action 的关键信号字段。

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_report_enhancement`

Expected: PASS

### Task 5: Harden Publish Target Input

**Files:**
- Modify: `src/service/analysis_service.py`
- Test: `tests/test_publish_target.py`

**Step 1: Write the failing test**

补充字符串/列表两种 `publish_target` 输入都能正确路由的测试。

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_publish_target`

Expected: FAIL because string input iterates by character.

**Step 3: Write minimal implementation**

在服务层统一规范化 `publish_target` 为列表。

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_publish_target`

Expected: PASS

### Task 6: End-to-End Local Verification

**Files:**
- Modify: `tests/verify_full_flow.py`
- Optionally modify: `requirements.txt`

**Step 1: Write/adjust verification entry**

确保验证脚本依赖可控，最少能在本地无 Gemini 调用场景下跑通 dry-run 或 mock 流程。

**Step 2: Run verification commands**

Run:
- `python3 -m unittest tests.test_trading_calendar`
- `python3 -m unittest tests.test_database_records`
- `python3 -m unittest tests.test_signal_scorecard_modes`
- `python3 -m unittest tests.test_report_enhancement`
- `python3 -m unittest tests.test_publish_target`

**Step 3: If environment is missing dependencies**

安装缺失依赖后重跑，并记录实际通过命令。

**Step 4: Final verification**

Run the full command set fresh and confirm zero failures before claiming completion.
