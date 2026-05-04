"""
自动研报主入口
聚合数据 → AI 生成研报 → 推送 Telegram
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from chinese_calendar import is_workday

from src.report_gen.data_aggregator import DataAggregator
from src.report_gen.report_generator import ReportGenerator
from src.reporter.telegram_client import TelegramClient
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


class AutoReportRunner:
    """自动研报运行器"""

    def __init__(self):
        self.config = ConfigLoader().config
        self.aggregator = DataAggregator()
        self.generator = ReportGenerator()
        self.telegram = TelegramClient()
        self.state_file = Path("data/report_state.json")
        self._load_state()

    def _load_state(self):
        """加载上次生成状态"""
        self.last_report_date = ""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.last_report_date = data.get("last_report_date", "")
            except Exception:
                pass

    def _save_state(self):
        """保存生成状态"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "last_report_date": self.last_report_date,
            "last_run": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2))

    def _build_telegram_message(self, report: str, data: Dict[str, Any]) -> str:
        """构建 Telegram 消息"""
        timestamp = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))

        # 添加简要市场数据摘要
        market = data.get("market", {}).get("indices", {})
        market_summary = ""
        if market:
            changes = []
            for name, info in market.items():
                change = info.get("change", 0)
                direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                changes.append(f"{name}{direction}{abs(change):.1f}%")
            market_summary = " | ".join(changes[:3])

        lines = [
            f"🔬 Sentinel 每日研报",
            f"时间: {timestamp}",
        ]
        if market_summary:
            lines.append(f"市场: {market_summary}")
        lines.append("")
        lines.append(report)

        return "\n".join(lines)

    async def run(self, dry_run: bool = False, force: bool = False) -> Dict[str, Any]:
        """执行一次研报生成"""
        # 非交易日直接跳过
        today_date = datetime.now().date()
        if not is_workday(today_date):
            logger.info("📅 今日非交易日，跳过研报生成")
            return {"generated": False, "reason": "non_trading_day", "skip_reason": "非交易日"}

        logger.info("🚀 启动自动研报生成...")

        # 检查今天是否已经生成过
        today = datetime.now().strftime("%Y-%m-%d")
        if not force and self.last_report_date == today:
            logger.info("✅ 今日已生成过研报，跳过")
            return {"generated": False, "reason": "already_generated"}

        # 1. 聚合数据
        data = await self.aggregator.aggregate()

        # 2. AI 生成研报
        report = await self.generator.generate(data)

        # 3. 构建消息
        message = self._build_telegram_message(report, data)

        # 4. 推送
        if dry_run:
            logger.info(f"[DRY RUN] 研报:\n{message}")
            pushed = False
        else:
            self.telegram._send_message(message)
            logger.info("✅ 研报已推送到 Telegram")
            pushed = True

        # 5. 保存状态
        self.last_report_date = today
        self._save_state()

        return {
            "generated": True,
            "pushed": pushed,
            "report": report,
            "message": message,
            "data_summary": {
                "indices": len(data.get("market", {}).get("indices", {})),
                "sectors": len(data.get("sectors", {}).get("sectors", {})),
                "portfolio": len(data.get("portfolio", {}).get("portfolio", [])),
                "news": sum(len(v) for v in data.get("news", {}).values()),
                "policy": len(data.get("policy", [])),
                "github": sum(len(v) for v in data.get("github", {}).values()),
            }
        }


async def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Sentinel 自动研报")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不推送消息")
    parser.add_argument("--force", action="store_true", help="强制生成（忽略今日已生成检查）")
    args = parser.parse_args()

    runner = AutoReportRunner()
    result = await runner.run(dry_run=args.dry_run, force=args.force)

    if result.get("generated"):
        print("✅ 研报已生成并推送")
    elif result.get("reason") == "already_generated":
        print("ℹ️ 今日已生成过研报，使用 --force 强制重新生成")
    else:
        print("❌ 研报生成失败")

    if result.get("data_summary"):
        summary = result["data_summary"]
        print(f"\n数据统计:")
        print(f"  指数: {summary['indices']} 个")
        print(f"  板块: {summary['sectors']} 个")
        print(f"  持仓: {summary['portfolio']} 只")
        print(f"  新闻: {summary['news']} 条")
        print(f"  政策: {summary['policy']} 条")
        print(f"  GitHub: {summary['github']} 个仓库")


if __name__ == "__main__":
    asyncio.run(main())
