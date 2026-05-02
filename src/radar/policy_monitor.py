"""
政策变动监控模块
使用 AkShare 内置新闻源监控政策动态
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.logger import logger


class PolicyMonitor:
    """政策变动监控器"""

    # 政策关键词
    POLICY_KEYWORDS = [
        "证监会",
        "央行",
        "国务院",
        "发改委",
        "财政部",
        "货币政策",
        "财政政策",
        "降息",
        "降准",
        "IPO",
        "注册制",
        "退市",
        "监管",
        "资本市场",
        "金融改革",
        "人民币",
        "外汇",
        "国债",
    ]

    # 高重要性关键词
    HIGH_IMPORTANCE = [
        "国务院",
        "央行",
        "证监会",
        "降息",
        "降准",
        "重大改革",
        "紧急",
        "重磅",
        "历史性",
        "首次",
    ]

    # AkShare 新闻源
    NEWS_SOURCES = [
        ("cls", ak.stock_info_global_cls, {"symbol": "全部"}),
        ("sina", ak.stock_info_global_sina, {}),
        ("ths", ak.stock_info_global_ths, {}),
    ]

    def __init__(self, keywords: Optional[List[str]] = None):
        self.keywords = keywords or self.POLICY_KEYWORDS

    async def _fetch_news(self) -> List[Dict[str, str]]:
        """获取新闻"""
        all_news = []

        for source_name, func, kwargs in self.NEWS_SOURCES:
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

                for _, row in df.head(30).iterrows():
                    title = str(row[title_col]).strip()
                    if title and len(title) > 10:
                        all_news.append({
                            "title": title,
                            "source": source_name,
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch news from {source_name}: {e}")

        return all_news

    def _filter_policy_news(self, news_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """过滤政策相关新闻"""
        filtered = []
        for news in news_list:
            title = news["title"]
            # 检查是否包含政策关键词
            for kw in self.keywords:
                if kw in title:
                    # 评估重要性
                    importance = "low"
                    for high_kw in self.HIGH_IMPORTANCE:
                        if high_kw in title:
                            importance = "high"
                            break
                    if importance == "low":
                        importance = "medium"

                    news["importance"] = importance
                    filtered.append(news)
                    break
        return filtered

    async def monitor(self, count: int = 5) -> List[Dict[str, str]]:
        """监控政策变动"""
        logger.info("📋 开始监控政策变动...")

        # 获取新闻
        all_news = await self._fetch_news()

        # 过滤政策新闻
        policy_news = self._filter_policy_news(all_news)

        # 按重要性排序
        importance_order = {"high": 0, "medium": 1, "low": 2}
        policy_news.sort(key=lambda x: importance_order.get(x.get("importance", "low"), 99))

        # 去重
        seen = set()
        unique_news = []
        for news in policy_news:
            if news["title"] not in seen:
                seen.add(news["title"])
                unique_news.append(news)

        logger.info(f"✅ 政策监控完成，发现 {len(unique_news)} 条政策动态")
        return unique_news[:count]
