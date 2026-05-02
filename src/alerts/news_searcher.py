"""
异动相关新闻搜索
当检测到异动时，自动搜索相关新闻帮助判断原因
"""

import asyncio
import re
from typing import Any, Dict, List, Optional

import requests

from src.utils.logger import logger


class NewsSearcher:
    """异动相关新闻搜索"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    async def search_stock_news(self, code: str, name: str, count: int = 3) -> List[Dict[str, str]]:
        """
        搜索个股相关新闻
        使用百度新闻搜索作为数据源
        """
        try:
            query = f"{name} {code} 股票 最新消息"
            url = "https://www.baidu.com/s"
            params = {
                "wd": query,
                "tn": "news",
                "rn": count,
            }
            resp = self.session.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                return []

            # 简单提取标题和摘要
            news_list = []
            # 匹配新闻标题和摘要
            title_pattern = re.compile(r'<h3[^>]*>.*?</h3>', re.DOTALL)
            matches = title_pattern.findall(resp.text)

            for match in matches[:count]:
                # 提取纯文本
                title = re.sub(r'<[^>]+>', '', match).strip()
                if title and len(title) > 5:
                    news_list.append({"title": title, "source": "百度新闻"})

            return news_list
        except Exception as e:
            logger.warning(f"News search failed for {code} ({name}): {e}")
            return []

    async def search_market_news(self, keyword: str, count: int = 3) -> List[Dict[str, str]]:
        """
        搜索市场相关新闻（板块、概念等）
        """
        try:
            query = f"{keyword} A股 最新消息"
            url = "https://www.baidu.com/s"
            params = {
                "wd": query,
                "tn": "news",
                "rn": count,
            }
            resp = self.session.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                return []

            news_list = []
            title_pattern = re.compile(r'<h3[^>]*>.*?</h3>', re.DOTALL)
            matches = title_pattern.findall(resp.text)

            for match in matches[:count]:
                title = re.sub(r'<[^>]+>', '', match).strip()
                if title and len(title) > 5:
                    news_list.append({"title": title, "source": "百度新闻"})

            return news_list
        except Exception as e:
            logger.warning(f"Market news search failed for {keyword}: {e}")
            return []

    async def batch_search(self, targets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
        """
        批量搜索多个标的的新闻
        targets: [{"code": "510500", "name": "中证500ETF"}, ...]
        返回: {"510500": [{"title": "...", "source": "..."}], ...}
        """
        async def search_one(target: Dict[str, Any]) -> tuple:
            code = target["code"]
            name = target["name"]
            news = await self.search_stock_news(code, name)
            return code, news

        results = await asyncio.gather(*[search_one(t) for t in targets])
        return dict(results)
