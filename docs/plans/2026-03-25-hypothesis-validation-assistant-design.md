# Hypothesis Validation Assistant Design

**Date:** 2026-03-25

## Goal

把 Sentinel 从“会发日报的中期策略工具”升级成“围绕真实持仓的中期投资助手 + 历史假设验证器”。

这轮重构优先解决两个问题：

1. 用户无法方便地用历史区间验证一个具体猜想。
2. `swing` 报告能读，但还不够可信、可执行、可验收。

## Current Problems

### 1. 验证能力存在，但没有产品级入口

项目已经具备三类底层能力：

- 确定性回测
- walk-forward 验证
- `swing` 历史样本统计

但这些能力现在主要埋在 `AnalysisService` 内部，用户只能通过固定的 `--validation-report` 看最近样本摘要，无法直接回答下面这些实际问题：

- 最近两周如果按当前 `swing` 策略执行，会怎样？
- 某次急跌区间里，系统会不会更早提示撤退？
- 如果只看真实持仓和观察池，过去一个月建议质量如何？

### 2. 验证口径分散，证据不成体系

当前验证结果同时混合：

- `live` 真实建议跟踪
- synthetic 重建样本 scorecard
- 组合级确定性回测
- walk-forward

但缺少一个统一的结果模型把这些证据整理成“同一个结论下的不同证据层”。这导致 CLI、WebUI、推送虽然都能展示验证摘要，但都还不够适合投资决策。

### 3. 报告仍偏系统视角，不够投资者视角

现在的 `swing` 报告已经比早期版本更可读，但仍有几个问题：

- 术语还偏多
- 历史证据与当前动作没有紧密绑定
- 缺少清晰的撤退条件与验证口径说明
- 用户无法快速区分“这是实时结论”还是“这是历史上验证过的倾向”

### 4. 用户无法独立验收策略质量

目前缺的不是再加更多模型，而是一个稳定的验证闭环：

- 指定时间范围
- 指定持仓或观察池
- 输出结论、交易流水、权益曲线、基准对比
- 让用户直接看到“这个猜想在历史上有没有站住”

没有这层能力，报告再精致也难建立信任。

## Product Direction

重构后的产品应首先服务一个中长期、进攻型的投资者。

系统应该：

- 以真实持仓和少量观察池为中心
- 以 `2-12` 周的中期决策为主
- 先给动作，再给证据
- 在进攻上敢给建议，在撤退上给出明确触发条件
- 允许用户对任何历史区间发起验证，而不是被动等待定时报告

系统不应该：

- 继续围绕短线命中率优化
- 把 LLM 当成决策器
- 只给抽象观点，不给历史证据和撤退条件

## Options

### Option A: 在现有 `AnalysisService` 内继续扩展验证参数

优点：

- 改动最少
- 可以最快加出 `--from/--to` 一类入口

缺点：

- 会继续加重 `AnalysisService` 的职责
- 验证、渲染、问答、报告输出仍然耦合
- 后面要补 WebUI / 推送 / 实验 preset 时会越来越难维护

### Option B: 引入独立的假设验证层，复用现有回测内核

优点：

- 能保留现有回测和验证资产
- 可以把“报告生成”和“历史验证”拆成两个一等能力
- 更适合把 CLI、WebUI、推送统一到一套结果协议
- 是当前投入产出比最高的方案

缺点：

- 需要整理现有数据流和结果结构
- 本轮改动会涉及 CLI、服务层、渲染层和测试

### Option C: 直接引入更重的策略/回测框架并做插件化重写

优点：

- 架构上限最高
- 未来支持更多策略实验和资产类型会更容易

缺点：

- 本轮重构成本过高
- 现有业务问题不是“底层回测引擎不够强”，而是“验证能力没产品化”

## Decision

选择 Option B。

理由：

1. 它直接解决“如何用历史验证我的猜想”这个当前最关键的问题。
2. 它复用已有回测资产，不会无谓推倒重来。
3. 它能在一轮重构里同时改善准确性、可解释性和可验收性。

## Target Architecture

### 1. 双主能力结构

系统拆成两条主链路：

1. `analysis`: 负责生成当前 `swing` / `morning` / `midday` / `close` 报告。
2. `validation`: 负责历史区间验证、实验回放、证据聚合和结果导出。

`analysis` 消费 `validation` 产出的摘要，不再自己拼接各类验证逻辑。

### 2. Validation Domain

新增独立验证域对象，用统一结构表达结果：

- `request`
- `sample_coverage`
- `benchmark_summary`
- `signal_scorecard`
- `backtest_summary`
- `walkforward_summary`
- `trade_ledger`
- `equity_curve`
- `investor_summary`

这样 CLI、WebUI、推送只需要决定“展示哪一层”，不用各自重复组装数据。

### 3. Experiment / Hypothesis Layer

在验证域之上增加实验层，支持：

- 任意时间区间
- 最近 N 天
- 指定标的集合
- 指定基准
- 指定 preset

首批 preset 只做与当前用户一致的中期场景，例如：

- `aggressive_midterm`
- `defensive_retreat_check`
- `portfolio_focus`

### 4. Report Rendering Redesign

`swing` 报告输出按投资动作重排：

1. 市场判断
2. 账户动作
3. 当前持仓怎么做
4. 观察池里是否值得试仓
5. 什么条件下撤退
6. 历史证据是否支持继续进攻

术语一律压缩成 plain language，不把内部指标命名直接暴露给用户。

### 5. Unified Output Surface

三类输出统一使用一份 compact result：

- CLI
- WebUI
- Feishu / Telegram

默认展示简洁摘要；如需更完整诊断，再通过详细模式拉取交易流水、权益曲线和分窗口结果。

## CLI / API Design

本轮引入明确的历史验证入口，而不是继续扩展 `--validation-report`：

```bash
python -m src.main validate --mode swing --days 60
python -m src.main validate --mode swing --from 2026-02-01 --to 2026-03-25
python -m src.main validate --mode swing --from 2026-03-01 --to 2026-03-20 --codes 510300 512660
python -m src.main experiment --preset aggressive_midterm --days 90
```

兼容性策略：

- 现有 `--validation-report` 保留
- 其内部改走新的验证服务
- 输出仍兼容当前 CLI / WebUI / 推送使用方式

## Data Flow

### 1. 当前报告路径

1. `main.py` 解析普通分析命令
2. `AnalysisService` 生成市场和持仓结论
3. `ValidationService` 提供 compact validation summary
4. report renderer 输出简洁报告

### 2. 历史验证路径

1. `main.py` 解析 `validate` / `experiment`
2. `ValidationService` 组装记录区间和标的范围
3. 底层回测引擎执行 deterministic backtest / walkforward / scorecard
4. 输出结构化结果
5. CLI / JSON / WebUI 使用同一份协议渲染

## Error Handling

需要明确区分三类情况：

1. 样本不足
2. 数据缺失
3. 验证已执行但结果不支持当前动作

报告文案必须把这三类情况说清楚，不能笼统写成“暂无统计”。

## Testing Strategy

本轮测试重点不是覆盖所有市场逻辑，而是覆盖“验证闭环是否可靠”：

1. 日期范围过滤正确
2. 指定代码过滤正确
3. `validate` 命令可输出摘要和 JSON
4. 回测结果包含交易流水和权益曲线
5. 基准超额和最大回撤统计正确
6. `--validation-report` 兼容旧行为但底层走新服务
7. `swing` 报告文案按新结构输出

## Success Criteria

满足以下条件即可认为这轮重构达到目标：

1. 用户可以直接对历史区间发起验证，不必等定时任务。
2. 每次验证能看到收益、超额、回撤、交易次数、交易明细和权益曲线。
3. `swing` 报告能先回答“现在该做什么”，再回答“为什么”。
4. 报告里的历史证据与当前动作一致，不再是松散附注。
5. CLI、WebUI、推送三端展示基于同一份 compact validation result。
6. 本地可跑通核心验证命令，并有自动化测试覆盖主路径。
