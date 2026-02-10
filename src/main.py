import asyncio
import sys
import argparse
import json
from typing import Dict, Any, List

from src.utils.logger import logger
from src.service.analysis_service import AnalysisService
from src.web.server import WebServer
from src.utils.config_loader import ConfigLoader
from src.web.api import get_router
import os

def setup_proxy():
    """Inject proxy settings into environment if configured."""
    system_config = ConfigLoader().get_system_config()
    proxy = system_config.get('proxy')
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        logger.info(f"Global Proxy Enabled: {proxy}")

def _print_text_summary(result: Dict[str, Any], mode: str):
    """Format analysis result as human-readable text for terminal output."""
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    lines = []
    if mode == 'morning':
        lines.append(f"=== 早报分析 ===")
        lines.append(f"隔夜综述: {result.get('global_overnight_summary', 'N/A')}")
        lines.append(f"大宗商品: {result.get('commodity_summary', 'N/A')}")
        lines.append(f"美债影响: {result.get('us_treasury_impact', 'N/A')}")
        lines.append(f"A股展望: {result.get('a_share_outlook', 'N/A')}")
        risk = result.get('risk_events', [])
        if risk:
            lines.append(f"风险事件: {', '.join(risk)}")
        for a in result.get('actions', []):
            lines.append(f"  [{a.get('code')}] {a.get('name')} | 预期:{a.get('opening_expectation')} | 策略:{a.get('strategy')}")
    elif mode == 'close':
        lines.append(f"=== 收盘复盘 ===")
        lines.append(f"总结: {result.get('market_summary', 'N/A')}")
        lines.append(f"温度: {result.get('market_temperature', 'N/A')}")
        for a in result.get('actions', []):
            lines.append(f"  [{a.get('code')}] {a.get('name')}")
            lines.append(f"    今日: {a.get('today_review', '')}")
            lines.append(f"    明日: {a.get('tomorrow_plan', '')}")
            lines.append(f"    支撑:{a.get('support_level', 0)} / 压力:{a.get('resistance_level', 0)}")
    else:  # midday
        lines.append(f"=== 午盘分析 ===")
        lines.append(f"情绪: {result.get('market_sentiment', 'N/A')}")
        lines.append(f"量能: {result.get('volume_analysis', 'N/A')}")
        lines.append(f"指数: {result.get('indices_info', 'N/A')}")
        lines.append(f"点评: {result.get('macro_summary', 'N/A')}")
        for a in result.get('actions', []):
            pct = a.get('pct_change_str', '')
            lines.append(f"  [{a.get('code')}] {a.get('name')} {pct} | 信号:{a.get('signal','N/A')} | 操作:{a.get('operation','N/A')}")
            if a.get('reason'):
                lines.append(f"    理由: {a.get('reason')}")

    print("\n".join(lines))

def entry_point():
    parser = argparse.ArgumentParser(description="Project Sentinel V2")
    parser.add_argument('--mode', type=str, default='midday', choices=['midday', 'close', 'morning'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without calling expensive APIs or sending notifications')
    parser.add_argument('--replay', action='store_true', help='Replay analysis using last saved data')
    parser.add_argument('--webui', action='store_true', help='Start WebUI server')
    parser.add_argument('--publish', action='store_true', help='Push results to Feishu (default: no push)')
    parser.add_argument('--output', type=str, default='text', choices=['text', 'json'], help='Output format')
    parser.add_argument('--ask', type=str, default=None, help='Ask a follow-up question about cached analysis')
    parser.add_argument('--date', type=str, default=None, help='Target date (YYYY-MM-DD) for analysis or Q&A')

    args = parser.parse_args()

    # 1. Setup Proxy (Before any networking)
    setup_proxy()

    # 2. Init Service
    service = AnalysisService()

    if args.webui:
        from src.web.api import init_routes
        init_routes(service)
        server = WebServer(port=8000)
        server.run()
    elif args.ask:
        # Q&A mode
        answer = asyncio.run(service.ask_question(
            question=args.ask,
            date=args.date,
            mode=args.mode
        ))
        if args.output == 'json':
            print(json.dumps({"question": args.ask, "answer": answer}, ensure_ascii=False))
        else:
            print(answer)
    else:
        # Standard analysis mode
        result = asyncio.run(service.run_analysis(
            mode=args.mode,
            dry_run=args.dry_run,
            replay=args.replay,
            publish=args.publish
        ))
        if args.output == 'json':
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_text_summary(result, args.mode)

if __name__ == "__main__":
    entry_point()
