"""
市场异动检测模块
检测：放量、急涨急跌、换手率异常
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.collector.data_fetcher import DataCollector
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


@dataclass
class Anomaly:
    """单个异动事件"""
    code: str
    name: str
    anomaly_type: str  # volume_spike | sharp_move | high_turnover
    severity: str  # warning | alert | critical
    current_price: float
    pct_change: float
    volume: float
    turnover_rate: float
    detail: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


class AnomalyDetector:
    """市场异动检测器"""

    def __init__(self):
        self.config = ConfigLoader().config
        self.alert_config = self.config.get("alert", {})
        self.thresholds = self.alert_config.get("thresholds", {})

        # 默认阈值
        self.price_change_threshold = self.thresholds.get("price_change_pct", 3.0)
        self.volume_ratio_threshold = self.thresholds.get("volume_ratio", 1.5)
        self.turnover_threshold = self.thresholds.get("turnover_rate", 8.0)

        self.collector = DataCollector()

    def _get_watch_targets(self) -> List[Dict[str, Any]]:
        """获取监控目标：portfolio + watchlist"""
        targets = []
        for stock in self.config.get("portfolio", []):
            targets.append({**stock, "source": "portfolio"})
        for stock in self.config.get("watchlist", []):
            targets.append({**stock, "source": "watchlist"})
        return targets

    async def _fetch_historical_avg_volume(self, code: str, days: int = 5) -> Optional[float]:
        """获取近N天平均成交量"""
        try:
            # 复用 DataCollector 的数据源获取历史数据
            source = self.collector.sources[0]  # TencentSource
            df = await self.collector._run_blocking(
                source.fetch_prices, code=code, period="daily", count=days + 2
            )
            if df is None or df.empty:
                return None
            # 取最近 N 天的成交量平均
            avg_vol = df["volume"].tail(days).mean()
            return avg_vol if avg_vol > 0 else None
        except Exception as e:
            logger.warning(f"Failed to fetch historical volume for {code}: {e}")
            return None

    async def _fetch_current_quote(self, code: str) -> Optional[Dict[str, Any]]:
        """获取实时行情"""
        try:
            quote = await self.collector._fetch_single_quote_with_retry(code)
            return quote
        except Exception as e:
            logger.warning(f"Failed to fetch quote for {code}: {e}")
            return None

    def _detect_anomalies(
        self,
        target: Dict[str, Any],
        quote: Dict[str, Any],
        avg_volume: Optional[float],
    ) -> List[Anomaly]:
        """对单个标的检测异动"""
        anomalies = []
        code = target["code"]
        name = quote.get("name", target.get("name", code))
        price = quote.get("current_price", 0)
        pct = quote.get("pct_change", 0)
        volume = quote.get("volume", 0)
        turnover = quote.get("turnover_rate", 0)

        # 1. 急涨急跌检测
        if abs(pct) >= self.price_change_threshold:
            severity = "critical" if abs(pct) >= 5.0 else "alert" if abs(pct) >= 4.0 else "warning"
            direction = "急涨" if pct > 0 else "急跌"
            anomalies.append(Anomaly(
                code=code, name=name,
                anomaly_type="sharp_move",
                severity=severity,
                current_price=price,
                pct_change=pct,
                volume=volume,
                turnover_rate=turnover,
                detail=f"{direction} {pct:+.2f}%，当前价 {price}",
            ))

        # 2. 放量检测（需要历史数据）
        if avg_volume and avg_volume > 0 and volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio >= self.volume_ratio_threshold:
                severity = "critical" if volume_ratio >= 3.0 else "alert" if volume_ratio >= 2.0 else "warning"
                anomalies.append(Anomaly(
                    code=code, name=name,
                    anomaly_type="volume_spike",
                    severity=severity,
                    current_price=price,
                    pct_change=pct,
                    volume=volume,
                    turnover_rate=turnover,
                    detail=f"量比 {volume_ratio:.1f}x（当前 {volume:.0f}手 / 5日均 {avg_volume:.0f}手）",
                ))

        # 3. 换手率异常检测
        if turnover >= self.turnover_threshold:
            severity = "alert" if turnover >= 15.0 else "warning"
            anomalies.append(Anomaly(
                code=code, name=name,
                anomaly_type="high_turnover",
                severity=severity,
                current_price=price,
                pct_change=pct,
                volume=volume,
                turnover_rate=turnover,
                detail=f"换手率 {turnover:.1f}% 异常偏高",
            ))

        return anomalies

    async def scan(self) -> List[Anomaly]:
        """扫描所有标的，返回异动列表"""
        targets = self._get_watch_targets()
        if not targets:
            logger.warning("No targets to scan (portfolio + watchlist empty)")
            return []

        logger.info(f"🔍 开始扫描 {len(targets)} 个标的的异动...")

        # 并发获取所有标的的实时行情和历史数据
        async def process_target(target: Dict[str, Any]) -> List[Anomaly]:
            code = target["code"]
            quote, avg_vol = await asyncio.gather(
                self._fetch_current_quote(code),
                self._fetch_historical_avg_volume(code),
            )
            if not quote:
                return []
            return self._detect_anomalies(target, quote, avg_vol)

        results = await asyncio.gather(*[process_target(t) for t in targets])

        # 合并所有异动
        all_anomalies = []
        for anomaly_list in results:
            all_anomalies.extend(anomaly_list)

        # 按严重程度排序
        severity_order = {"critical": 0, "alert": 1, "warning": 2}
        all_anomalies.sort(key=lambda a: severity_order.get(a.severity, 99))

        logger.info(f"✅ 扫描完成，发现 {len(all_anomalies)} 个异动")
        return all_anomalies
