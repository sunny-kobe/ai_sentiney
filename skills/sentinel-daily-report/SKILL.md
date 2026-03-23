---
name: sentinel-daily-report
description: Use when generating or publishing Project Sentinel midday or close reports and report quality must be checked before AI narration or publishing.
---

# Sentinel Daily Report

## 目标

为 `midday` / `close` 日报提供统一的质量门禁、结构化证据输出和降级策略，避免在数据不完整或证据不足时直接生成自由叙事报告。

## 质量门禁

生成日报前必须检查：

- 是否交易日
- `context_date` 是否为当日
- 是否有持仓数据
- 指数/广度是否存在
- 是否有消息证据

门禁结果：

- `normal`: 正常生成结构化报告 + AI 解释
- `degraded`: 仅发结构化快报，允许无 AI 解释
- `blocked`: 终止日报生成

## degraded 策略

当以下情况出现时进入 `degraded`：

- 数据不是当日
- 新闻证据不足
- AI 输出覆盖率不足
- AI 调用失败但结构化证据仍可用

`degraded` 模式必须：

- 明确标注 `quality_status = degraded`
- 展示数据时间
- 展示来源标签
- 使用规则引擎操作建议，不让模型自由决定信号

## 报告内容要求

日报至少包含：

- 市场概况
- 每只持仓的 `signal`
- 确定性 `operation`
- `tech_evidence`
- `news_evidence`
- `source_labels`
- `data_timestamp`

## 验证命令

```bash
../../.venv/bin/python -m pytest -q tests/test_report_quality.py tests/test_structured_report.py tests/test_analysis_service_quality_flow.py tests/test_report_rendering_quality.py tests/test_project_skill_files.py
../../.venv/bin/python -m pytest -q tests
../../.venv/bin/python -m src.main --mode midday --replay --dry-run
```

## 发布规则

- `blocked`: 不发布
- `degraded`: 允许发布，但标题和正文必须明确说明是结构化快报
- `normal`: 正常发布
