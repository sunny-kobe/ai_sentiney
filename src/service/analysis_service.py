import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader
from src.collector.data_fetcher import DataCollector
from src.processor.data_processor import DataProcessor
from src.analyst.gemini_client import GeminiClient
from src.reporter.feishu_client import FeishuClient
from src.reporter.telegram_client import TelegramClient
from src.storage.database import SentinelDB
from src.processor.signal_tracker import evaluate_yesterday, calculate_rolling_stats, calculate_pair_rolling_stats, build_scorecard, _compute_risk_stats, _compute_buy_stats
from src.processor.swing_tracker import build_swing_scorecard
from src.utils.trading_calendar import should_run_market_report
from src.service.report_quality import (
    build_quality_detail,
    build_swing_quality_guard,
    evaluate_input_quality,
    evaluate_output_quality,
)
from src.service.structured_report import build_structured_report
from src.service.portfolio_advisor import build_investor_snapshot
from src.service.performance_gate import build_default_performance_context, gate_offensive_setup
from src.service.swing_strategy import build_swing_report, resolve_benchmark_code
from src.service.strategy_engine import build_strategy_snapshot, build_intraday_rule_report, build_close_rule_report
from src.backtest.engine import run_deterministic_backtest
from src.backtest.walkforward import run_walkforward_validation
from src.service.strategy_lab_service import StrategyLabService
from src.service.validation_service import ValidationService


SWING_LAB_PRESETS = (
    "aggressive_trend_guard",
    "aggressive_leader_focus",
    "aggressive_core_rotation",
)

DEGRADED_OVERVIEW_LABEL = "信息不全，先看技术结构"
DEGRADED_INTRADAY_SUMMARY = "当前主要依据技术面和已采集快讯整理，先给保守执行摘要。"
DEGRADED_CLOSE_SUMMARY = "当前主要依据技术面和已采集快讯整理，先给盘后执行摘要。"
DEGRADED_CLOSE_REVIEW = "盘后信息不全，先看技术结构"
DEGRADED_ACTION_REASON = "增量消息不足，先按技术结构保守处理。"
DEGRADED_CLOSE_ACTION_REASON = "盘后增量消息不足，先按技术结构制定明日计划。"


class AnalysisService:
    def __init__(self):
        self.config = ConfigLoader().config
        self.db = SentinelDB()
        self.validation_service = ValidationService(self.db, self.config)
        self.strategy_lab_service = StrategyLabService(self.db, self.config, self.validation_service)
        self.data_path = Path("data/latest_context.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_swing_strategy_preferences(self) -> Dict[str, Any]:
        swing_config = ((self.config.get("strategy") or {}).get("swing") or {})
        return build_investor_snapshot(
            portfolio=self.config.get("portfolio", []),
            watchlist=self.config.get("watchlist", []),
            portfolio_state=self.config.get("portfolio_state", {}),
            swing_config=swing_config,
        ).get("strategy_preferences", {})

    def _context_stock_codes(self, context: Optional[Dict[str, Any]]) -> set[str]:
        if not context:
            return set()
        return {
            str(stock.get("code", "") or "")
            for stock in (context.get("stocks") or [])
            if stock.get("code")
        }

    def _context_match_score(self, context: Optional[Dict[str, Any]], universe_codes: Optional[set[str]]) -> tuple[int, int]:
        codes = self._context_stock_codes(context)
        if not universe_codes:
            return len(codes), len(codes)
        return len(codes & universe_codes), len(codes)

    def _load_cached_context(self, mode: str, universe_codes: Optional[set[str]] = None) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        if self.data_path.exists():
            with open(self.data_path, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if mode != "swing":
                return cached
            if cached.get("stocks") or not universe_codes:
                candidates.append(cached)

        candidate_modes = [mode]
        if mode == "swing":
            candidate_modes.extend(["close", "midday"])

        for candidate_mode in candidate_modes:
            latest_record = self.db.get_latest_record(mode=candidate_mode)
            if latest_record:
                candidates.append(latest_record)

        if not candidates:
            return None

        return max(candidates, key=lambda item: self._context_match_score(item, universe_codes))

    def _align_swing_context_to_snapshot(
        self,
        context: Dict[str, Any],
        investor_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        aligned = dict(context or {})
        stock_map = {
            str(stock.get("code", "") or ""): dict(stock)
            for stock in (context.get("stocks") or [])
            if stock.get("code")
        }
        ordered_universe = investor_snapshot.get("universe") or []
        aligned_stocks: List[Dict[str, Any]] = []
        missing_codes: List[str] = []

        for asset in ordered_universe:
            code = str(asset.get("code", "") or "")
            if not code:
                continue
            stock = stock_map.get(code)
            if not stock:
                missing_codes.append(code)
                continue
            merged = dict(stock)
            merged["code"] = code
            merged["name"] = asset.get("name", merged.get("name", code))
            merged["strategy"] = asset.get("strategy", merged.get("strategy", "trend"))
            merged["priority"] = asset.get("priority", merged.get("priority", "normal"))
            merged["held"] = asset.get("held", False)
            merged["shares"] = int(asset.get("shares", merged.get("shares", 0)) or 0)
            if asset.get("cost") is not None:
                merged["cost"] = asset.get("cost")
            aligned_stocks.append(merged)

        aligned["stocks"] = aligned_stocks
        aligned["data_issues"] = []
        if missing_codes:
            aligned["data_issues"].append(
                "缓存行情未覆盖当前账户的全部标的："
                + "、".join(missing_codes[:5])
                + ("，请优先使用 --mode swing --dry-run 拉取实时数据。" if len(missing_codes) else "")
            )
        return aligned

    async def collect_and_process_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """Collects raw data and processes it into AI-ready context."""
        # 1. Collect Data (Async)
        collector = DataCollector()
        try:
            raw_data = await collector.collect_all(portfolio)

            market_breadth = raw_data['market_breadth']
            north_funds = raw_data['north_funds']
            stock_data_list = raw_data['stocks']
            indices = raw_data.get('indices', {})
            macro_news = raw_data.get('macro_news', {})

            logger.info(f"Data Collected. Market Breadth: {market_breadth}, North Funds: {north_funds}")

            # 1.5. Enrich stock data with portfolio config (strategy, cost)
            portfolio_map = {p['code']: p for p in portfolio}
            for stock_raw in stock_data_list:
                cfg = portfolio_map.get(stock_raw.get('code', ''), {})
                stock_raw['strategy'] = cfg.get('strategy', 'trend')
                stock_raw['cost'] = cfg.get('cost', 0)
                stock_raw['shares'] = cfg.get('shares', 0)

            # 2. Process Data (Indicators)
            processor = DataProcessor()
            processed_stocks = []
            for stock_raw in stock_data_list:
                stock_indicators = processor.calculate_indicators(stock_raw)
                processed_stocks.append(stock_indicators)

            # Pre-calculate signals (north_funds removed in v2.0)
            processed_stocks = processor.generate_signals(processed_stocks)

            return {
                "context_date": datetime.now().strftime('%Y-%m-%d'),
                "market_breadth": market_breadth,
                "north_funds": north_funds,
                "indices": indices,
                "macro_news": macro_news,
                "stocks": processed_stocks,
                "portfolio_state": self.config.get('portfolio_state', {}),
                "strategy_preferences": self._get_swing_strategy_preferences(),
                "collection_status": raw_data.get("collection_status", {}),
                "data_issues": raw_data.get("data_issues", []),
                "source_labels": raw_data.get("source_labels", []),
            }
        finally:
            collector.close()

    async def collect_and_process_morning_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """Collects and processes morning pre-market data."""
        collector = DataCollector()
        try:
            raw_data = await collector.collect_morning_data(portfolio)

            processor = DataProcessor()
            processed_data = processor.process_morning_data(raw_data, portfolio)
            processed_data["context_date"] = datetime.now().strftime('%Y-%m-%d')
            processed_data["collection_status"] = raw_data.get("collection_status", {})
            processed_data["data_issues"] = raw_data.get("data_issues", [])
            processed_data["source_labels"] = raw_data.get("source_labels", [])

            logger.info(f"Morning data collected. Global indices: {len(processed_data.get('global_indices', []))}, "
                         f"Commodities: {len(processed_data.get('commodities', []))}, "
                         f"Stocks: {len(processed_data.get('stocks', []))}")
            return processed_data
        finally:
            collector.close()

    def post_process_result(self, analysis_result: Dict, ai_input: Dict, mode: str = 'midday') -> Dict:
        """Injects real-time data back into analysis result for display."""
        if mode == 'morning':
            return self._post_process_morning(analysis_result, ai_input)
        if mode == 'swing':
            analysis_result.setdefault("summary", analysis_result.get("market_conclusion", ""))
            analysis_result.setdefault("quality_status", "normal")
            analysis_result.setdefault("quality_issues", [])
            analysis_result.setdefault("data_timestamp", ai_input.get("context_date"))
            analysis_result.setdefault("source_labels", ["rule_engine", "history"])
            return analysis_result

        indices = ai_input.get('indices', {})
        processed_stocks = ai_input.get('stocks', [])
        structured_map = {
            stock.get("code"): stock
            for stock in ai_input.get("structured_report", {}).get("stocks", [])
            if stock.get("code")
        }
        
        # 1. Format Indices Info
        indices_str = []
        for name, data in indices.items():
            pct = data.get('change_pct', 0.0)
            sign = "+" if pct > 0 else ""
            indices_str.append(f"{name} {sign}{pct}%")
        analysis_result['indices_info'] = " / ".join(indices_str)
        
        # 2. MATCH Stock Pct Change to Actions
        for action in analysis_result.get('actions', []):
            code = action.get('code')
            name = action.get('name')
            
            # Robust matching: try code first, then name
            stock_obj = None
            if code:
                for s in processed_stocks:
                    if s['code'] == code:
                        stock_obj = s
                        break
            
            if not stock_obj and name:
                for s in processed_stocks:
                    if s['name'] == name:
                        stock_obj = s
                        break
            
            if stock_obj:
                pct = stock_obj.get('pct_change', 0.0)
                current_price = stock_obj.get('current_price', 0.0)
                quote_status = stock_obj.get('quote_status', 'missing')
                action['quote_status'] = quote_status

                if quote_status == "fresh":
                    action['current_price'] = current_price
                    sign = "+" if pct > 0 else ""
                    color = "🔴" if pct > 0 else "🟢"
                    action['pct_change_str'] = f"`{color} {sign}{pct}%`"
                else:
                    if mode in {"midday", "preclose"}:
                        action['current_price'] = 0.0
                    action['pct_change_str'] = ""

                # 🔧 FIX: 传递 T+1 相关字段到 actions
                if 'tradeable' in stock_obj:
                    action['tradeable'] = stock_obj['tradeable']
                if 'signal_note' in stock_obj:
                    action['signal_note'] = stock_obj['signal_note']
                # 传递多维指标字段
                if 'signal' in stock_obj and not action.get('signal'):
                    action['signal'] = stock_obj['signal']
                if 'confidence' in stock_obj:
                    action['confidence'] = stock_obj['confidence']
                if 'tech_summary' in stock_obj:
                    action['tech_summary'] = stock_obj['tech_summary']
                structured_stock = structured_map.get(code)
                if structured_stock:
                    if not action.get('operation'):
                        action['operation'] = structured_stock.get('operation', action.get('operation', ''))
                    action['source_labels'] = structured_stock.get('source_labels', [])
                    action['data_timestamp'] = structured_stock.get('data_timestamp')
                    action['news_evidence'] = structured_stock.get('news_evidence', [])
            else:
                action['pct_change_str'] = ""

        # Pass through signal scorecard
        scorecard = ai_input.get('signal_scorecard')
        if scorecard:
            analysis_result['signal_scorecard'] = scorecard
        structured_report = ai_input.get("structured_report")
        if structured_report:
            analysis_result["structured_report"] = structured_report
            analysis_result["data_timestamp"] = structured_report.get("data_timestamp")
            analysis_result["source_labels"] = structured_report.get("source_labels", [])
        analysis_result.setdefault("data_issues", ai_input.get("data_issues", []))
        analysis_result.setdefault("collection_status", ai_input.get("collection_status", {}))

        return analysis_result

    def _post_process_morning(self, analysis_result: Dict, ai_input: Dict) -> Dict:
        """Injects raw overnight data into morning analysis result for Feishu display."""
        # Format global indices info
        global_indices = ai_input.get('global_indices', [])
        indices_parts = []
        for idx in global_indices:
            pct = idx.get('change_pct', 0)
            sign = "+" if pct > 0 else ""
            emoji = "🔴" if pct > 0 else "🟢"
            indices_parts.append(f"{emoji} {idx['name']} {sign}{pct}%")
        analysis_result['global_indices_info'] = "\n".join(indices_parts)

        # Format commodities info
        commodities = ai_input.get('commodities', [])
        commodity_parts = []
        for c in commodities:
            pct = c.get('change_pct', 0)
            sign = "+" if pct > 0 else ""
            commodity_parts.append(f"{c['name']} {sign}{pct}%")
        analysis_result['commodities_info'] = " / ".join(commodity_parts)

        # Format treasury info
        treasury = ai_input.get('us_treasury', {})
        if treasury:
            y10 = treasury.get('yield_10y', 0)
            y2 = treasury.get('yield_2y', 0)
            spread = treasury.get('spread_10y_2y', 0)
            analysis_result['treasury_info'] = f"10Y: {y10}% / 2Y: {y2}% / 利差: {spread}%"

        # Match overnight drivers to actions
        stocks = ai_input.get('stocks', [])
        for action in analysis_result.get('actions', []):
            code = action.get('code', '')
            for s in stocks:
                if s.get('code') == code:
                    if not action.get('overnight_driver'):
                        action['overnight_driver'] = s.get('overnight_driver_str', '')
                    if not action.get('ma20_status'):
                        action['ma20_status'] = s.get('ma20_status', 'NEAR')
                    break

        analysis_result.setdefault("data_issues", ai_input.get("data_issues", []))
        analysis_result.setdefault("source_labels", ai_input.get("source_labels", []))
        analysis_result.setdefault("collection_status", ai_input.get("collection_status", {}))

        return analysis_result

    async def run_analysis(
        self,
        mode: str,
        dry_run: bool = False,
        replay: bool = False,
        publish: bool = False,
        publish_target: list = None
    ) -> Dict:
        """
        Runs the full analysis pipeline.
        Returns the analysis result dict.
        """
        logger.info(f"=== Starting Analysis ({mode.upper()}) ===")

        run_guard = should_run_market_report(
            mode=mode,
            publish=publish,
            replay=replay,
            dry_run=dry_run,
        )
        if not run_guard["should_run"]:
            message = f"Skipping {mode} analysis on non-trading day {run_guard['calendar']['date']}"
            logger.info(message)
            return {
                "skipped": True,
                "reason": run_guard["skip_reason"],
                "message": message,
                "calendar": run_guard["calendar"],
            }
        
        portfolio = self.config.get('portfolio', [])
        investor_snapshot = build_investor_snapshot(
            portfolio=portfolio,
            watchlist=self.config.get("watchlist", []),
            portfolio_state=self.config.get("portfolio_state", {}),
            swing_config=((self.config.get("strategy") or {}).get("swing") or {}),
        )
        market_universe = investor_snapshot["universe"] if mode == "swing" else portfolio
        ai_input = None

        # --- Step 1: Data Preparation ---
        if replay:
            universe_codes = {
                str(item.get("code", "") or "")
                for item in investor_snapshot.get("universe", [])
                if item.get("code")
            } if mode == "swing" else None
            cached_context = self._load_cached_context(mode, universe_codes=universe_codes)
            if cached_context:
                logger.info("Replay Mode: Loading cached data...")
                ai_input = (
                    self._align_swing_context_to_snapshot(cached_context, investor_snapshot)
                    if mode == "swing"
                    else cached_context
                )
            elif replay:
                logger.error("No historical data found for replay.")
                return {"error": "No replay data"}
        else:
            if not market_universe:
                logger.warning("Market universe is empty.")
                return {"error": "Portfolio is empty" if mode != "swing" else "Portfolio and watchlist are empty"}
            
            try:
                if mode == 'morning':
                    ai_input = await self.collect_and_process_morning_data(portfolio)
                else:
                    ai_input = await self.collect_and_process_data(market_universe)
                # Save context
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(ai_input, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Data collection failed: {e}")
                return {"error": str(e)}

        # --- Step 1.5: Signal Tracking ---
        if mode in ('midday', 'close') and not dry_run:
            analysis_date = ai_input.get("context_date") or datetime.now().strftime('%Y-%m-%d')
            scorecard = self._compute_signal_scorecard(
                ai_input.get('stocks', []),
                mode=mode,
                analysis_date=analysis_date,
            )
            if scorecard:
                ai_input['signal_scorecard'] = scorecard

        quality_input = {"status": "normal", "issues": []}
        quality_detail = ""
        if mode in ('midday', 'preclose', 'close'):
            quality_input = evaluate_input_quality(ai_input, mode=mode)
            quality_detail = build_quality_detail(ai_input, quality_input["issues"], mode=mode)
            ai_input["quality_input"] = quality_input
            ai_input["quality_detail"] = quality_detail
            ai_input["structured_report"] = build_structured_report(
                ai_input,
                mode=mode,
                quality_status=quality_input["status"],
            )
            if quality_input["status"] == "blocked" and not dry_run:
                return self._build_blocked_report(
                    mode,
                    ai_input["structured_report"],
                    quality_input["issues"],
                    quality_detail,
                )
        collection_quality_status = (
            "degraded"
            if (ai_input.get("collection_status") or {}).get("overall_status") == "degraded"
            else "normal"
        )
        collection_quality_issues = list(ai_input.get("data_issues", []) or [])

        # --- Step 2: AI Analysis ---
        analysis_result = {}
        
        try:
            if mode == "swing":
                analysis_date = ai_input.get("context_date") or datetime.now().strftime('%Y-%m-%d')
                ai_input.setdefault("portfolio_state", investor_snapshot.get("portfolio_state", {}))
                ai_input.setdefault("strategy_preferences", investor_snapshot.get("strategy_preferences", {}))
                ai_input.setdefault("holdings", investor_snapshot.get("holdings", []))
                ai_input.setdefault("watchlist", investor_snapshot.get("watchlist", []))
                ai_input.setdefault("held_codes", investor_snapshot.get("held_codes", set()))
                ai_input.setdefault("watchlist_codes", investor_snapshot.get("watchlist_codes", set()))
                swing_quality_guard = build_swing_quality_guard(ai_input)
                ai_input.setdefault("swing_quality_guard", swing_quality_guard)
                historical_records = self._get_swing_history_records(days=90)
                validation_report = self._compute_swing_validation_report(historical_records)
                if validation_report:
                    validation_compact = self._build_compact_validation_snapshot(validation_report)
                    validation_report = {**validation_report, "compact": validation_compact}
                    ai_input.setdefault("performance_context", validation_report.get("performance_context", {}))
                    ai_input.setdefault("validation_report", validation_report)
                analysis_result = build_swing_report(ai_input, historical_records, analysis_date)
                if validation_report:
                    if validation_report.get("scorecard"):
                        analysis_result["swing_scorecard"] = validation_report.get("scorecard")
                    analysis_result["validation_report"] = validation_report
                    analysis_result["validation_compact"] = validation_report.get("compact")
                analysis_result["lab_hint"] = self._build_swing_lab_hint()
                analysis_result.setdefault("summary", analysis_result.get("market_conclusion", ""))
                analysis_result.setdefault("quality_status", collection_quality_status)
                analysis_result.setdefault("quality_issues", collection_quality_issues)
                analysis_result.setdefault("data_timestamp", analysis_date)
                analysis_result.setdefault("source_labels", ["rule_engine", "history"])
                analysis_result.setdefault("data_issues", ai_input.get("data_issues", []))
                analysis_result.setdefault("collection_status", ai_input.get("collection_status", {}))
                analysis_result.setdefault("execution_readiness", swing_quality_guard.get("execution_readiness"))
                analysis_result.setdefault("quality_summary", swing_quality_guard.get("summary"))
                analysis_result.setdefault("trade_guard", swing_quality_guard)
            elif mode in ("midday", "preclose", "close") and quality_input["status"] == "degraded":
                analysis_result = self._build_degraded_report(
                    mode,
                    ai_input["structured_report"],
                    quality_input["issues"],
                    quality_detail,
                )
            elif mode in ("midday", "preclose", "close"):
                historical_records = self._get_swing_history_records(days=90)
                strategy_snapshot = build_strategy_snapshot(
                    ai_input,
                    historical_records=historical_records,
                    mode=mode,
                )
                if mode == "close":
                    analysis_result = build_close_rule_report(
                        ai_input,
                        strategy_snapshot,
                        scorecard=ai_input.get("signal_scorecard"),
                    )
                else:
                    analysis_result = build_intraday_rule_report(
                        ai_input,
                        strategy_snapshot,
                        mode=mode,
                        scorecard=ai_input.get("signal_scorecard"),
                    )
                analysis_result.setdefault("strategy_snapshot", strategy_snapshot)
                analysis_result.setdefault("structured_report", ai_input.get("structured_report"))
                analysis_result.setdefault("data_timestamp", ai_input.get("structured_report", {}).get("data_timestamp"))
                analysis_result.setdefault("source_labels", ai_input.get("structured_report", {}).get("source_labels", []))
            elif dry_run:
                logger.info("Dry Run Mode: Mocking AI response.")
                for s in ai_input.get('stocks', []):
                    logger.info(f"[DRY-RUN TAGS] {s['name']} Tech: {s.get('tech_summary')}")
                analysis_result = {
                    "market_sentiment": "DryRun",
                    "summary": "This is a dry run.",
                    "actions": [],
                    "quality_status": collection_quality_status if mode in ("morning", "swing") else quality_input["status"],
                    "quality_issues": collection_quality_issues if mode in ("morning", "swing") else quality_input["issues"],
                    "structured_report": ai_input.get("structured_report"),
                    "data_timestamp": ai_input.get("structured_report", {}).get("data_timestamp"),
                    "source_labels": ai_input.get("structured_report", {}).get("source_labels", []),
                    "data_issues": ai_input.get("data_issues", []),
                    "collection_status": ai_input.get("collection_status", {}),
                }
            else:
                analyst = GeminiClient()
                if mode == 'morning':
                    system_prompt = self.config['prompts'].get('morning_brief')
                    if system_prompt:
                        analysis_result = analyst.analyze_morning(ai_input, system_prompt)
                    else:
                        logger.error("Morning brief prompt not found in config!")
                        return {"error": "Missing morning_brief prompt"}

            # Unified Post-Processing
            analysis_result = self.post_process_result(analysis_result, ai_input, mode=mode)
            if mode in ("midday", "preclose", "close") and not dry_run:
                output_quality = evaluate_output_quality(
                    analysis_result,
                    ai_input.get("structured_report", {}),
                    mode=mode,
                )
                if quality_input["status"] == "normal" and output_quality["status"] == "degraded":
                    analysis_result = self._build_degraded_report(
                        mode,
                        ai_input["structured_report"],
                        output_quality["issues"],
                        build_quality_detail(ai_input, output_quality["issues"], mode=mode),
                    )
                    analysis_result = self.post_process_result(analysis_result, ai_input, mode=mode)
                if "quality_status" not in analysis_result:
                    analysis_result["quality_status"] = "normal" if output_quality["status"] == "normal" else "degraded"
                analysis_result["quality_issues"] = output_quality["issues"] if output_quality["issues"] else quality_input["issues"]
                analysis_result["quality_detail"] = (
                    build_quality_detail(ai_input, output_quality["issues"], mode=mode)
                    if output_quality["issues"]
                    else quality_detail
                )
            elif mode in ("midday", "preclose", "close"):
                analysis_result.setdefault("quality_status", quality_input["status"])
                analysis_result.setdefault("quality_issues", quality_input["issues"])
                analysis_result.setdefault("quality_detail", quality_detail)
            else:
                analysis_result.setdefault("quality_status", collection_quality_status)
                analysis_result.setdefault("quality_issues", collection_quality_issues)
            
            logger.info(f"{mode.capitalize()} Analysis Completed.")
            
        except Exception as e:
            logger.error(f"AI Analysis Failed: {e}")
            return {"error": f"AI Analysis Failed: {e}"}

        # --- Step 3: Reporting ---
        if dry_run:
            logger.info("Dry Run Mode: Skipping push.")
        elif publish:
            targets = self._normalize_publish_targets(publish_target)
            for target in targets:
                try:
                    if target == "telegram":
                        reporter = TelegramClient()
                        if mode == 'midday':
                            reporter.send_midday_report(analysis_result)
                        elif mode == 'preclose':
                            reporter.send_preclose_report(analysis_result)
                        elif mode == 'close':
                            reporter.send_close_report(analysis_result)
                        elif mode == 'morning':
                            reporter.send_morning_report(analysis_result)
                        elif mode == 'swing':
                            reporter.send_swing_report(analysis_result)
                    else:
                        reporter = FeishuClient()
                        if mode == 'midday':
                            reporter.send_card(analysis_result)
                        elif mode == 'preclose':
                            reporter.send_preclose_card(analysis_result)
                        elif mode == 'close':
                            reporter.send_close_card(analysis_result)
                        elif mode == 'morning':
                            reporter.send_morning_card(analysis_result)
                        elif mode == 'swing':
                            reporter.send_swing_card(analysis_result)
                    logger.info(f"Published to {target}")
                except Exception as e:
                    logger.error(f"Failed to publish to {target}: {e}")
        else:
            logger.info("Publish not requested: Skipping push.")

        # --- Step 4: Persistence ---
        if not dry_run or (dry_run and replay):
            if not dry_run: 
                self.db.save_record(mode=mode, ai_input=ai_input, ai_analysis=analysis_result)

        logger.info(f"=== Analysis ({mode.upper()}) Finished ===")
        return analysis_result

    def _build_blocked_report(
        self,
        mode: str,
        structured_report: Dict[str, Any],
        issues: List[str],
        quality_detail: str,
    ) -> Dict[str, Any]:
        return {
            "error": "Insufficient input quality for report generation",
            "mode": mode,
            "quality_status": "blocked",
            "quality_issues": issues,
            "quality_detail": quality_detail,
            "structured_report": structured_report,
            "data_timestamp": structured_report.get("data_timestamp"),
            "source_labels": structured_report.get("source_labels", []),
        }

    def _build_degraded_report(
        self,
        mode: str,
        structured_report: Dict[str, Any],
        issues: List[str],
        quality_detail: str,
    ) -> Dict[str, Any]:
        actions = []
        for stock in structured_report.get("stocks", []):
            base_action = {
                "code": stock.get("code"),
                "name": stock.get("name"),
                "signal": stock.get("signal"),
                "confidence": stock.get("confidence"),
                "operation": stock.get("operation"),
                "current_price": stock.get("current_price", 0.0),
                "pct_change_str": "",
                "tech_summary": stock.get("tech_evidence", ""),
                "source_labels": stock.get("source_labels", []),
                "data_timestamp": stock.get("data_timestamp"),
            }
            evidence_text = " / ".join(stock.get("news_evidence", [])[:2]).strip()
            if mode == "close":
                base_action["today_review"] = DEGRADED_CLOSE_REVIEW
                base_action["tomorrow_plan"] = stock.get("operation")
                base_action["reason"] = evidence_text or DEGRADED_CLOSE_ACTION_REASON
            else:
                base_action["reason"] = evidence_text or DEGRADED_ACTION_REASON
            actions.append(base_action)

        top = {
            "quality_status": "degraded",
            "quality_issues": issues,
            "quality_detail": quality_detail,
            "structured_report": structured_report,
            "data_timestamp": structured_report.get("data_timestamp"),
            "source_labels": structured_report.get("source_labels", []),
            "actions": actions,
        }
        if mode == "close":
            top.update({
                "market_summary": DEGRADED_CLOSE_SUMMARY,
                "market_temperature": DEGRADED_OVERVIEW_LABEL,
            })
        else:
            top.update({
                "market_sentiment": DEGRADED_OVERVIEW_LABEL,
                "volume_analysis": "N/A",
                "macro_summary": DEGRADED_INTRADAY_SUMMARY,
                "indices_info": structured_report.get("market", {}).get("indices_info", ""),
            })
        return top

    async def ask_question(self, question: str, date: str = None, mode: str = 'midday') -> str:
        """
        Q&A mode: answer user questions based on cached data.
        Detects trend keywords and routes to trend analysis if needed.
        """
        logger.info(f"=== Q&A Mode: '{question}' ===")

        # Detect accuracy query
        if mode == "swing":
            if self._detect_accuracy_query(question):
                return self._run_swing_accuracy_report()
            return self._run_swing_question(question)

        if self._detect_accuracy_query(question):
            return self._run_accuracy_report(mode=mode)

        # Detect trend question
        if self._detect_trend(question):
            return await self._run_trend_analysis(question)

        # Single-day question: load cached data
        if date:
            raw_data = self.db.get_record_by_date(date, mode)
            ai_result = self.db.get_analysis_by_date(date, mode)
        else:
            record = self.db.get_last_analysis(mode)
            if record:
                raw_data = record.get('raw_data')
                ai_result = record.get('ai_result')
            else:
                raw_data = None
                ai_result = None

        if not raw_data and not ai_result:
            return "没有找到缓存的分析数据。请先运行一次分析（python -m src.main --mode midday）再进行追问。"

        analyst = GeminiClient()
        qa_prompt = self.config['prompts'].get('qa_prompt', '')
        answer = analyst.ask_question(raw_data, ai_result, question, qa_prompt)
        return answer

    def _detect_trend(self, question: str) -> bool:
        """Detect if the question is about trends (multi-day analysis)."""
        trend_keywords = ['趋势', '走势', '一周', '一个月', '近期', '最近', '这周', '本周', '上周', '本月', '上月', '几天', '多天']
        return any(kw in question for kw in trend_keywords)

    def _normalize_publish_targets(self, publish_target) -> List[str]:
        if not publish_target:
            return ["feishu"]
        if isinstance(publish_target, str):
            return [publish_target]
        return list(publish_target)

    def _compute_signal_scorecard(
        self,
        today_stocks: List[Dict],
        mode: str = 'midday',
        analysis_date: str = None,
    ) -> Optional[Dict]:
        """Compute scorecard by mode-specific signal follow-up semantics."""
        try:
            analysis_date = analysis_date or datetime.now().strftime('%Y-%m-%d')

            if mode == 'close':
                baseline = self.db.get_latest_analysis_for_date(mode='midday', target_date=analysis_date)
                comparison_mode = 'intraday_followup'
                comparison_label = '今日午盘信号 -> 今日收盘验证'
                rolling = self._compute_intraday_scorecard_stats(days=7)
            else:
                baseline = self.db.get_previous_analysis(mode='midday', before_date=analysis_date)
                comparison_mode = 'overnight_followup'
                comparison_label = '昨日午盘信号 -> 今日午盘验证'
                records = self.db.get_records_range(mode='midday', days=8)
                rolling = calculate_rolling_stats(records, days=7)

            if not baseline or not baseline.get('ai_result'):
                logger.info("Signal Tracker: No baseline data, skipping scorecard.")
                return None

            yesterday_actions = baseline['ai_result'].get('actions', [])
            if not yesterday_actions or not today_stocks:
                return None

            eval_results = evaluate_yesterday(yesterday_actions, today_stocks)
            scorecard = build_scorecard(
                eval_results,
                rolling,
                comparison_mode=comparison_mode,
                comparison_label=comparison_label,
            )
            logger.info(f"Signal Tracker: {scorecard.get('summary_text', '')}")
            return scorecard
        except Exception as e:
            logger.warning(f"Signal Tracker failed: {e}")
            return None

    def _compute_intraday_scorecard_stats(self, days: int = 7) -> Dict:
        midday_records = self.db.get_records_range(mode='midday', days=days)
        pairs = []
        for midday_record in midday_records:
            target_date = midday_record.get('date')
            if not target_date:
                continue
            close_record = self.db.get_latest_analysis_for_date(mode='close', target_date=target_date)
            if not close_record:
                continue
            pairs.append({
                "actions": midday_record.get('ai_result', {}).get('actions', []),
                "stocks": close_record.get('raw_data', {}).get('stocks', []),
            })
        return calculate_pair_rolling_stats(pairs, days=days)

    def _detect_accuracy_query(self, question: str) -> bool:
        """Detect if the question is about signal accuracy."""
        keywords = ['准确率', '命中率', '准不准', '靠谱', '可靠', '信得过', '历史表现', '胜率', '准吗', '准么', '靠谱吗', '可信']
        return any(kw in question for kw in keywords)

    def _run_accuracy_report(self, mode: str = "midday") -> str:
        """Generate a formatted accuracy report."""
        if mode == "swing":
            return self._run_swing_accuracy_report()

        records = self.db.get_records_range(mode='midday', days=31)

        stats_7d = calculate_rolling_stats(records[:8], days=7)
        stats_30d = calculate_rolling_stats(records, days=30)

        lines = ["📊 信号追踪准确率报告", ""]

        def _format_stats(label, stats):
            total = stats.get('total', 0)
            if total == 0:
                return [f"**{label}**: 数据不足，暂无统计"]
            parts = [f"**{label}**: 命中率 {int(stats['hit_rate']*100)}% ({stats['hits']}/{total})"]
            # 风险信号命中率（剥离SAFE）
            risk = _compute_risk_stats(stats.get('by_signal', {}))
            if risk['total'] > 0:
                parts.append(f"  - 风险信号(DANGER/WARNING/OVERBOUGHT): {int(risk['rate']*100)}% ({risk['hits']}/{risk['total']})")
            # 买入信号命中率
            buy = _compute_buy_stats(stats.get('by_signal', {}))
            if buy['total'] > 0:
                parts.append(f"  - 买入信号(OPPORTUNITY/ACCUMULATE): {int(buy['rate']*100)}% ({buy['hits']}/{buy['total']})")
            for conf, cs in stats.get('by_confidence', {}).items():
                if cs['total'] > 0:
                    parts.append(f"  - {conf}置信度: {int(cs['rate']*100)}% ({cs['hits']}/{cs['total']})")
            for sig, ss in stats.get('by_signal', {}).items():
                if ss['total'] > 0:
                    parts.append(f"  - {sig}: {int(ss['rate']*100)}% ({ss['hits']}/{ss['total']})")
            return parts

        lines.extend(_format_stats("近7日", stats_7d))
        lines.append("")
        lines.extend(_format_stats("近30日", stats_30d))

        return "\n".join(lines)

    def _get_swing_history_records(self, days: int = 90) -> List[Dict]:
        return self.validation_service._get_swing_history_records(days=days)

    def _get_swing_report_records(self, days: int = 90) -> List[Dict]:
        return self.validation_service._get_swing_report_records(days=days)

    def _build_swing_benchmark_map(self, records: List[Dict]) -> Dict[str, str]:
        benchmark_map = {}
        available_codes = {
            str(stock.get("code"))
            for record in records
            for stock in ((record.get("raw_data") or {}).get("stocks", []) or [])
            if stock.get("code")
        }
        for record in records:
            for stock in (record.get("raw_data") or {}).get("stocks", []) or []:
                code = stock.get("code")
                if not code or code in benchmark_map:
                    continue

                benchmark_code = resolve_benchmark_code(stock, available_codes)
                if benchmark_code:
                    benchmark_map[code] = benchmark_code
        return benchmark_map

    def _compute_swing_scorecard(self, historical_records: List[Dict]) -> Optional[Dict]:
        validation_report = self._compute_swing_validation_report(historical_records)
        if not validation_report:
            return None
        return validation_report.get("scorecard")

    def _build_synthetic_swing_records(self, historical_records: List[Dict]) -> List[Dict]:
        if not historical_records:
            return []

        sorted_records = sorted(historical_records, key=lambda item: item.get("date", ""))
        synthetic_records = []

        for index, record in enumerate(sorted_records):
            raw_data = record.get("raw_data") or {}
            if not raw_data.get("stocks"):
                continue
            report_input = dict(raw_data)
            report_input.setdefault("strategy_preferences", self._get_swing_strategy_preferences())

            context_window = sorted_records[max(0, index - 20): index + 1]
            swing_report = build_swing_report(
                report_input,
                context_window,
                analysis_date=record.get("date") or datetime.now().strftime('%Y-%m-%d'),
            )
            actions = [
                {
                    "code": action.get("code"),
                    "name": action.get("name"),
                    "action_label": action.get("action_label"),
                    "confidence": action.get("confidence"),
                    "target_weight": action.get("target_weight") if action.get("action_label") in {"增配", "减配", "回避"} else None,
                }
                for action in swing_report.get("actions", [])
                if action.get("code") and action.get("action_label")
            ]
            if not actions:
                continue

            synthetic_records.append(
                {
                    "date": record.get("date"),
                    "raw_data": raw_data,
                    "ai_result": {"actions": actions},
                }
            )

        return synthetic_records

    def _primary_window_stats(
        self,
        scorecard: Optional[Dict[str, Any]],
        *,
        bucket: str = "overall",
        action_label: Optional[str] = None,
        preferred_windows: tuple[int, ...] = (20, 10, 40),
    ) -> tuple[Optional[int], Dict[str, Any]]:
        stats_root = ((scorecard or {}).get("stats") or {}).get(bucket, {})
        if action_label is not None:
            stats_root = stats_root.get(action_label, {})
        available_windows = [int(window) for window in ((scorecard or {}).get("windows") or [])]
        search_windows = list(preferred_windows) + sorted(
            [window for window in available_windows if window not in preferred_windows],
            reverse=True,
        )
        primary_window = next((window for window in search_windows if stats_root.get(window, {}).get("count", 0) > 0), None)
        return primary_window, stats_root.get(primary_window, {}) if primary_window is not None else {}

    def _build_live_validation_summary_text(self, scorecard: Optional[Dict[str, Any]]) -> str:
        primary_window, stats = self._primary_window_stats(scorecard, preferred_windows=(20, 10, 40))
        if primary_window is None:
            return "真实建议跟踪样本还不够，先继续积累。"

        count = int(stats.get("count", 0) or 0)
        avg_return = float(stats.get("avg_absolute_return", 0.0) or 0.0)
        avg_relative = stats.get("avg_relative_return")
        avg_drawdown = float(stats.get("avg_max_drawdown", 0.0) or 0.0)
        by_action = ((scorecard or {}).get("stats") or {}).get("by_action", {})
        add_stats = (by_action.get("增配") or {}).get(primary_window, {})
        add_count = int(add_stats.get("count", 0) or 0)
        add_return = float(add_stats.get("avg_absolute_return", 0.0) or 0.0)

        parts = [f"真实建议跟踪近90天已兑现{primary_window}日建议{count}笔"]
        if avg_relative is not None:
            if float(avg_relative) >= 0:
                parts.append(f"平均跑赢基准{avg_relative * 100:.1f}%")
            else:
                parts.append(f"平均落后基准{abs(float(avg_relative)) * 100:.1f}%")
        else:
            parts.append(f"平均收益{avg_return * 100:.1f}%")

        if add_count > 0:
            parts.append(f"增配组平均收益{add_return * 100:.1f}%")
        parts.append(f"平均回撤{avg_drawdown * 100:.1f}%")
        if count < 5:
            verdict = "样本还少，先继续积累。"
        elif avg_relative is not None and float(avg_relative) <= 0:
            verdict = "暂时没有稳定跑赢基准，先别主动放大仓位。"
        elif avg_drawdown <= -0.10:
            verdict = "有收益但回撤偏大，进攻也要留撤退空间。"
        else:
            verdict = "这套建议近期仍有效，可以继续进攻，但继续分批。"
        return "，".join(parts) + f"；{verdict}"

    def _build_validation_performance_context(
        self,
        scorecard: Optional[Dict[str, Any]],
        backtest_report: Optional[Dict[str, Any]],
        live_scorecard: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = build_default_performance_context()
        live_window, live_stats = self._primary_window_stats(
            live_scorecard,
            bucket="by_action",
            action_label="增配",
        )
        synthetic_window, synthetic_stats = self._primary_window_stats(
            scorecard,
            bucket="by_action",
            action_label="增配",
        )

        gate = {"allowed": False, "reason": "样本不足"}
        if live_window is not None and int(live_stats.get("count", 0) or 0) >= 5:
            live_gate = gate_offensive_setup(live_stats)
            gate = {
                "allowed": bool(live_gate.get("allowed")),
                "reason": f"真实建议{live_gate.get('reason', '')}",
            }
        elif synthetic_window is not None:
            gate = gate_offensive_setup(synthetic_stats)

        if backtest_report and int(backtest_report.get("trade_count", 0) or 0) >= 3:
            if float(backtest_report.get("total_return", 0) or 0) <= 0:
                gate = {"allowed": False, "reason": "正式回测收益不达标"}
            elif float(backtest_report.get("max_drawdown", 0) or 0) <= -0.12:
                gate = {"allowed": False, "reason": "正式回测回撤偏大"}
            elif gate.get("allowed"):
                gate = {"allowed": True, "reason": f"{gate.get('reason', '样本通过')}，正式回测未见明显恶化"}

        context["offensive"]["pullback_resume"] = gate
        return context

    def _build_validation_summary_text(
        self,
        live_report: Optional[Dict[str, Any]],
        scorecard: Optional[Dict[str, Any]],
        backtest_report: Optional[Dict[str, Any]],
        walkforward_report: Optional[Dict[str, Any]],
    ) -> str:
        live_scorecard = (live_report or {}).get("scorecard")
        live_window, live_stats = self._primary_window_stats(live_scorecard, preferred_windows=(20, 10, 40))

        if live_window is not None and int(live_stats.get("count", 0) or 0) >= 5:
            evidence_parts: List[str] = []
            if (live_report or {}).get("summary_text"):
                evidence_parts.append(str(live_report["summary_text"]).strip())

            trade_count = int((backtest_report or {}).get("trade_count", 0) or 0)
            if trade_count >= 3:
                evidence_parts.append(
                    f"正式回测收益{float((backtest_report or {}).get('total_return', 0.0) or 0.0) * 100:.1f}%，"
                    f"最大回撤{float((backtest_report or {}).get('max_drawdown', 0.0) or 0.0) * 100:.1f}%，"
                    f"交易{trade_count}笔"
                )
            if (walkforward_report or {}).get("segment_count", 0) > 0:
                evidence_parts.append(
                    f"滚动验证{walkforward_report['segment_count']}段，平均收益{walkforward_report['avg_total_return'] * 100:.1f}%"
                )

            return " 参考：".join([evidence_parts[0], "；".join(evidence_parts[1:]) + "。"]) if len(evidence_parts) > 1 else evidence_parts[0]

        primary_window, stats = self._primary_window_stats(scorecard, preferred_windows=(20, 10, 40))
        count = int(stats.get("count", 0) or 0)
        avg_return = float(stats.get("avg_absolute_return", 0.0) or 0.0)
        avg_relative = stats.get("avg_relative_return")
        avg_drawdown = float(stats.get("avg_max_drawdown", 0.0) or 0.0)
        trade_count = int((backtest_report or {}).get("trade_count", 0) or 0)
        backtest_return = float((backtest_report or {}).get("total_return", 0.0) or 0.0)
        backtest_drawdown = float((backtest_report or {}).get("max_drawdown", 0.0) or 0.0)

        if count < 8:
            verdict = "历史样本还不够，当前先把这套信号当辅助参考，不单独放大仓位。"
        elif avg_return <= 0 or (isinstance(avg_relative, (int, float)) and avg_relative < 0):
            verdict = "最近这套中期动作没有体现出明显优势，先别因为它主动放大仓位。"
        elif avg_drawdown <= -0.10 or (trade_count >= 3 and backtest_drawdown <= -0.12):
            verdict = "这套中期动作有机会，但历史回撤偏大，进攻也要预留撤退空间。"
        else:
            verdict = "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。"

        evidence_parts: List[str] = []
        if primary_window is not None:
            details = [
                f"{primary_window}日样本{count}",
                f"平均收益{avg_return * 100:.1f}%",
            ]
            if isinstance(avg_relative, (int, float)):
                if avg_relative >= 0:
                    details.append(f"平均跑赢基准{avg_relative * 100:.1f}%")
                else:
                    details.append(f"平均落后基准{abs(avg_relative) * 100:.1f}%")
            details.append(f"平均回撤{avg_drawdown * 100:.1f}%")
            evidence_parts.append("，".join(details))

        if trade_count >= 3:
            evidence_parts.append(
                f"回测收益{backtest_return * 100:.1f}%，最大回撤{backtest_drawdown * 100:.1f}%，交易{trade_count}笔"
            )
        else:
            evidence_parts.append("正式回测样本还不够，先别把这一段结果当成定论")

        if (walkforward_report or {}).get("segment_count", 0) > 0:
            evidence_parts.append(
                f"滚动验证{walkforward_report['segment_count']}段，平均收益{walkforward_report['avg_total_return'] * 100:.1f}%"
            )

        if not evidence_parts:
            return verdict
        return f"{verdict} 参考：{'；'.join(evidence_parts)}。"

    def _extract_validation_verdict(self, summary_text: str) -> str:
        text = str(summary_text or "").strip()
        if not text:
            return "中期策略统计数据不足，暂无报告。"
        if "参考：" in text:
            return text.split("参考：", 1)[0].strip()
        if "；" in text:
            return text.rsplit("；", 1)[-1].strip()
        return text

    def _build_compact_validation_snapshot(
        self,
        validation_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.validation_service._build_compact_validation_snapshot(validation_report)

    def _build_live_validation_records(
        self,
        swing_records: List[Dict[str, Any]],
        close_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for record in sorted(close_records, key=lambda item: item.get("date", "")):
            record_date = record.get("date")
            if not record_date:
                continue
            merged.setdefault(record_date, {"date": record_date, "raw_data": None, "ai_result": None})
            if record.get("raw_data"):
                merged[record_date]["raw_data"] = record.get("raw_data")

        for record in sorted(swing_records, key=lambda item: item.get("date", "")):
            record_date = record.get("date")
            if not record_date:
                continue
            merged.setdefault(record_date, {"date": record_date, "raw_data": None, "ai_result": None})
            if merged[record_date].get("raw_data") is None and record.get("raw_data"):
                merged[record_date]["raw_data"] = record.get("raw_data")

            actions = []
            for action in ((record.get("ai_result") or {}).get("actions") or []):
                if not action.get("code"):
                    continue
                label = str(
                    action.get("action_label")
                    or action.get("conclusion")
                    or action.get("operation")
                    or "观察"
                )
                actions.append(
                    {
                        "code": action.get("code"),
                        "name": action.get("name", action.get("code")),
                        "action_label": label,
                        "confidence": action.get("confidence", "未知"),
                    }
                )
            if actions:
                merged[record_date]["ai_result"] = {"actions": actions}

        ordered = []
        for record_date in sorted(merged):
            record = merged[record_date]
            stocks = ((record.get("raw_data") or {}).get("stocks") or [])
            if stocks:
                ordered.append(record)
        return ordered

    def _compute_live_swing_validation_report(
        self,
        swing_records: List[Dict[str, Any]],
        close_records: List[Dict[str, Any]],
        benchmark_map: Optional[Dict[str, str]] = None,
        windows: tuple[int, ...] = (10, 20, 40),
    ) -> Optional[Dict[str, Any]]:
        return self.validation_service._compute_live_swing_validation_report(
            swing_records,
            close_records,
            benchmark_map=benchmark_map,
            windows=windows,
        )

    def _compute_swing_validation_report(self, historical_records: List[Dict]) -> Optional[Dict]:
        if not historical_records:
            return None

        sorted_records = sorted(historical_records, key=lambda item: item.get("date", ""))
        live_report = self._compute_live_swing_validation_report(
            self._get_swing_report_records(days=max(len(sorted_records), 90)),
            sorted_records,
            benchmark_map=self._build_swing_benchmark_map(sorted_records),
        )
        synthetic_records = self._build_synthetic_swing_records(sorted_records)
        if not synthetic_records:
            return {
                "live": live_report,
                "scorecard": None,
                "backtest": {
                    "summary_text": "正式回测样本不足，暂不放大解释",
                    "total_return": 0.0,
                    "max_drawdown": 0.0,
                    "trade_count": 0,
                    "trades": [],
                    "equity_curve": [],
                },
                "walkforward": {"segment_count": 0, "segments": [], "avg_total_return": 0.0},
                "performance_context": self.validation_service._build_validation_performance_context(
                    None,
                    None,
                    (live_report or {}).get("scorecard"),
                ),
                "summary_text": self.validation_service._build_validation_summary_text(
                    live_report,
                    None,
                    None,
                    None,
                ),
            }

        scorecard = build_swing_scorecard(
            synthetic_records,
            benchmark_map=self._build_swing_benchmark_map(sorted_records),
            windows=(10, 20, 40),
        )

        lot_size = int((self.config.get("portfolio_state") or {}).get("lot_size", 100) or 100)
        backtest_result = run_deterministic_backtest(
            synthetic_records,
            initial_cash=100_000.0,
            lot_size=lot_size,
        )
        backtest_report = {
            "total_return": backtest_result.get("total_return", 0.0),
            "max_drawdown": backtest_result.get("max_drawdown", 0.0),
            "trade_count": len(backtest_result.get("trades", []) or []),
            "summary_text": "",
            "trades": backtest_result.get("trades", []) or [],
            "equity_curve": backtest_result.get("equity_curve", []) or [],
            "final_value": backtest_result.get("final_value", 0.0),
            "initial_value": backtest_result.get("initial_value", 0.0),
        }
        if backtest_report["trade_count"] >= 3:
            backtest_report["summary_text"] = (
                f"回测收益{backtest_result.get('total_return', 0.0) * 100:.1f}%，"
                f"最大回撤{backtest_result.get('max_drawdown', 0.0) * 100:.1f}%，"
                f"交易{len(backtest_result.get('trades', []) or [])}笔"
            )
        else:
            backtest_report["summary_text"] = "正式回测样本不足，暂不放大解释"
        walkforward_report = (
            run_walkforward_validation(
                synthetic_records,
                train_window=2,
                test_window=2,
                initial_cash=100_000.0,
            )
            if len(synthetic_records) >= 4
            else {"segment_count": 0, "segments": [], "avg_total_return": 0.0}
        )
        performance_context = self.validation_service._build_validation_performance_context(
            scorecard,
            backtest_report,
            (live_report or {}).get("scorecard"),
        )

        return {
            "live": live_report,
            "scorecard": scorecard,
            "backtest": backtest_report,
            "walkforward": walkforward_report,
            "performance_context": performance_context,
            "summary_text": self.validation_service._build_validation_summary_text(
                live_report,
                scorecard,
                backtest_report,
                walkforward_report,
            ),
        }

    def build_validation_snapshot(self, mode: str) -> Dict[str, Any]:
        if mode == "swing":
            historical_records = self._get_swing_history_records(days=90)
            validation_report = self._compute_swing_validation_report(historical_records)
            if not validation_report:
                return {"mode": mode, "summary_text": "中期策略统计数据不足，暂无报告。"}

            latest_record_date = max(
                (str(record.get("date", "") or "") for record in historical_records if record.get("date")),
                default="",
            ) or None
            compact = self._build_compact_validation_snapshot(validation_report)

            lines = [validation_report.get("summary_text", "中期策略统计数据不足，暂无报告。")]
            live_summary = ((validation_report.get("live") or {}).get("summary_text") or "").strip()
            if live_summary:
                lines.append(f"真实建议: {live_summary}")
            if validation_report.get("backtest", {}).get("summary_text"):
                lines.append(f"回测: {validation_report['backtest']['summary_text']}")
            if validation_report.get("walkforward", {}).get("segment_count", 0) > 0:
                lines.append(
                    f"滚动验证: {validation_report['walkforward']['segment_count']}段，"
                    f"平均收益{validation_report['walkforward']['avg_total_return'] * 100:.1f}%"
                )

            snapshot = {
                "mode": mode,
                "summary_text": validation_report.get("summary_text", "中期策略统计数据不足，暂无报告。"),
                "compact": compact,
            }
            if latest_record_date:
                snapshot["as_of_date"] = latest_record_date
            snapshot["text"] = "\n".join(lines)
            return snapshot

        return {"mode": mode, "summary_text": self._run_accuracy_report(mode=mode)}

    def build_validation_result(
        self,
        *,
        mode: str,
        days: int = 90,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        codes: Optional[List[str]] = None,
        preset: Optional[str] = None,
        group_by: Optional[str] = None,
    ):
        return self.validation_service.build_validation_result(
            mode=mode,
            days=days,
            date_from=date_from,
            date_to=date_to,
            codes=codes,
            preset=preset,
            group_by=group_by,
        )

    def build_lab_result(
        self,
        *,
        mode: str,
        preset: str,
        days: int = 90,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        codes: Optional[List[str]] = None,
        group_by: Optional[str] = None,
        scoring_mode: str = "composite",
        overrides: Optional[List[str]] = None,
    ):
        return self.strategy_lab_service.build_lab_result(
            mode=mode,
            preset=preset,
            days=days,
            date_from=date_from,
            date_to=date_to,
            codes=codes,
            group_by=group_by,
            scoring_mode=scoring_mode,
            overrides=overrides,
        )

    def _run_swing_accuracy_report(self) -> str:
        snapshot = self.build_validation_snapshot("swing")
        return snapshot.get("text") or snapshot.get("summary_text", "中期策略统计数据不足，暂无报告。")

    def _build_swing_lab_hint(self) -> Optional[Dict[str, Any]]:
        best_hint: Optional[Dict[str, Any]] = None
        best_key: Optional[tuple[float, int]] = None
        for preset in SWING_LAB_PRESETS:
            result = self.build_lab_result(mode="swing", preset=preset)
            payload = result.to_dict(detail="compact") if hasattr(result, "to_dict") else dict(result or {})
            summary = dict(payload.get("summary") or {})
            diff = dict(payload.get("diff") or {})
            score_delta = round(
                float(summary.get("candidate_score", 0.0) or 0.0)
                - float(summary.get("baseline_score", 0.0) or 0.0),
                4,
            )
            candidate_trade_count = int(summary.get("candidate_trade_count", 0) or 0)
            hint = {
                "preset": payload.get("preset") or preset,
                "winner": payload.get("winner", "baseline"),
                "summary_text": payload.get("summary_text", ""),
                "score_delta": score_delta,
                "trade_count_delta": int(diff.get("trade_count_delta", 0) or 0),
                "candidate_trade_count": candidate_trade_count,
                "total_return_delta": float(diff.get("total_return_delta", 0.0) or 0.0),
                "max_drawdown_delta": float(diff.get("max_drawdown_delta", 0.0) or 0.0),
            }
            ranking_key = (score_delta, -candidate_trade_count)
            if best_key is None or ranking_key > best_key:
                best_key = ranking_key
                best_hint = hint
        return best_hint

    def _run_swing_question(self, question: str) -> str:
        historical_records = self._get_swing_history_records(days=90)
        universe_codes = {
            str(item.get("code", "") or "")
            for item in build_investor_snapshot(
                portfolio=self.config.get("portfolio", []),
                watchlist=self.config.get("watchlist", []),
                portfolio_state=self.config.get("portfolio_state", {}),
                swing_config=((self.config.get("strategy") or {}).get("swing") or {}),
            ).get("universe", [])
            if item.get("code")
        }
        raw_data = self._load_cached_context("swing", universe_codes=universe_codes)
        if not raw_data:
            return "没有找到可用的中期缓存数据。请先运行一次 `python -m src.main --mode swing --dry-run`。"

        analysis_date = raw_data.get("context_date") or datetime.now().strftime('%Y-%m-%d')
        report_input = self._align_swing_context_to_snapshot(
            raw_data,
            build_investor_snapshot(
                portfolio=self.config.get("portfolio", []),
                watchlist=self.config.get("watchlist", []),
                portfolio_state=self.config.get("portfolio_state", {}),
                swing_config=((self.config.get("strategy") or {}).get("swing") or {}),
            ),
        )
        report_input.setdefault("strategy_preferences", self._get_swing_strategy_preferences())
        validation_report = self._compute_swing_validation_report(historical_records)
        if validation_report:
            report_input.setdefault("performance_context", validation_report.get("performance_context", {}))
            report_input.setdefault("validation_report", validation_report)
        report = build_swing_report(report_input, historical_records, analysis_date)
        scorecard = validation_report.get("scorecard") if validation_report else None

        lines = [f"市场结论: {report.get('market_conclusion', '暂无结论')}"]
        position_plan = report.get("position_plan") or {}
        if position_plan:
            lines.append(
                f"仓位计划: 总仓位{position_plan.get('total_exposure', 'N/A')}，"
                f"核心仓{position_plan.get('core_target', 'N/A')}，"
                f"卫星仓{position_plan.get('satellite_target', 'N/A')}，"
                f"现金{position_plan.get('cash_target', 'N/A')}"
            )
        if scorecard:
            lines.append(f"中期跟踪: {scorecard.get('summary_text', '')}")
        if validation_report and validation_report.get("summary_text"):
            lines.append(f"验证摘要: {validation_report['summary_text']}")
        for issue in report_input.get("data_issues", []):
            lines.append(f"数据提示: {issue}")
        lines.append("组合动作:")
        for label in ("增配", "持有", "减配", "回避", "观察"):
            items = report.get("portfolio_actions", {}).get(label, [])
            if not items:
                continue
            names = "、".join(item.get("name", "") for item in items if item.get("name"))
            lines.append(f"- {label}: {names}")
        if report.get("actions"):
            lead = report["actions"][0]
            lines.append(
                f"当前优先项: {lead.get('name', '')} -> {lead.get('conclusion', lead.get('action_label', '观察'))}。"
                f" {lead.get('plan', '')}"
            )
        return "\n".join(lines)

    async def _run_trend_analysis(self, question: str) -> str:
        """Run trend analysis over multiple days of historical data."""
        # Determine how many days to look back
        if '一个月' in question or '本月' in question or '上月' in question:
            days = 30
        elif '两周' in question:
            days = 14
        else:
            days = 7  # default to one week

        # Try close records first (more complete), fallback to midday
        records = self.db.get_records_range(mode='close', days=days)
        if not records:
            records = self.db.get_records_range(mode='midday', days=days)

        if not records:
            return f"没有找到最近{days}天的历史数据，无法进行趋势分析。"

        # Build trend context
        trend_context = []
        for r in reversed(records):  # chronological order
            day_summary = {
                "date": r['date'],
                "ai_result": r.get('ai_result'),
            }
            raw = r.get('raw_data')
            if raw:
                day_summary["market_breadth"] = raw.get('market_breadth')
                day_summary["indices"] = raw.get('indices')
            trend_context.append(day_summary)

        analyst = GeminiClient()
        trend_prompt = self.config['prompts'].get('trend_prompt', '')
        answer = analyst.ask_question(
            context_data={"trend_data": trend_context, "days": days},
            ai_result=None,
            question=question,
            system_prompt=trend_prompt
        )
        return answer
