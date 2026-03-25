# Validation Panel Design

## Goal

把现有 `swing` 验证结果从“能算出来”提升到“能被快速读懂、能被直接验收”。

本轮只做三个直接影响使用体验的点：

1. WebUI 增加只读验证面板。
2. `--validation-report --output json` 改成压缩版快照，而不是输出整份重型统计。
3. 飞书 / Telegram 的 `swing` 报告补一行验证计数提示，明确真实样本和历史样本分别是多少。

## Current Gap

现在虽然已经有 `build_validation_snapshot()`，但仍有三个明显问题：

1. JSON 输出过大，默认包含完整 `evaluations`，不适合脚本消费，也不适合验收。
2. WebUI 看不到验证状态，仍然要靠 CLI。
3. 推送里只有一句验证摘要，没有把“真实样本是否足够”直接说清楚。

这会导致用户知道系统“在验证”，但不知道：

- 当前真实建议样本有多少
- 现在的结论主要来自真实跟踪还是 synthetic 历史重建
- 当前进攻权限是开还是关

## Options

### Option A: 新建独立 validation dashboard 页面和复杂前端组件

优点：

- 可视化最好。

缺点：

- 改动面过大，本轮不是必须。

### Option B: 在现有 WebUI 上加一个轻量验证卡片，并把 snapshot 统一压缩

优点：

- 改动小，收益高。
- CLI / WebUI / 推送可以共用同一份 compact snapshot。

缺点：

- 展示依然偏文本，不是图表化面板。

### Option C: 只压缩 JSON，不碰 WebUI 和推送

优点：

- 实现最快。

缺点：

- 用户端感知提升不明显。

## Decision

选 Option B。

理由：

1. 它能最快把“验证是否可信”暴露给用户。
2. WebUI、CLI、推送共享同一份 compact snapshot，后续也更容易扩成图表。
3. 不需要重写前端框架，也不需要引入额外依赖。

## Design

### 1. Compact Validation Snapshot

`build_validation_snapshot("swing")` 返回两层数据：

1. `summary_text` / `text`
2. `compact`

`compact` 只保留高价值字段：

- `verdict`
- `live_sample_count`
- `live_primary_window`
- `synthetic_sample_count`
- `synthetic_primary_window`
- `backtest_trade_count`
- `walkforward_segment_count`
- `offensive_allowed`
- `offensive_reason`

不再默认返回：

- `scorecard.evaluations`
- 大段逐笔窗口明细

如果以后需要完整诊断，再单独加 `--verbose-validation`，但不在本轮范围。

### 2. WebUI Validation Panel

在现有 Dashboard 上新增：

1. 一个“验证状态”卡片
2. 页面加载时自动请求 `/api/validation?mode=swing`
3. 显示：
   - 当前结论
   - 真实建议样本
   - synthetic 样本
   - 是否允许进攻
   - 更新时间

不做复杂图表，不加新页面，就在当前 Dashboard 里补一块状态区。

### 3. Reporter Hint Line

飞书 / Telegram 的 `swing` 报告在 `验证摘要` 下补一行简短计数：

示例：

`真实样本: 0 | 历史样本: 20日189笔 | 进攻权限: 关闭（样本不足）`

这样用户不用看 JSON，也能立刻知道当前验证到底靠什么。

### 4. CLI JSON Behavior

`python -m src.main --mode swing --validation-report --output json`

默认输出 compact snapshot，不再吐完整 scorecard。

CLI 纯文本仍保留自然语言总结，不改使用方式。

## Data Flow

1. `AnalysisService.build_validation_snapshot("swing")`
2. 内部生成 `validation_report`
3. 压缩成 `compact`
4. 提供给：
   - CLI `--validation-report`
   - Web `/api/validation`
   - reporter hint line

## Testing

重点覆盖：

1. snapshot 默认不包含重型 `evaluations`
2. `/api/validation` 返回 compact snapshot
3. Web template 能渲染 validation panel 占位与请求逻辑
4. 飞书 / Telegram 出现样本计数提示

## Success Criteria

本轮完成的标准：

1. `validation-report --output json` 明显变轻，可直接脚本消费。
2. WebUI 能看到验证状态，而不是只看到分析结果。
3. 飞书 / Telegram 能直接看出真实样本和进攻权限。
