# Trading-Day Reporting Reliability Design

**Date:** 2026-03-19

## Goal

修正项目在交易日报告上的关键正确性问题，覆盖交易日判定、统计窗口口径、午盘/收盘信号追踪口径、规则引擎与最终报告的一致性，以及本地测试可运行性。

## Scope

- 统一交易日守卫，避免非 A 股交易日自动发报告。
- 将“最近 N 天”统计修正为“最近 N 个唯一交易日”。
- 区分“隔日验证”和“当日午盘到收盘验证”两类 scorecard。
- 让规则引擎输出成为报告中的权威信号字段。
- 修复失真的报告相关测试，并补充可执行的本地验证路径。

## Non-Goals

- 不重做整个分析架构。
- 不替换 Gemini SDK 或大改 Prompt 体系。
- 不重构 WebUI/API。

## Design

### 1. Trading Day Guard

新增一个轻量交易日工具模块，基于 `akshare` 交易日历接口判断当天是否为 A 股交易日，并提供降级策略：

- 优先使用交易日历接口做精确判断。
- 接口异常时退化为工作日判断，并显式标记为 fallback。
- CLI 主流程在 `publish/replay/normal run` 前统一检查。
- GitHub Actions 和本地 cron 脚本改为先执行“是否交易日”检查，再决定是否运行。

### 2. Unique Trading-Day Persistence Semantics

数据库读取口径从“最近 N 条记录”切换为“最近 N 个唯一日期的最新记录”：

- 为 `get_last_analysis` / `get_records_range` / 新增按日期取最近记录的方法统一语义。
- 同一交易日多次重跑时，只保留该日期最新一条作为统计样本。
- 趋势分析、准确率报告、scorecard 都建立在该语义之上。

### 3. Scorecard Split

把当前混乱的 scorecard 拆成两种明确模式：

- `overnight_followup`: 昨日午盘信号 vs 今日午盘涨跌，用于午盘报告和准确率统计。
- `intraday_followup`: 今日午盘信号 vs 今日收盘涨跌，用于收盘报告。

报告展示文案同步更改，避免把“今日午盘到收盘验证”误说成“昨日验证”。

### 4. Rule Engine as Source of Truth

`DataProcessor.generate_signals()` 产出的 `signal/confidence/tech_summary` 视为系统信号真值：

- `post_process_result()` 统一把这些字段覆盖进 AI actions。
- AI 保留 `reason/today_review/tomorrow_plan/bull_case/bear_case` 等解释性内容。
- 这样报告中的信号标签、统计逻辑、追踪逻辑、渲染分组口径一致。

### 5. Testability

修复和补齐测试：

- 把错误的 `from src.main import post_process_result` 改为面向 `AnalysisService`。
- 新增 DB 去重读取、scorecard 模式区分、规则字段覆盖、publish target 字符串容错、交易日守卫的测试。
- 提供本地最小运行路径：优先 `python3 -m unittest`，必要时安装缺失依赖后再跑。

## Risks

- `akshare` 交易日历接口在本地/CI 可能失败，因此需要 fallback，且测试要 mock。
- 改 DB 读取语义后，旧记录统计结果会变化，这是预期修正，不是回归。
- 强制以规则引擎覆盖 AI 信号后，部分历史报告文风会变化，但一致性更高。
