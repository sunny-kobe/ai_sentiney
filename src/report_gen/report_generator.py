"""
AI 研报生成模块
使用 MiMo 生成智能研报
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.analyst.openai_compat_client import OpenAICompatClient
from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


class ReportGenerator:
    """AI 研报生成器"""

    # 研报系统提示词
    SYSTEM_PROMPT = """你是一位专业的A股投资研究分析师。请根据提供的数据生成一份简洁的每日研报。

输出要求：
1. **市场综述**（100字）：今日市场整体表现、主要驱动因素
2. **板块分析**（150字）：领涨/领跌板块分析，行业轮动趋势
3. **持仓点评**（200字）：每只持仓的简要点评和操作建议
4. **风险提示**（100字）：需要关注的风险因素
5. **明日展望**（100字）：明日市场展望和操作策略

要求：
- 语言简洁专业
- 数据驱动，引用具体数字
- 给出明确的操作建议
- 风险提示要具体
- 总字数控制在600-800字
- 使用 emoji 增加可读性"""

    def __init__(self):
        self.config = ConfigLoader().config
        # 初始化 MiMo 客户端
        mimo_config = self.config.get('ai', {}).get('mimo', {})
        base_url = mimo_config.get('base_url', '')
        api_key = mimo_config.get('api_key', '')
        model = mimo_config.get('model', 'mimo-v2.5-pro')
        self.client = OpenAICompatClient(base_url, api_key, model)

    def _format_data_for_prompt(self, data: Dict[str, Any]) -> str:
        """格式化数据为提示词"""
        lines = ["# 每日研报数据输入\n"]

        # 市场概览
        market = data.get("market", {}).get("indices", {})
        if market:
            lines.append("## 市场概览")
            for name, info in market.items():
                price = info.get("price", 0)
                change = info.get("change", 0)
                direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                lines.append(f"- {name}: {price} ({direction}{abs(change):.2f}%)")
            lines.append("")

        # 板块表现
        sectors = data.get("sectors", {}).get("sectors", {})
        if isinstance(sectors, dict):
            gainers = sectors.get("top_gainers", [])
            losers = sectors.get("top_losers", [])
            if gainers or losers:
                lines.append("## 板块表现")
                if gainers:
                    lines.append("领涨板块:")
                    for g in gainers[:3]:
                        lines.append(f"  - {g.get('板块名称', '')}: +{g.get('涨跌幅', 0):.2f}%")
                if losers:
                    lines.append("领跌板块:")
                    for l in losers[:3]:
                        lines.append(f"  - {l.get('板块名称', '')}: {l.get('涨跌幅', 0):.2f}%")
                lines.append("")

        # 持仓状态
        portfolio = data.get("portfolio", {}).get("portfolio", [])
        if portfolio:
            lines.append("## 持仓状态")
            for p in portfolio:
                name = p.get("name", "")
                code = p.get("code", "")
                price = p.get("price", 0)
                change = p.get("change", 0)
                cost = p.get("cost", 0)
                strategy = p.get("strategy", "")

                pnl = 0
                if cost and price:
                    pnl = (price - cost) / cost * 100

                direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                pnl_str = f"+{pnl:.1f}%" if pnl > 0 else f"{pnl:.1f}%"

                lines.append(f"- {name}({code}): {price} {direction}{abs(change):.2f}% | 成本{cost} | 盈亏{pnl_str} | 策略{strategy}")
            lines.append("")

        # 行业新闻
        news = data.get("news", {})
        if news:
            lines.append("## 行业新闻")
            for sector, news_list in news.items():
                if news_list:
                    lines.append(f"[{sector}]")
                    for n in news_list[:2]:
                        lines.append(f"  - {n.get('title', '')}")
            lines.append("")

        # 政策动态
        policy = data.get("policy", [])
        if policy:
            lines.append("## 政策动态")
            for p in policy[:3]:
                importance = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(p.get("importance", "low"), "⚪")
                lines.append(f"- {importance} {p.get('title', '')}")
            lines.append("")

        # GitHub Trending
        github = data.get("github", {})
        if github:
            lines.append("## 技术热点 (GitHub Trending)")
            for lang, repos in github.items():
                if repos:
                    lines.append(f"[{lang.upper()}]")
                    for r in repos[:2]:
                        stars = r.get("stars", 0)
                        today = r.get("today_stars", 0)
                        lines.append(f"  - {r.get('full_name', '')} ⭐{stars}(+{today})")
            lines.append("")

        return "\n".join(lines)

    async def generate(self, data: Dict[str, Any]) -> str:
        """生成研报"""
        logger.info("🤖 开始生成 AI 研报...")

        # 格式化数据
        user_content = self._format_data_for_prompt(data)

        try:
            # 调用 MiMo 生成研报
            report = self.client.chat(self.SYSTEM_PROMPT, user_content)
            logger.info("✅ AI 研报生成完成")
            return report
        except Exception as e:
            logger.error(f"AI 研报生成失败: {e}")
            # 降级：生成简单摘要
            return self._generate_fallback_report(data)

    def _generate_fallback_report(self, data: Dict[str, Any]) -> str:
        """降级研报（无 AI）"""
        timestamp = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
        lines = [
            f"📊 每日研报 ({timestamp})",
            "",
            "【市场综述】",
        ]

        # 市场概览
        market = data.get("market", {}).get("indices", {})
        if market:
            for name, info in market.items():
                change = info.get("change", 0)
                direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                lines.append(f"- {name}: {direction}{abs(change):.2f}%")
        else:
            lines.append("暂无市场数据")

        lines.append("")
        lines.append("【持仓状态】")

        # 持仓状态
        portfolio = data.get("portfolio", {}).get("portfolio", [])
        if portfolio:
            for p in portfolio:
                name = p.get("name", "")
                change = p.get("change", 0)
                direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                lines.append(f"- {name}: {direction}{abs(change):.2f}%")
        else:
            lines.append("暂无持仓数据")

        return "\n".join(lines)
