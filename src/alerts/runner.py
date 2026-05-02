"""
市场异动预警主入口
扫描 → 检测异动 → 搜索相关新闻 → 推送 Telegram
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.alerts.anomaly_detector import Anomaly, AnomalyDetector
from src.alerts.news_searcher import NewsSearcher
from src.reporter.telegram_client import TelegramClient
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger

# 异动类型中文映射
ANOMALY_TYPE_CN = {
    "sharp_move": "价格异动",
    "volume_spike": "放量异动",
    "high_turnover": "换手异常",
}

# 严重程度 emoji
SEVERITY_EMOJI = {
    "critical": "🚨",
    "alert": "⚠️",
    "warning": "📊",
}


class AlertRunner:
    """异动预警运行器"""

    def __init__(self):
        self.config = ConfigLoader().config
        self.detector = AnomalyDetector()
        self.news_searcher = NewsSearcher()
        self.telegram = TelegramClient()
        self.alert_config = self.config.get("alert", {})
        self.state_file = Path("data/alert_state.json")
        self._load_state()

    def _load_state(self):
        """加载上次预警状态（用于去重）"""
        self.last_alerts: Dict[str, str] = {}
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.last_alerts = data.get("last_alerts", {})
            except Exception:
                pass

    def _save_state(self):
        """保存预警状态"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "last_alerts": self.last_alerts,
            "last_scan": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2))

    def _make_alert_key(self, anomaly: Anomaly) -> str:
        """生成异动去重 key"""
        return f"{anomaly.code}:{anomaly.anomaly_type}:{anomaly.severity}"

    def _filter_new_anomalies(self, anomalies: List[Anomaly]) -> List[Anomaly]:
        """过滤掉已经推送过的异动（同类型同级别不重复推送）"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        new_anomalies = []

        for anomaly in anomalies:
            key = self._make_alert_key(anomaly)
            last_date = self.last_alerts.get(key, "")
            # 同一天内不重复推送同类型同级别的异动
            if last_date != today:
                new_anomalies.append(anomaly)
                self.last_alerts[key] = today

        return new_anomalies

    def _build_alert_message(
        self, anomalies: List[Anomaly], news_map: Dict[str, List[Dict[str, str]]]
    ) -> str:
        """构建预警消息"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"🛡️ Sentinel 异动预警", f"时间: {now}", ""]

        # 按标的分组
        by_code: Dict[str, List[Anomaly]] = {}
        for a in anomalies:
            by_code.setdefault(a.code, []).append(a)

        for code, code_anomalies in by_code.items():
            first = code_anomalies[0]
            lines.append(f"{'─' * 20}")
            lines.append(f"{SEVERITY_EMOJI.get(first.severity, '📊')} {first.name}（{code}）")

            for a in code_anomalies:
                type_cn = ANOMALY_TYPE_CN.get(a.anomaly_type, a.anomaly_type)
                lines.append(f"  • [{type_cn}] {a.detail}")

            # 附加相关新闻
            news = news_map.get(code, [])
            if news:
                lines.append(f"  📰 相关新闻:")
                for n in news[:2]:
                    lines.append(f"    - {n['title']}")

            lines.append("")

        return "\n".join(lines)

    async def run(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        执行一次异动扫描
        返回: {"anomalies": [...], "sent": bool, "message": str}
        """
        logger.info("🚀 启动异动预警扫描...")

        # 1. 扫描异动
        anomalies = await self.detector.scan()

        if not anomalies:
            logger.info("✅ 未发现异动")
            return {"anomalies": [], "sent": False, "message": ""}

        # 2. 过滤已推送的
        new_anomalies = self._filter_new_anomalies(anomalies)

        if not new_anomalies:
            logger.info("✅ 发现异动但均已推送过，跳过")
            return {"anomalies": [a.__dict__ for a in anomalies], "sent": False, "message": ""}

        # 3. 搜索相关新闻（只搜有异动的标的）
        search_targets = [
            {"code": a.code, "name": a.name}
            for a in new_anomalies
        ]
        # 去重
        seen = set()
        unique_targets = []
        for t in search_targets:
            if t["code"] not in seen:
                seen.add(t["code"])
                unique_targets.append(t)

        news_map = await self.news_searcher.batch_search(unique_targets)

        # 4. 构建消息
        message = self._build_alert_message(new_anomalies, news_map)

        # 5. 推送
        if dry_run:
            logger.info(f"[DRY RUN] 预警消息:\n{message}")
        else:
            self.telegram._send_message(message)
            logger.info("✅ 预警已推送到 Telegram")

        # 6. 保存状态
        self._save_state()

        return {
            "anomalies": [a.__dict__ for a in new_anomalies],
            "sent": not dry_run,
            "message": message,
        }


async def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Sentinel 市场异动预警")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不推送消息")
    args = parser.parse_args()

    runner = AlertRunner()
    result = await runner.run(dry_run=args.dry_run)

    if result["anomalies"]:
        print(f"\n发现 {len(result['anomalies'])} 个异动:")
        for a in result["anomalies"]:
            print(f"  {SEVERITY_EMOJI.get(a['severity'], '📊')} {a['name']}({a['code']}): {a['detail']}")
    else:
        print("✅ 未发现异动")


if __name__ == "__main__":
    asyncio.run(main())
