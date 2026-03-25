import asyncio
import argparse
import json
import logging
import os
import sys
import warnings
from typing import Dict, Any, List

from src.utils.logger import logger
from src.service.analysis_service import AnalysisService
from src.web.server import WebServer
from src.utils.config_loader import ConfigLoader
from src.web.api import get_router

existing_pythonwarnings = os.environ.get("PYTHONWARNINGS", "")
ignore_rule = "ignore:resource_tracker:UserWarning"
if ignore_rule not in existing_pythonwarnings:
    os.environ["PYTHONWARNINGS"] = f"{existing_pythonwarnings},{ignore_rule}".strip(",")

warnings.filterwarnings(
    "ignore",
    message=r"resource_tracker: There appear to be .* leaked semaphore objects to clean up at shutdown",
    category=UserWarning,
)

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
    if result.get("skipped"):
        print(f"Skipped: {result.get('message', 'non-trading day')}")
        return

    lines = []
    quality_status = result.get("quality_status")
    data_timestamp = result.get("data_timestamp")
    source_labels = result.get("source_labels", [])

    if mode == 'swing':
        lines.append("=== 中长期投资助手 ===")
        if quality_status:
            lines.append(f"质量: {quality_status}")
        if data_timestamp:
            lines.append(f"时间: {data_timestamp}")
        if source_labels:
            lines.append(f"来源: {', '.join(source_labels)}")
        if result.get("validation_summary"):
            lines.append("验证摘要:")
            lines.append(f"  {result.get('validation_summary')}")
        position_plan = result.get("position_plan") or {}
        lines.append("今日结论:")
        lines.append(f"  {result.get('market_conclusion', '暂无结论')}")
        lines.append("账户动作:")
        if position_plan.get("current_total_exposure"):
            lines.append(f"  当前总仓位: {position_plan.get('current_total_exposure', 'N/A')}")
        lines.append(f"  总仓位: {position_plan.get('total_exposure', 'N/A')}")
        lines.append(f"  现金目标: {position_plan.get('cash_target', 'N/A')}")
        execution_order = position_plan.get("execution_order") or []
        lines.append(f"  优先动作: {'；'.join(execution_order) if execution_order else '暂无'}")
        lines.append("持仓处理:")
        for action in result.get("actions", []):
            lines.append(
                f"  [{action.get('code')}] {action.get('name')} | 结论:{action.get('conclusion', action.get('action_label', '观察'))}"
                f" | 当前:{action.get('current_weight', '0%')} | 目标:{action.get('target_weight', 'N/A')}"
            )
            lines.append(f"    原因: {action.get('reason', '')}")
            lines.append(f"    计划: {action.get('plan', '')}")
            lines.append(f"    风险线: {action.get('risk_line', '')}")
        lines.append("观察池机会:")
        watchlist_candidates = result.get("watchlist_candidates", []) or []
        if watchlist_candidates:
            for candidate in watchlist_candidates:
                lines.append(
                    f"  [{candidate.get('code')}] {candidate.get('name')} | 动作:{candidate.get('action_label', '继续观察')}"
                )
                lines.append(f"    原因: {candidate.get('reason', '')}")
                lines.append(f"    计划: {candidate.get('plan', '')}")
                lines.append(f"    失效条件: {candidate.get('risk_line', '')}")
        else:
            lines.append("  当前没有值得试仓的新方向。")
        lines.append("风险清单:")
        risk_items = [f"  - {issue}" for issue in (result.get("data_issues") or [])]
        for action in result.get("actions", []):
            if action.get("action_label") in {"减配", "回避"} and action.get("risk_line"):
                risk_items.append(f"  - {action.get('name')}: {action.get('risk_line')}")
        for candidate in watchlist_candidates:
            if candidate.get("risk_line"):
                risk_items.append(f"  - {candidate.get('name')}: {candidate.get('risk_line')}")
        lines.extend(risk_items[:3] or ["  - 暂无额外风险提示。"])
    elif mode == 'morning':
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
    elif mode == 'preclose':
        lines.append(f"=== 收盘前执行 ===")
        if quality_status:
            lines.append(f"质量: {quality_status}")
        if data_timestamp:
            lines.append(f"时间: {data_timestamp}")
        if source_labels:
            lines.append(f"来源: {', '.join(source_labels)}")
        lines.append(f"情绪: {result.get('market_sentiment', 'N/A')}")
        lines.append(f"量能: {result.get('volume_analysis', 'N/A')}")
        lines.append(f"指数: {result.get('indices_info', 'N/A')}")
        lines.append(f"执行摘要: {result.get('macro_summary', 'N/A')}")
        for a in result.get('actions', []):
            pct = a.get('pct_change_str', '')
            confidence = a.get('confidence', '')
            conf_tag = f" [{confidence}]" if confidence else ""
            lines.append(f"  [{a.get('code')}] {a.get('name')} {pct} | 信号:{a.get('signal','N/A')}{conf_tag} | 执行:{a.get('operation','N/A')}")
            tech = a.get('tech_summary', '')
            if tech:
                lines.append(f"    指标: {tech}")
            if a.get('reason'):
                lines.append(f"    理由: {a.get('reason')}")
    elif mode == 'close':
        lines.append(f"=== 收盘复盘 ===")
        if quality_status:
            lines.append(f"质量: {quality_status}")
        if data_timestamp:
            lines.append(f"时间: {data_timestamp}")
        if source_labels:
            lines.append(f"来源: {', '.join(source_labels)}")
        lines.append(f"总结: {result.get('market_summary', 'N/A')}")
        lines.append(f"温度: {result.get('market_temperature', 'N/A')}")
        # Signal Scorecard
        scorecard = result.get('signal_scorecard')
        if scorecard:
            lines.append(f"")
            lines.append(f"📊 {scorecard.get('comparison_label', '信号追踪')}: {scorecard.get('summary_text', '')}")
            for e in scorecard.get('yesterday_evaluation', []):
                if e['result'] == 'NEUTRAL':
                    continue
                icon = "✅" if e['result'] == 'HIT' else "❌"
                lines.append(f"  {icon} {e['name']} {e['yesterday_signal']}[{e.get('confidence', '')}] → {e['today_change']}%")
            lines.append(f"")
        for a in result.get('actions', []):
            lines.append(f"  [{a.get('code')}] {a.get('name')}")
            lines.append(f"    今日: {a.get('today_review', '')}")
            lines.append(f"    明日: {a.get('tomorrow_plan', '')}")
            lines.append(f"    支撑:{a.get('support_level', 0)} / 压力:{a.get('resistance_level', 0)}")
            tech = a.get('tech_summary', '')
            if tech:
                lines.append(f"    指标: {tech}")
    else:  # midday
        lines.append(f"=== 午盘分析 ===")
        if quality_status:
            lines.append(f"质量: {quality_status}")
        if data_timestamp:
            lines.append(f"时间: {data_timestamp}")
        if source_labels:
            lines.append(f"来源: {', '.join(source_labels)}")
        lines.append(f"情绪: {result.get('market_sentiment', 'N/A')}")
        lines.append(f"量能: {result.get('volume_analysis', 'N/A')}")
        lines.append(f"指数: {result.get('indices_info', 'N/A')}")
        lines.append(f"点评: {result.get('macro_summary', 'N/A')}")
        # Signal Scorecard
        scorecard = result.get('signal_scorecard')
        if scorecard:
            lines.append(f"")
            lines.append(f"📊 {scorecard.get('comparison_label', '信号追踪')}: {scorecard.get('summary_text', '')}")
            for e in scorecard.get('yesterday_evaluation', []):
                if e['result'] == 'NEUTRAL':
                    continue
                icon = "✅" if e['result'] == 'HIT' else "❌"
                lines.append(f"  {icon} {e['name']} {e['yesterday_signal']}[{e.get('confidence', '')}] → {e['today_change']}%")
            lines.append(f"")
        for a in result.get('actions', []):
            pct = a.get('pct_change_str', '')
            confidence = a.get('confidence', '')
            conf_tag = f" [{confidence}]" if confidence else ""
            lines.append(f"  [{a.get('code')}] {a.get('name')} {pct} | 信号:{a.get('signal','N/A')}{conf_tag} | 操作:{a.get('operation','N/A')}")
            tech = a.get('tech_summary', '')
            if tech:
                lines.append(f"    指标: {tech}")
            if a.get('reason'):
                lines.append(f"    理由: {a.get('reason')}")

    print("\n".join(lines))

def entry_point():
    parser = argparse.ArgumentParser(description="Project Sentinel V2")
    parser.add_argument('--mode', type=str, default='midday', choices=['midday', 'preclose', 'close', 'morning', 'swing'], help='Execution mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without calling expensive APIs or sending notifications')
    parser.add_argument('--replay', action='store_true', help='Replay analysis using last saved data')
    parser.add_argument('--validation-report', action='store_true', help='Print validation summary for the selected mode')
    parser.add_argument('--webui', action='store_true', help='Start WebUI server')
    parser.add_argument('--publish', action='store_true', help='Push results to configured channel (default: no push)')
    parser.add_argument('--publish-target', type=str, nargs='+', default=['feishu'], choices=['feishu', 'telegram'], help='Publish destination(s), can specify multiple')
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
    elif args.validation_report:
        snapshot = service.build_validation_snapshot(mode=args.mode)
        if args.output == 'json':
            print(json.dumps(snapshot, ensure_ascii=False))
        else:
            print(snapshot.get("text") or snapshot.get("summary_text", "暂无验证结果"))
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
            publish=args.publish,
            publish_target=args.publish_target
        ))
        if args.output == 'json':
            print(json.dumps(result, ensure_ascii=False))
        else:
            _print_text_summary(result, args.mode)


def _force_process_exit(exit_code: int = 0):
    """Terminate the CLI without waiting on leaked third-party worker resources."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        logging.shutdown()
        os._exit(int(exit_code))

if __name__ == "__main__":
    code = 0
    try:
        maybe_code = entry_point()
        if isinstance(maybe_code, int):
            code = maybe_code
    except KeyboardInterrupt:
        code = 130
    except Exception:
        logger.exception("Fatal error while running Project Sentinel CLI.")
        code = 1
    finally:
        _force_process_exit(code)
