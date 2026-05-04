# Hermes 执行架构

ai_sentiney 从 GitHub Actions 迁移到 Hermes Agent 作为主力执行平台。

## 架构说明

```
Hermes Agent (本地 Mac)
    ↓ cron 定时触发
    ↓ 调用 Python CLI
    ↓ 输出 JSON
    ↓ 格式化为 Telegram 消息
    ↓ 推送到用户 Telegram 对话
```

## 定时任务表

| 任务名 | 时间 (CST) | 模式 | 内容 |
|--------|-----------|------|------|
| 早盘简报 | 08:10 | morning | 隔夜外盘映射、A股开盘预判 |
| 午盘分析 | 11:40 | midday | 市场情绪、信号追踪、持仓建议 |
| 尾盘执行 | 15:05 | preclose | 尾盘执行清单（减仓/持有/加仓） |
| 收盘复盘 | 15:10 | close + PE | 收盘复盘 + PE百分位定投监控 |

所有任务仅在交易日运行（周一-周五，自动跳过节假日）。

## PE 百分位监控

`scripts/pe_monitor.py` — 基于 csindex 真实 PE 历史数据（10年+每日）。

监控范围：沪深300、中证500、中证A500（宽基指数）
阈值：A 股适配版 — <30% 定投 / 30-70% 持有 / >70% 分批卖
数据源：csindex index-perf API（历史 PE）+ AkShare（当前 PE-TTM）

注意：PE 百分位仅用于长期定投资金配置，不影响 ai_sentiney 短期交易信号。

## GitHub Actions（已关闭自动定时）

`.github/workflows/daily_sentinel.yml` 仅保留手动触发（workflow_dispatch）作为兜底。
默认推送目标已改为 telegram。

如需手动运行：GitHub → Actions → Run workflow → 选择 mode 和 target。

## 本地开发命令

```bash
# 激活环境
cd /Users/lan/Desktop/code/ai_sentiney && source .venv/bin/activate

# 手动跑各模式
python -m src.main --mode morning --output text
python -m src.main --mode midday --output text
python -m src.main --mode preclose --output text
python -m src.main --mode close --output text
python -m src.main --mode swing --output text

# PE 监控
python3 scripts/pe_monitor.py

# 推送到 Telegram
python -m src.main --mode midday --publish --publish-target telegram
```
