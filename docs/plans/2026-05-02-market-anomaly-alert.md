# 市场异动预警 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 当持仓/观察池标的出现异常放量、急涨急跌、跳空等异动时，自动搜索相关新闻并推送到 Telegram。

**Architecture:** 新增 `src/alerts/` 模块，复用现有 DataCollector 采集数据，新增异动检测引擎，复用 TelegramClient 推送。通过 `--mode alert` CLI 入口触发，后续接入 Hermes cronjob 实现定时监控。

**Tech Stack:** Python, AkShare (数据源), asyncio, 现有 TelegramClient

---

## 异动检测规则 (MVP)

| 规则 | 触发条件 | 严重度 |
|------|---------|--------|
| 放量异动 | 当日成交量 > N倍5日均量 | ⚠️ 中 |
| 急涨急跌 | 日内涨跌幅 > 阈值 (默认3%) | 🔴 高 |
| 跳空缺口 | 开盘价 vs 昨收 > 阻值 (默认2%) | ⚠️ 中 |
| 涨跌停 | 触及涨跌停板 | 🔴 高 |
| MA20突破 | 价格从一侧穿越MA20 | ⚠️ 中 |

---

## Task 1: 新增 alerts 配置段

**Objective:** 在 config.yaml 中添加异动预警的参数配置

**Files:**
- Modify: `config.yaml`

---

## Task 2: 创建异动检测引擎

**Objective:** 实现 `src/alerts/anomaly_detector.py`，核心检测逻辑

**Files:**
- Create: `src/alerts/__init__.py`
- Create: `src/alerts/anomaly_detector.py`

---

## Task 3: 创建异动预警服务

**Objective:** 实现 `src/alerts/alert_service.py`，编排数据采集→检测→搜索新闻→推送

**Files:**
- Create: `src/alerts/alert_service.py`

---

## Task 4: 添加 CLI 入口

**Objective:** 在 main.py 中添加 `--mode alert` 入口

**Files:**
- Modify: `src/main.py`

---

## Task 5: 添加 Telegram 推送格式

**Objective:** 在 TelegramClient 中添加异动预警消息格式

**Files:**
- Modify: `src/reporter/telegram_client.py`

---

## Task 6: 接入 Hermes cronjob

**Objective:** 创建定时任务，盘中每30分钟扫描一次
