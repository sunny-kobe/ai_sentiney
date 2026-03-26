# Strategy Lab Design

**Date:** 2026-03-26

## Goal

在现有 `validate / experiment / backtest / walkforward / diagnostics` 能力之上，新增一个真正面向“验证投资猜想”的实验台。

这个实验台不再只回答“历史表现好不好”，而是回答：

- 如果把某条规则改掉，结果会不会更好
- 如果调参数，收益和回撤会怎么变化
- 如果调整组合构建约束，整体曲线会不会更稳

一句话：把“拍脑袋改策略”变成“基于证据做策略实验”。

## Why This Matters

当前系统已经能做三件关键事：

1. 生成中期 `swing` 报告
2. 跑历史验证、正式回测、walk-forward
3. 用 grouped diagnostics 找出最近是哪类动作在拖后腿

但它还缺最后一个闭环：

- 用户发现问题
- 用户提出猜想
- 系统快速模拟“改法 A vs 改法 B”
- 系统明确给出差异
- 用户决定是否把 candidate 升级为主策略

如果没有这个闭环，当前 diagnostics 只能说明“哪里错了”，却不能高效回答“改成什么更好”。

## Current Gaps

### 1. `validate` 更像审计，不像实验

`validate` 只能对单一策略快照给出结论，不能天然表达：

- baseline 是什么
- candidate 改了什么
- 改动前后差异在哪里

### 2. `experiment` 还是 preset 入口，不够结构化

当前 `experiment` 能指定 `preset`，但表达能力有限：

- 不适合同时承载规则改动、参数改动、组合改动
- 很难继续扩展成一个“稳定实验接口”

### 3. 没有统一的实验配置模型

目前系统缺少一个统一对象来表达：

- 规则覆盖
- 参数覆盖
- 组合约束
- 评分口径
- baseline/candidate 对比关系

没有这个层，后面所有实验能力都会散落在 CLI 参数和 service helper 里。

## Options

### Option A: 继续扩展 `experiment`

优点：

- 改动最小
- 复用现有入口最快

缺点：

- 命令会迅速变成参数地狱
- `validate` / `experiment` / `lab` 的职责边界会越来越混
- 后续做批量对比会非常难维护

### Option B: 新增独立 `lab` 子命令

优点：

- 对外语义清晰：`validate` 看现在，`lab` 看假设
- 能用统一实验配置模型承载规则、参数、组合三类实验
- 便于后续扩展对比矩阵、批量实验和推荐改动

缺点：

- 需要新建一层 request/result 模型
- 需要在 CLI 和 service 层加一个新入口

### Option C: 完全配置文件驱动

优点：

- 表达能力最强
- 适合批量实验

缺点：

- 第一版太重
- 用户反馈慢，不适合当前“快速验证猜想”的工作方式

## Decision

选择 Option B。

第一版新增 `lab` 命令，但底层尽量复用现有 `ValidationService`、回测引擎和 diagnostics 数据。

同时采用：

- `preset + override` 作为输入模式
- `baseline vs candidate` 作为输出核心
- 综合评分为默认排序，同时保留收益、超额、回撤、样本数明细

## Scope

第一版覆盖三类实验：

### 1. 规则对比

例如：

- 防守期把 `持有` 降级为 `减配`
- 只保留高置信度 `增配`
- 屏蔽某些 `cluster`
- 对高波动组提早降级

### 2. 参数调优

例如：

- 主观察窗口从 `20` 调到 `10/40`
- 回撤阈值从 `-8%` 调到 `-6%`
- 进攻/防守切换门槛微调

### 3. 组合构建

例如：

- 只保留 `portfolio + top1 watchlist`
- 宽基做核心仓，风险 cluster 只保留 leader
- aggressive / balanced 组合模板对比

第一版不做：

- WebUI 面板
- 自动选择最优 candidate 并回写主策略
- 批量网格搜索
- 自动生成太多花哨图表

## Target UX

### CLI

```bash
python -m src.main lab --preset aggressive_midterm
python -m src.main lab --preset defensive_exit_fix --group-by action
python -m src.main lab --preset broad_beta_core --override confidence_min=高
python -m src.main lab --preset aggressive_midterm --override hold_in_defense=degrade,cluster_blocklist=small_cap
python -m src.main lab --preset aggressive_midterm --output json
```

### Text Output

第一版文本输出分四段：

1. baseline 摘要
2. candidate 摘要
3. diff 摘要
4. 投资者结论

示例风格：

`candidate 相比 baseline，多赚 2.4%，超额提升 1.8%，最大回撤减少 3.1%，主要改善来自防守期持有组不再拖累；代价是交易次数增加 6 笔。`

## Data Model

### LabRequest

第一版统一实验请求对象：

- `mode`
- `preset`
- `days / date_from / date_to`
- `codes`
- `group_by`
- `scoring_mode`
- `overrides`

其中 `overrides` 按三类组织：

- `rule_overrides`
- `parameter_overrides`
- `portfolio_overrides`

### LabPreset

预置实验场景负责定义 candidate 的默认改法，例如：

- `aggressive_midterm`
- `defensive_exit_fix`
- `high_conf_only`
- `broad_beta_core`
- `risk_cluster_filter`

每个 preset 都必须能序列化成清晰的“本次实验改了什么”。

### LabResult

统一输出：

- `baseline`
- `candidate`
- `diff`
- `score`
- `winner`
- `summary_text`
- `diagnostics`
- `request`

## Evaluation Model

第一版继续沿用已有三块证据：

1. `scorecard`
2. `deterministic backtest`
3. `walk-forward`

但实验台要新增一个“对比层”：

- baseline 和 candidate 都跑同一组样本
- 输出逐项差值
- 再做综合评分

### Default Score

默认综合评分不只看收益。

第一版建议：

- 收益 35%
- 超额 30%
- 回撤 25%
- 样本与稳定性 10%

如果 candidate 收益略高，但回撤明显更差，不应轻易判胜。

## Architecture

### 1. CLI Layer

`main.py` 新增 `lab` 子命令。

职责：

- 解析 `preset + override`
- 选择 text/json 输出
- 调用新的实验服务入口

### 2. Service Layer

新增独立 `StrategyLabService`。

职责：

- 解析 preset
- 生成 baseline / candidate spec
- 对同一历史样本构建两套 synthetic records
- 跑 validation/backtest/walkforward
- 生成 diff 和结论

不建议把所有实验逻辑继续堆进 `ValidationService`，否则这个类会逐渐变成“大一统垃圾桶”。

### 3. Variant Builder Layer

新增“策略变体构建”层，把 candidate 的改动以纯数据方式表达。

它不直接改全局主策略，而是：

- 根据 baseline actions 做后处理
- 或在生成 synthetic actions 时应用局部覆盖

这个层是实验台真正的核心，因为它决定 candidate 改动是否稳定可复现。

### 4. Reuse Existing Validation Pipeline

实验台不重写回测逻辑，而是复用已有：

- synthetic record building
- scorecard
- deterministic backtest
- walk-forward
- grouped diagnostics

这样 baseline / candidate 才能用同一把尺子比较。

## Candidate Mutation Strategy

第一版推荐优先做“后处理型 candidate”。

也就是：

1. 先按当前规则生成 baseline actions
2. 再用 candidate mutation 对 actions 做局部变换
3. 用变换后的 actions 构造 candidate synthetic records

这样有三个好处：

- 实现快
- 风险低
- 容易解释“这次实验改了什么”

第一版不要急着把所有 candidate 都下沉到核心打分函数，否则实验层会和生产策略层过度耦合。

## Diagnostics in Lab

实验台应天然复用 grouped diagnostics，但要支持 diff 视角：

- baseline 的拖累组是谁
- candidate 的拖累组是谁
- 哪个拖累组被改善了

这能让实验结果不只输出“更好/更差”，还能输出“为什么更好/更差”。

## Error Handling

必须清晰区分：

- preset 不存在
- override 非法
- 样本不足，无法比较
- baseline 和 candidate 差异太小，不应强行宣布胜者

如果差异不显著，应该输出：

`当前样本下 candidate 没有形成足够明确优势，先别升级为主策略。`

## Success Criteria

第一版完成后，应满足：

1. 用户可以用一个统一命令发起规则/参数/组合实验。
2. 系统能同时输出 baseline、candidate、diff 和综合结论。
3. grouped diagnostics 能解释 candidate 改善或恶化来自哪里。
4. 结果足够清晰，能直接支持“是否升级为主策略”的决策。
