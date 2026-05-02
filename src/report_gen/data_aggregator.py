"""
研报数据聚合模块
聚合：市场数据 + 行业新闻 + 政策动态 + 技术指标
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.collector.data_fetcher import DataCollector
from src.radar.industry_news import IndustryNewsCollector
from src.radar.policy_monitor import PolicyMonitor
from src.radar.github_trending import GitHubTrendingTracker
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


class DataAggregator:
    """研报数据聚合器"""

    def __init__(self):
        self.config = ConfigLoader().config
        self.collector = DataCollector()
        self.industry = IndustryNewsCollector()
        self.policy = PolicyMonitor()
        self.github = GitHubTrendingTracker()

    async def _fetch_market_overview(self) -> Dict[str, Any]:
        """获取市场概览"""
        try:
            # 获取主要指数
            indices = {}
            index_list = [
                ("上证指数", "sh000001"),
                ("深证成指", "sz399001"),
                ("创业板指", "sz399006"),
                ("科创50", "sh000688"),
            ]

            for name, code in index_list:
                try:
                    quote = await self.collector._fetch_single_quote_with_retry(code.replace("sh", "").replace("sz", ""))
                    if quote:
                        indices[name] = {
                            "price": quote.get("current_price", 0),
                            "change": quote.get("pct_change", 0),
                        }
                except Exception:
                    pass

            return {"indices": indices}
        except Exception as e:
            logger.warning(f"Failed to fetch market overview: {e}")
            return {"indices": {}}

    async def _fetch_sector_performance(self) -> Dict[str, Any]:
        """获取板块表现"""
        try:
            # 获取板块涨跌幅
            df = ak.stock_board_industry_name_em()
            if df is None or df.empty:
                return {"sectors": []}

            # 取涨跌幅前5和后5
            if '涨跌幅' in df.columns:
                df = df.sort_values('涨跌幅', ascending=False)
                top_gainers = df.head(5)[['板块名称', '涨跌幅']].to_dict('records')
                top_losers = df.tail(5)[['板块名称', '涨跌幅']].to_dict('records')
                return {
                    "sectors": {
                        "top_gainers": top_gainers,
                        "top_losers": top_losers,
                    }
                }
            return {"sectors": []}
        except Exception as e:
            logger.warning(f"Failed to fetch sector performance: {e}")
            return {"sectors": []}

    async def _fetch_portfolio_status(self) -> Dict[str, Any]:
        """获取持仓状态"""
        portfolio = self.config.get("portfolio", [])
        if not portfolio:
            return {"portfolio": []}

        status_list = []
        for stock in portfolio:
            code = stock.get("code", "")
            name = stock.get("name", "")
            try:
                quote = await self.collector._fetch_single_quote_with_retry(code)
                if quote:
                    status_list.append({
                        "code": code,
                        "name": name,
                        "price": quote.get("current_price", 0),
                        "change": quote.get("pct_change", 0),
                        "cost": stock.get("cost", 0),
                        "strategy": stock.get("strategy", ""),
                    })
            except Exception:
                pass

        return {"portfolio": status_list}

    async def aggregate(self) -> Dict[str, Any]:
        """聚合所有数据"""
        logger.info("📊 开始聚合研报数据...")

        # 并发获取各类数据
        market_task = self._fetch_market_overview()
        sector_task = self._fetch_sector_performance()
        portfolio_task = self._fetch_portfolio_status()
        news_task = self.industry.collect_all(count_per_sector=2)
        policy_task = self.policy.monitor(count=3)
        github_task = self.github.track(top_n=2)

        results = await asyncio.gather(
            market_task, sector_task, portfolio_task,
            news_task, policy_task, github_task,
            return_exceptions=True
        )

        # 处理结果
        market, sectors, portfolio, news, policy, github = results

        # 处理异常
        if isinstance(market, Exception):
            logger.warning(f"Market fetch failed: {market}")
            market = {"indices": {}}
        if isinstance(sectors, Exception):
            logger.warning(f"Sector fetch failed: {sectors}")
            sectors = {"sectors": []}
        if isinstance(portfolio, Exception):
            logger.warning(f"Portfolio fetch failed: {portfolio}")
            portfolio = {"portfolio": []}
        if isinstance(news, Exception):
            logger.warning(f"News fetch failed: {news}")
            news = {}
        if isinstance(policy, Exception):
            logger.warning(f"Policy fetch failed: {policy}")
            policy = []
        if isinstance(github, Exception):
            logger.warning(f"GitHub fetch failed: {github}")
            github = {}

        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "market": market,
            "sectors": sectors,
            "portfolio": portfolio,
            "news": news,
            "policy": policy,
            "github": github,
        }

        logger.info("✅ 研报数据聚合完成")
        return data
