"""
智能信息雷达主入口
聚合：行业新闻 + 政策变动 + GitHub Trending
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.radar.industry_news import IndustryNewsCollector
from src.radar.policy_monitor import PolicyMonitor
from src.radar.github_trending import GitHubTrendingTracker
from src.reporter.telegram_client import TelegramClient
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


class RadarRunner:
    """智能信息雷达运行器"""

    def __init__(self):
        self.config = ConfigLoader().config
        self.radar_config = self.config.get("radar", {})

        # 初始化各模块
        sectors = self.radar_config.get("sectors", None)
        self.industry = IndustryNewsCollector(sectors=sectors)

        policy_keywords = self.radar_config.get("policy_keywords", None)
        self.policy = PolicyMonitor(keywords=policy_keywords)

        github_langs = self.radar_config.get("github_languages", ["python", "typescript", "rust", "go"])
        self.github = GitHubTrendingTracker(languages=github_langs)

        self.telegram = TelegramClient()
        self.state_file = Path("data/radar_state.json")
        self._load_state()

    def _load_state(self):
        """加载上次推送状态（用于去重）"""
        self.last_push: Dict[str, str] = {}
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.last_push = data.get("last_push", {})
            except Exception:
                pass

    def _save_state(self):
        """保存推送状态"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "last_push": self.last_push,
            "last_scan": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2))

    def _make_news_key(self, title: str) -> str:
        """生成新闻去重 key"""
        # 取标题前30个字符作为 key
        return title[:30]

    def _filter_new_items(self, items: List[Dict[str, str]], item_type: str) -> List[Dict[str, str]]:
        """过滤已经推送过的项目"""
        today = datetime.now().strftime("%Y-%m-%d")
        new_items = []

        for item in items:
            title = item.get("title", "")
            key = f"{item_type}:{self._make_news_key(title)}"
            last_date = self.last_push.get(key, "")
            if last_date != today:
                new_items.append(item)
                self.last_push[key] = today

        return new_items

    def _build_report(
        self,
        industry_news: Dict[str, List[Dict[str, str]]],
        policy_news: List[Dict[str, str]],
        github_trending: Dict[str, List[Dict[str, Any]]],
    ) -> str:
        """构建雷达报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"📡 Sentinel 智能信息雷达", f"时间: {now}", ""]

        # 1. 行业新闻
        has_industry = any(news for news in industry_news.values())
        if has_industry:
            lines.append("📰 行业动态")
            lines.append("─" * 20)
            for sector, news in industry_news.items():
                if news:
                    lines.append(f"【{sector}】")
                    for n in news[:2]:
                        lines.append(f"  • {n['title']}")
            lines.append("")

        # 2. 政策变动
        if policy_news:
            lines.append("📋 政策速递")
            lines.append("─" * 20)
            for p in policy_news[:3]:
                importance_emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(p.get("importance", "low"), "⚪")
                lines.append(f"  {importance_emoji} {p['title']}")
            lines.append("")

        # 3. GitHub Trending
        has_github = any(repos for repos in github_trending.values())
        if has_github:
            lines.append("🔥 GitHub Trending")
            lines.append("─" * 20)
            for lang, repos in github_trending.items():
                if repos:
                    lines.append(f"【{lang.upper()}】")
                    for r in repos[:2]:
                        stars_info = f"⭐{r['stars']}" if r.get('stars') else ""
                        today_info = f" (+{r['today_stars']} today)" if r.get('today_stars') else ""
                        desc = r.get('description', '')[:50]
                        lines.append(f"  • {r['full_name']} {stars_info}{today_info}")
                        if desc:
                            lines.append(f"    {desc}")
            lines.append("")

        return "\n".join(lines)

    async def run(self, dry_run: bool = False) -> Dict[str, Any]:
        """执行一次雷达扫描"""
        logger.info("🚀 启动智能信息雷达...")

        # 并发执行三个模块
        industry_task = self.industry.collect_all(count_per_sector=3)
        policy_task = self.policy.monitor(count=5)
        github_task = self.github.track(top_n=3)

        industry_news, policy_news, github_trending = await asyncio.gather(
            industry_task, policy_task, github_task
        )

        # 过滤已推送的
        filtered_industry = {}
        for sector, news in industry_news.items():
            filtered = self._filter_new_items(news, f"industry:{sector}")
            filtered_industry[sector] = filtered

        filtered_policy = self._filter_new_items(policy_news, "policy")

        # GitHub trending 不做过滤（每日变化大）
        filtered_github = github_trending

        # 检查是否有新内容
        has_industry = any(news for news in filtered_industry.values())
        has_policy = len(filtered_policy) > 0
        has_github = any(repos for repos in filtered_github.values())

        if not has_industry and not has_policy and not has_github:
            logger.info("✅ 无新内容，跳过推送")
            return {"pushed": False, "message": ""}

        # 构建报告
        message = self._build_report(filtered_industry, filtered_policy, filtered_github)

        # 推送
        if dry_run:
            logger.info(f"[DRY RUN] 雷达报告:\n{message}")
        else:
            self.telegram._send_message(message)
            logger.info("✅ 雷达报告已推送到 Telegram")

        # 保存状态
        self._save_state()

        return {
            "pushed": not dry_run,
            "message": message,
            "stats": {
                "industry": {s: len(n) for s, n in filtered_industry.items()},
                "policy": len(filtered_policy),
                "github": {l: len(r) for l, r in filtered_github.items()},
            }
        }


async def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Sentinel 智能信息雷达")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不推送消息")
    args = parser.parse_args()

    runner = RadarRunner()
    result = await runner.run(dry_run=args.dry_run)

    if result.get("pushed"):
        print("✅ 雷达报告已推送")
    else:
        print("✅ 无新内容")

    if result.get("stats"):
        stats = result["stats"]
        print(f"\n采集统计:")
        print(f"  行业新闻: {sum(stats.get('industry', {}).values())} 条")
        print(f"  政策动态: {stats.get('policy', 0)} 条")
        print(f"  GitHub: {sum(stats.get('github', {}).values())} 个仓库")


if __name__ == "__main__":
    asyncio.run(main())
