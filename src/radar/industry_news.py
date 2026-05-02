"""
行业新闻抓取模块
使用 AkShare 内置新闻源，更可靠
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.logger import logger


class IndustryNewsCollector:
    """行业新闻采集器"""

    # 默认关注的行业关键词
    DEFAULT_SECTORS = {
        "AI": ["人工智能", "AI", "大模型", "GPT", "机器人", "自动驾驶", "算力"],
        "半导体": ["半导体", "芯片", "GPU", "EDA", "光刻机", "封测"],
        "新能源": ["新能源", "光伏", "锂电池", "储能", "电动车", "充电桩"],
    }

    # AkShare 全球新闻源
    GLOBAL_NEWS_SOURCES = [
        ("cls", ak.stock_info_global_cls, {"symbol": "全部"}),
        ("sina", ak.stock_info_global_sina, {}),
        ("ths", ak.stock_info_global_ths, {}),
    ]

    def __init__(self, sectors: Optional[Dict[str, List[str]]] = None):
        self.sectors = sectors or self.DEFAULT_SECTORS

    async def _fetch_global_news(self) -> List[Dict[str, str]]:
        """获取全球财经新闻"""
        all_news = []

        for source_name, func, kwargs in self.GLOBAL_NEWS_SOURCES:
            try:
                df = func(**kwargs)
                if df is None or df.empty:
                    continue

                # 标准化列名
                title_col = None
                for col in ['标题', 'content', 'title', '新闻标题']:
                    if col in df.columns:
                        title_col = col
                        break

                if not title_col:
                    continue

                for _, row in df.head(20).iterrows():
                    title = str(row[title_col]).strip()
                    if title and len(title) > 10:
                        all_news.append({
                            "title": title,
                            "source": source_name,
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch news from {source_name}: {e}")

        return all_news

    def _filter_by_sector(self, news_list: List[Dict[str, str]], sector: str, keywords: List[str]) -> List[Dict[str, str]]:
        """按行业关键词过滤新闻"""
        filtered = []
        for news in news_list:
            title = news["title"].lower()
            for kw in keywords:
                if kw.lower() in title:
                    news["sector"] = sector
                    filtered.append(news)
                    break
        return filtered

    async def collect_all(self, count_per_sector: int = 3) -> Dict[str, List[Dict[str, str]]]:
        """采集所有行业的新闻"""
        logger.info(f"📰 开始采集行业新闻，关注 {len(self.sectors)} 个赛道...")

        # 获取全局新闻
        global_news = await self._fetch_global_news()

        # 按行业过滤
        news_by_sector = {}
        total = 0
        for sector, keywords in self.sectors.items():
            filtered = self._filter_by_sector(global_news, sector, keywords)
            news_by_sector[sector] = filtered[:count_per_sector]
            total += len(news_by_sector[sector])

        logger.info(f"✅ 行业新闻采集完成，共 {total} 条")
        return news_by_sector
