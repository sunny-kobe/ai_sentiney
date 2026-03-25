# Live Validation Loop Design

## Goal

让 `swing` 模式的“验证摘要”优先反映系统过去真实发出的建议后来表现如何，而不是只看规则重建样本和回测；同时提供一个可以直接执行的验证入口，方便人工验收。

## Problem

当前项目已经有三类验证能力：

1. 基于历史行情重建规则报告，再做 forward window 统计。
2. 基于重建动作做确定性回测。
3. 基于重建动作做 walk-forward。

这三类验证都能说明“规则在历史上大致如何”，但还缺少一个更贴近真实使用场景的问题：

`系统过去真的发给我的 swing 建议，后面兑现得怎么样？`

这会带来两个实际问题：

1. 报告里“验证摘要”的可信度不够直观，用户很难判断它是不是在自证。
2. 进攻型仓位闸门仍主要依赖 synthetic scorecard，没有优先参考真实建议表现。

## Options

### Option A: 新建规范化 recommendation ledger 表

优点：

- 结构最清晰，方便以后做 dashboard。
- 可以记录每条建议的生命周期和人工执行状态。

缺点：

- 需要数据库迁移、回填、状态同步，落地成本最高。
- 当前仓库已经把 `swing` 建议和行情上下文存进 `daily_records`，重复建设收益有限。

### Option B: 直接复用 `daily_records`，把 `swing` 建议记录和后续 `close` 行情拼起来做真实跟踪

优点：

- 不需要新表，改动面更小。
- 直接基于系统真实发出的 `swing` 报告做统计，可信度更高。
- 可以复用现有 `swing_tracker` 的 forward window 统计能力。

缺点：

- 统计粒度受现有持久化覆盖范围限制。
- 历史正式 `swing` 运行较少时，真实样本会不足。

### Option C: 接入外部回测/分析框架单独做验证中心

优点：

- 能力最强，未来扩展空间最大。

缺点：

- 当前阶段性价比最低。
- 用户当前最缺的是“可被信任的真实建议跟踪”，不是再引入一套更复杂的工具链。

## Decision

选择 Option B。

理由：

1. 它直接回答“过去真实发过的建议后来如何”这个核心问题。
2. 它不依赖新数据源和新数据库迁移，能快速进入稳定可用状态。
3. 它能与现有 synthetic scorecard / backtest / walk-forward 并存，形成“真实跟踪优先，历史重建补充”的验证体系。

## Design

### 1. 实时验证分层

`swing` 验证报告改成两层：

1. `live`: 基于历史 `swing` 报告 + 后续 `close` 行情计算的真实建议跟踪。
2. `synthetic`: 保留现有 scorecard / backtest / walk-forward，作为补充证据。

最终 `validation_report` 结构新增 `live` 字段，并让 `summary_text` 优先引用 `live` 结论；当 `live` 样本不足时，再回退到 synthetic 为主。

### 2. 真实建议跟踪的构造方式

数据来源：

1. `mode='swing'` 的历史记录提供“当日真实建议动作”。
2. `mode='close'` 的历史记录提供建议发出后各交易日的真实价格路径。

实现方式：

1. 读取最近一段时间的 `swing` 记录和 `close` 记录。
2. 按日期合并成一条时间轴记录：
   - `raw_data` 优先用 `close` 当日行情。
   - `ai_result.actions` 用 `swing` 当日动作。
3. 将这条合并后的时间轴送入现有 `build_swing_scorecard`。

这样可直接得到：

- 10/20/40 日 forward return
- 相对基准超额收益
- 最大回撤
- 按动作分类的统计

### 3. 进攻闸门优先级调整

当前 `pullback_resume` 的闸门主要看 synthetic scorecard 与 backtest。

改造后优先级调整为：

1. 如果 `live` 的增配样本已达到最小门槛，优先用 `live.by_action["增配"]` 决定是否允许主动进攻。
2. 如果 `live` 样本不足，再回退到 synthetic scorecard。
3. backtest 继续作为兜底否决项：
   - 总收益不达标时否决。
   - 最大回撤过大时否决。

这样能让“真实建议后来有没有持续跑赢”直接影响加仓权限。

### 4. 验证摘要文案

`validation_summary` 改成 plain language，优先回答三个问题：

1. 真实建议最近兑现得好不好。
2. 如果真实样本还少，历史重建样本怎么看。
3. 当前是否支持继续偏进攻执行。

示例风格：

`真实跟踪近90天已兑现 20 日建议 8 笔，平均跑赢基准 1.6%，增配组平均收益 4.2%。历史回测未见明显恶化，当前可以继续进攻，但仍按分批执行。`

### 5. 验证入口

新增 CLI 入口：

`python -m src.main --mode swing --validation-report`

用途：

1. 不跑完整报告也能直接看验证结果。
2. 方便手动验收和 GitHub Actions 故障排查。
3. 后续 WebUI 如需展示验证卡片，也可以直接复用同一份 snapshot。

### 6. 输出范围

本次改造只增强 `swing`：

1. CLI 文本输出
2. `ask` 准确率问答
3. Feishu / Telegram 的验证摘要

不在本次范围：

1. 新 Web 可视化页面
2. 人工成交回填
3. 独立 recommendation ledger 新表

## Data Flow

1. `run_analysis(mode="swing")`
2. 读取 close 历史 + swing 历史
3. 构建 `live` validation scorecard
4. 构建 synthetic scorecard / backtest / walk-forward
5. 聚合成新的 `validation_report`
6. 将结论注入 `build_swing_report`
7. 输出到 CLI / Feishu / Telegram

## Testing

重点覆盖：

1. `swing + close` 时间轴合并后，真实建议能得到 forward window 统计。
2. `live` 样本充足时，`summary_text` 优先使用 `live` 结论。
3. `live` 样本不足时，自动回退到 synthetic 结论。
4. 进攻闸门优先参考 `live` 增配统计。
5. `--validation-report` 能输出可读结果。

## Success Criteria

满足以下条件即可认为本轮完成：

1. `swing` 报告中的验证摘要优先体现真实历史建议表现。
2. 可以独立执行一条 CLI 命令查看验证结果。
3. 进攻加仓权限不再只看 synthetic 样本。
4. 新增测试覆盖 live validation 主路径并通过全量测试。
