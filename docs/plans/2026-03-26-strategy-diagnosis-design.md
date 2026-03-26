# Strategy Diagnosis Design

**Date:** 2026-03-26

## Goal

在现有历史验证能力之上，新增“策略失效诊断”层，让系统不只回答“最近有没有跑赢”，还要回答“最近到底是哪里在拖后腿”。

这轮改造只做一件事：

- 把 `swing` 的历史验证结果按 `动作 / 资产类型 / 市场状态 / 置信度` 分组，直接指出最近亏损来源和可能的规则问题。

## Why This Matters

上一轮已经把历史验证入口打通，当前系统已经可以输出：

- 时间区间验证
- preset 实验
- 回测收益 / 最大回撤 / 交易笔数
- walk-forward 摘要

但现在还有一个关键缺口：

系统能说“最近这套中期动作不占优”，却不能说明：

- 是 `增配` 组在亏，还是 `持有` 组在亏
- 是小盘 / AI / 半导体拖后腿，还是宽基本身也在失效
- 是在 `防守` 市场里做错了，还是 `进攻` 市场里过于保守
- 是高置信度判断也在错，还是低置信度噪声太多

没有这层诊断，后续策略优化只能靠感觉改规则，容易继续发散。

## Current Gaps

### 1. Validation Result 缺结论分解

当前 `ValidationService` 能给出整体摘要和 compact snapshot，但整体结果仍偏“组合级总分”，不够支持规则调优。

### 2. Existing Scorecard 只覆盖有限分组

现在 scorecard 已支持整体、动作、置信度等统计，但还不够：

- 缺少 `cluster` 维度
- 缺少 `market_regime` 维度
- 缺少一个专门面向“找拖后腿原因”的摘要层

### 3. CLI 无法直接做诊断

目前命令能验证区间，但还不能直接输出类似：

`最近 60 天主要亏损来自：防守期仍持有高波动标的、小盘持有组回撤过大、半导体减配动作不够早。`

## Options

### Option A: 继续手动读 JSON / scorecard 明细

优点：

- 实现最快
- 不需要新增领域对象

缺点：

- 仍然需要人工二次分析
- 无法形成稳定的策略优化闭环
- 用户体验差，不适合作为日常诊断工具

### Option B: 在 ValidationService 里新增一层 grouped diagnostics

优点：

- 直接复用现有历史验证数据和 scorecard 明细
- 成本低，收益高
- 能产出稳定的 `top drag / strongest bucket / regime mismatch` 结论
- 最适合下一轮策略优化

缺点：

- 需要给历史评估样本补 `cluster`、`regime` 这类元数据
- 需要新增一套文本摘要逻辑

### Option C: 单独做 Web dashboard / notebook 分析台

优点：

- 视觉效果最好
- 后续扩展空间大

缺点：

- 本轮不是主要问题
- 当前最缺的是“先得知道错在哪”，不是“先把图做漂亮”

## Decision

选择 Option B。

理由：

1. 它直接回答当前最关键的问题：最近到底是哪些决策类型在出错。
2. 它不需要重新设计回测引擎，只需在现有验证结果上增加诊断层。
3. 它能为下一轮真正的策略调优提供依据，而不是继续凭感觉改规则。

## Scope

本轮只覆盖 `swing`，且只做 CLI / JSON：

- `group_by=action`
- `group_by=cluster`
- `group_by=regime`
- `group_by=confidence`

本轮不做：

- 新的 WebUI 面板
- 图表化 dashboard
- 自动规则改写
- 多模式统一诊断

## Target Design

### 1. Diagnostic Observation Layer

在现有 scorecard evaluation 明细之上，新增一层“诊断观察样本”抽象。

每条 observation 至少包含：

- `code`
- `name`
- `action_label`
- `confidence`
- `cluster`
- `market_regime`
- `window`
- `absolute_return`
- `relative_return`
- `max_drawdown`

这样后续所有分组诊断都基于统一样本，不再在 CLI 层临时拼字段。

### 2. Group Dimensions

首批支持四个分组维度：

#### `action`

回答：

- 最近主要亏损来自 `增配 / 持有 / 减配 / 回避` 的哪一组
- 系统是“进攻错了”还是“防守错了”

#### `cluster`

回答：

- 宽基、小盘、AI、半导体、贵金属、个股中，哪一组拖后腿

`cluster` 直接复用现有 `infer_cluster()` 逻辑，避免重复定义资产类型。

#### `regime`

回答：

- 在 `进攻 / 均衡 / 防守 / 撤退` 哪种市场状态下，策略整体表现最差

这用于判断是否存在明显的“市场状态误判”或“状态下的动作模板不匹配”。

#### `confidence`

回答：

- 高置信度组是不是也在亏
- 是否存在“低置信度噪声过多”的问题

### 3. Aggregation Rules

每个分组至少输出：

- `sample_count`
- `avg_absolute_return`
- `avg_relative_return`
- `avg_max_drawdown`
- `win_rate`（如可稳定定义）

默认主窗口继续用 `20` 日；如 `20` 日样本不足，再回退 `10` 日，再考虑 `40` 日。

### 4. Diagnosis Summary

新增 investor-facing 诊断摘要，优先回答三件事：

1. 最近最大的拖累来自哪里
2. 最近相对最稳的部分来自哪里
3. 下一轮规则优先应该改什么

示例风格：

`最近 60 天主要亏损不是来自加仓，而是来自防守期仍继续持有高波动方向。拖累最大的组是小盘持有组，20 日平均收益 -4.6%，平均落后基准 1.9%，平均回撤 -11.2%。相对更稳的是宽基减配组，说明当前更像是“退出不够快”，而不是“进攻太多”。`

### 5. CLI Shape

继续复用 `validate` 命令，不新增独立 `diagnose` 命令。

新增参数：

```bash
python -m src.main validate --mode swing --days 60 --group-by action
python -m src.main validate --mode swing --days 90 --group-by cluster --output json
python -m src.main validate --mode swing --from 2026-02-01 --to 2026-03-25 --group-by regime
python -m src.main experiment --preset aggressive_midterm --group-by action
```

默认行为：

- 如果没有 `--group-by`，保持当前验证结果
- 如果指定 `--group-by`，在保留整体摘要的同时，追加诊断摘要和分组表

### 6. JSON Shape

在现有 validation result 上新增：

- `diagnostics.summary_text`
- `diagnostics.group_by`
- `diagnostics.primary_window`
- `diagnostics.groups[]`
- `diagnostics.top_drag`
- `diagnostics.top_strength`

这样 CLI 和后续 WebUI 都能直接复用。

## Data Flow

1. `main.py` 解析 `--group-by`
2. `ValidationService` 构建完整 validation result
3. 从 scorecard evaluations / synthetic context 生成 observation rows
4. 按指定维度聚合
5. 生成 diagnosis summary
6. CLI / JSON 输出

## Error Handling

需要清晰区分：

- 没有诊断维度
- 有诊断维度但样本不足
- 有诊断结果且明确存在拖累组

不能把这三种情况都写成“暂无统计”。

## Testing

重点验证：

1. `action` 分组能正确聚合样本数、收益、超额、回撤
2. `cluster` 分组使用的分类稳定
3. `regime` 分组能识别不同市场状态
4. `--group-by` 不影响原有 `validate` / `experiment` 兼容性
5. 文本摘要能稳定指出 `top_drag`

## Success Criteria

本轮完成后，应满足：

1. 用户可以直接看出最近最大的亏损来源属于哪一类决策。
2. 系统能明确区分“进攻错了”还是“防守错了”。
3. CLI / JSON 能稳定输出 grouped diagnostics。
4. 下一轮策略优化可以基于诊断结果定向修改，而不是继续拍脑袋改规则。
