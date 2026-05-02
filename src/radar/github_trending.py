"""
GitHub Trending 追踪模块
监控热门仓库和技术方向
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from src.utils.logger import logger


class GitHubTrendingTracker:
    """GitHub Trending 追踪器"""

    # 默认关注的语言
    DEFAULT_LANGUAGES = ["python", "typescript", "rust", "go"]

    # 默认关注的时间范围
    DEFAULT_SINCE = "daily"  # daily, weekly, monthly

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        since: str = "daily",
    ):
        self.languages = languages or self.DEFAULT_LANGUAGES
        self.since = since
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    async def _fetch_trending(self, language: str, since: str = "daily") -> List[Dict[str, Any]]:
        """获取单个语言的 trending 仓库"""
        try:
            url = f"https://github.com/trending/{language}"
            params = {"since": since}
            resp = self.session.get(url, params=params, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"GitHub trending returned {resp.status_code} for {language}")
                return []

            repos = []
            # 解析 trending 页面
            # 匹配仓库信息
            repo_pattern = re.compile(
                r'<article class="Box-row">(.*?)</article>',
                re.DOTALL
            )
            matches = repo_pattern.findall(resp.text)

            for match in matches[:5]:  # 每个语言取前5个
                repo = self._parse_repo(match, language)
                if repo:
                    repos.append(repo)

            return repos
        except Exception as e:
            logger.warning(f"GitHub trending fetch failed for {language}: {e}")
            return []

    def _parse_repo(self, html: str, language: str) -> Optional[Dict[str, Any]]:
        """解析单个仓库信息"""
        try:
            # 提取仓库名 - 匹配 /user/repo 格式的链接
            name_match = re.search(r'href="(/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)"', html)
            if not name_match:
                return None
            full_name = name_match.group(1).strip('/')

            # 跳过非仓库链接
            if full_name.startswith(('login', 'sponsors', 'signup')):
                return None

            # 提取描述
            desc_match = re.search(r'<p class="[^"]*">(.*?)</p>', html, re.DOTALL)
            description = ""
            if desc_match:
                description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

            # 提取星标数
            stars_match = re.search(r'(\d[\d,]*)\s*stars', html)
            stars = 0
            if stars_match:
                stars = int(stars_match.group(1).replace(',', ''))

            # 提取今日新增星标
            today_stars_match = re.search(r'(\d[\d,]*)\s*stars\s*today', html)
            today_stars = 0
            if today_stars_match:
                today_stars = int(today_stars_match.group(1).replace(',', ''))

            # 提取语言
            lang_match = re.search(r'itemprop="programmingLanguage">(.*?)<', html)
            repo_language = lang_match.group(1).strip() if lang_match else language

            return {
                "full_name": full_name,
                "url": f"https://github.com/{full_name}",
                "description": description[:200] if description else "",
                "language": repo_language,
                "stars": stars,
                "today_stars": today_stars,
            }
        except Exception as e:
            logger.warning(f"Failed to parse repo: {e}")
            return None

    async def track(self, top_n: int = 3) -> Dict[str, List[Dict[str, Any]]]:
        """追踪所有语言的 trending"""
        logger.info(f"🔥 开始追踪 GitHub Trending，关注语言: {', '.join(self.languages)}")

        tasks = [
            self._fetch_trending(lang, self.since)
            for lang in self.languages
        ]
        results = await asyncio.gather(*tasks)

        trending_by_lang = {}
        total = 0
        for lang, repos in zip(self.languages, results):
            trending_by_lang[lang] = repos[:top_n]
            total += len(repos[:top_n])

        logger.info(f"✅ GitHub Trending 追踪完成，共 {total} 个热门仓库")
        return trending_by_lang

    async def search_repo(self, query: str, count: int = 5) -> List[Dict[str, Any]]:
        """搜索仓库"""
        try:
            url = "https://api.github.com/search/repositories"
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": count,
            }
            resp = self.session.get(url, params=params, timeout=15)

            if resp.status_code != 200:
                return []

            data = resp.json()
            repos = []

            for item in data.get("items", [])[:count]:
                repos.append({
                    "full_name": item["full_name"],
                    "url": item["html_url"],
                    "description": (item.get("description") or "")[:200],
                    "language": item.get("language", ""),
                    "stars": item.get("stargazers_count", 0),
                    "forks": item.get("forks_count", 0),
                    "updated_at": item.get("updated_at", ""),
                })

            return repos
        except Exception as e:
            logger.warning(f"GitHub search failed for {query}: {e}")
            return []
