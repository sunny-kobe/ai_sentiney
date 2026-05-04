# AI Agent 协同工作流指南 v2

> 编排者（Hermes）+ 执行者（Claude Code / Codex）的最佳实践

## 模式概述

```
┌─────────────────────────────────────────────────────────────┐
│                         用户（你）                           │
│                           ↓ 指令                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                  Hermes（编排者）                        ││
│  │                                                         ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              ││
│  │  │ 任务规划  │  │ 进度追踪  │  │ 结果验证  │              ││
│  │  └──────────┘  └──────────┘  └──────────┘              ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              ││
│  │  │ 上下文管理│  │ 错误恢复  │  │ 成本控制  │              ││
│  │  └──────────┘  └──────────┘  └──────────┘              ││
│  └───────────────────────┬─────────────────────────────────┘│
│                          ↓                                   │
│  ┌──────────────────────────────────────────────────────────┐│
│  │              Claude Code + SuperClaude                   ││
│  │                                                          ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐               ││
│  │  │ 读代码   │  │ 改代码   │  │ 跑测试   │               ││
│  │  └──────────┘  └──────────┘  └──────────┘               ││
│  │                                                          ││
│  │  MCP: Tavily / Context7 / Memory / GitHub / Sequential   ││
│  │  Agents: python-expert / quality-engineer / ...          ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 编排者规则（Hermes）

### 1. 任务分解

```
大任务 → 拆成中任务（3-5个）
中任务 → 拆成小任务（每个 5-15 分钟）
小任务 → 传给执行者
```

**原则**：
- **INVEST**：Independent、Negotiable、Valuable、Estimable、Small、Testable
- **垂直切片**：按功能切分，不按技术层切分
- **风险前置**：最不确定的部分先做

### 2. 上下文传递模板

```markdown
## 目标
[一句话描述]

## 约束
- 不要修改 X
- 必须保持向后兼容
- 遵循项目代码规范

## 相关文件
- src/xxx.py（需要修改）
- tests/test_xxx.py（需要更新）

## 验收标准
- [ ] 所有测试通过
- [ ] 无 lint 错误
- [ ] 功能正常工作
```

### 3. 验证循环

```
执行者完成 → 我验证 → 通过？→ 下一个任务
                    → 失败？→ 分析原因 → 重试/拆分
```

### 4. 进度报告

每完成一个里程碑，向用户报告：
- ✅ 完成了什么
- ⏳ 正在做什么
- ❌ 遇到什么问题
- 📊 关键数据（测试数、覆盖率等）

---

## 执行者规则（Claude Code / Codex）

### 1. 接收任务后

```bash
# 1. 先读 CLAUDE.md / AGENTS.md 了解项目
# 2. 运行测试确认基线
python -m pytest tests/ -q

# 3. 开始执行任务
# 4. 每个逻辑单元后验证
# 5. 完成后报告结果
```

### 2. 代码修改原则

| 原则 | 说明 |
|------|------|
| 先读后写 | 修改前先理解现有代码 |
| 最小变更 | 只改必需部分 |
| 保持一致 | 遵循项目风格 |
| 频繁验证 | 每改一点就测试 |
| 原子提交 | 一个逻辑变更一个 commit |

### 3. 错误处理

```
遇到错误 → 记录 → 尝试修复 → 修复成功？→ 继续
                              → 修复失败？→ 报告给编排者
```

---

## 四大改进模式

### 1. TDD 模式（测试驱动开发）

**原则**：先写测试，再写代码

**流程**：
```
Step 1: Hermes 让 Claude Code 写测试
        "为 XXX 功能写测试，覆盖正常/边界/错误场景"
        ↓
Step 2: Hermes 验证测试失败
        python -m pytest tests/test_xxx.py -q
        确认：FAIL（预期）
        ↓
Step 3: Hermes 让 Claude Code 写代码
        "实现 XXX 功能，让所有测试通过"
        ↓
Step 4: Hermes 验证测试通过
        python -m pytest tests/ -q
        确认：PASS
```

**适用场景**：
- 新功能开发
- 边界条件处理
- 需要明确规格的任务

**示例**：
```
Hermes: "为涨跌停检测写测试，覆盖主板/创业板/科创板/ST"
Claude Code: 写 10 个测试
Hermes: 验证测试失败（功能未实现）
Hermes: "实现涨跌停检测，让所有测试通过"
Claude Code: 实现功能
Hermes: 验证测试通过（300 passed）
```

### 2. 并行模式

**原则**：无依赖任务同时执行

**流程**：
```
Step 1: Hermes 分析任务依赖关系
        Task A: 修改 alerts 模块
        Task B: 修改 radar 模块
        Task C: 修改 reporter 模块
        → 三者无依赖，可并行
        ↓
Step 2: Hermes 同时启动多个 Claude Code
        Claude Code 1 → alerts（worktree/alerts）
        Claude Code 2 → radar（worktree/radar）
        Claude Code 3 → reporter（worktree/reporter）
        ↓
Step 3: Hermes 等待所有完成
        ↓
Step 4: Hermes 合并结果
        git merge worktree/alerts
        git merge worktree/radar
        git merge worktree/reporter
        ↓
Step 5: Hermes 验证集成测试
        python -m pytest tests/ -q
```

**适用场景**：
- 多模块独立修改
- 批量任务处理
- 时间紧迫的任务

**命令**：
```bash
# 创建 worktree
git worktree add -b fix/alerts /tmp/alerts main
git worktree add -b fix/radar /tmp/radar main

# 并行启动
claude -p "修改 alerts 模块" --worktree /tmp/alerts &
claude -p "修改 radar 模块" --worktree /tmp/radar &

# 等待完成
wait

# 合并
git merge fix/alerts
git merge fix/radar
```

### 3. 成本控制模式

**原则**：分层模型策略

**策略**：

| 任务类型 | 模型 | 原因 |
|---------|------|------|
| 简单 bug fix | haiku | 快速、便宜 |
| 代码格式化 | haiku | 机械性任务 |
| 一般功能开发 | sonnet | 平衡性能和成本 |
| 复杂重构 | opus | 需要深度推理 |
| 架构设计 | opus | 需要全局思考 |

**实现**：
```bash
# 简单任务用 haiku
claude -p "修复 typo" --model haiku --max-turns 3

# 一般任务用 sonnet（默认）
claude -p "添加日志记录" --max-turns 10

# 复杂任务用 opus
claude -p "重构数据处理管道" --model opus --max-turns 20
```

**Token 节省技巧**：
1. **CLAUDE.md 缓存**：不变的上下文放这里，利用 prompt caching
2. **搜索先行**：先 search 定位，再 edit 修改
3. **粒度控制**：每个任务 1000-3000 output tokens 最佳
4. **提前失败**：前置条件不满足立即失败
5. **/compact**：上下文大了及时压缩

### 4. 错误恢复模式

**原则**：智能分析，分级处理

**流程**：
```
执行失败
    ↓
分析失败类型
    ├── 测试失败 → 分析哪个测试 → 修复该测试
    ├── 编译错误 → 分析错误信息 → 修复语法/导入
    ├── 运行时错误 → 分析堆栈 → 修复逻辑
    └── 超时 → 任务太大 → 拆分重试
    ↓
选择恢复策略
    ├── 策略 1: 直接重试（偶发错误）
    ├── 策略 2: 换个方法（当前方法不行）
    ├── 策略 3: 拆分任务（任务太复杂）
    └── 策略 4: 报告用户（无法自动恢复）
```

**示例**：
```
Claude Code: "重构失败，测试 test_xxx 报错"
Hermes: 分析 → 测试期望旧 API
Hermes: 策略 → 先更新测试，再重构
Hermes: "先更新 test_xxx 适配新 API，然后继续重构"
Claude Code: 更新测试 + 重构
Hermes: 验证通过
```

---

## 工具选择指南

| 场景 | 推荐工具 | 原因 |
|------|---------|------|
| 简单 bug fix | Claude Code `-p` | 快速、一次性 |
| 复杂重构 | Claude Code 交互式 | 需要多轮对话 |
| 并行任务 | Claude Code worktree | 隔离环境 |
| 代码审查 | Claude Code | 理解能力强 |
| 简单代码生成 | Codex | 快速 |
| 配置文件修改 | Hermes 直接改 | 简单任务不值得委派 |
| TDD | Claude Code `-p` | 先写测试再写代码 |

---

## 工作流示例

### 示例 1: TDD 开发新功能

```
用户: "添加涨跌停检测"
    ↓
Hermes: 设计任务
    ↓
Hermes → Claude Code: "写测试，覆盖主板/创业板/科创板/ST"
    ↓
Claude Code: 写 10 个测试
    ↓
Hermes: 验证测试失败（功能未实现）
    ↓
Hermes → Claude Code: "实现功能，让测试通过"
    ↓
Claude Code: 实现 _get_limit_info() + 检测逻辑
    ↓
Hermes: 验证测试通过（300 passed）
    ↓
Hermes: 提交代码
```

### 示例 2: 并行重构多个模块

```
用户: "优化 alerts、radar、reporter 三个模块"
    ↓
Hermes: 分析依赖 → 无依赖，可并行
    ↓
Hermes: 创建 3 个 worktree
    ↓
Hermes: 同时启动 3 个 Claude Code
    Claude Code 1 → alerts
    Claude Code 2 → radar
    Claude Code 3 → reporter
    ↓
Hermes: 等待所有完成
    ↓
Hermes: 合并 + 集成测试
    ↓
Hermes: 提交代码
```

### 示例 3: 成本优化的任务拆分

```
用户: "重构整个项目"
    ↓
Hermes: 拆成 4 批
    第一批: 紧急修复（简单）→ haiku
    第二批: 架构优化（复杂）→ opus
    第三批: 测试补全（中等）→ sonnet
    第四批: 依赖管理（简单）→ haiku
    ↓
Hermes: 按批次执行，每批用合适模型
    ↓
Hermes: 验证 + 提交
```

### 示例 4: 错误恢复

```
Hermes → Claude Code: "重构 XXX"
    ↓
Claude Code: 重构失败，测试报错
    ↓
Hermes: 分析 → 测试期望旧 API
    ↓
Hermes → Claude Code: "先更新测试适配新 API"
    ↓
Claude Code: 更新测试
    ↓
Hermes: 验证测试更新正确
    ↓
Hermes → Claude Code: "继续重构"
    ↓
Claude Code: 完成重构
    ↓
Hermes: 验证通过
```

---

## 常见陷阱

| 陷阱 | 解决方案 |
|------|---------|
| 执行者改太多 | 明确任务边界，只传必要文件 |
| 上下文丢失 | 用 CLAUDE.md 持久化关键信息 |
| 测试失败无人管 | 每个任务必须验证测试 |
| 成本失控 | 设置 max-turns 和 max-budget |
| 权限过大 | 不用 --dangerously-skip-permissions |
| 并行冲突 | 用 worktree 隔离 |
| TDD 流程中断 | 先验证失败再写代码 |
| 错误恢复失败 | 分级处理，必要时报告用户 |

---

## 配置文件

| 文件 | 用途 |
|------|------|
| `CLAUDE.md` | Claude Code 项目指南 |
| `AGENTS.md` | Codex 项目指南 |
| `.cursorrules` | Cursor IDE 规则 |
| `.claude/settings.json` | Claude Code 权限和 hooks |
| `.codex/config.json` | Codex 配置 |
| `docs/WORKFLOW.md` | 本文件 |
