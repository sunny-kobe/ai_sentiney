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
from src.utils.trading_calendar import should_run_market_report
from src.service.report_quality import evaluate_input_quality, evaluate_output_quality
from src.service.structured_report import build_structured_report

class AnalysisService:
    def __init__(self):
        self.config = ConfigLoader().config
        self.db = SentinelDB()
        self.data_path = Path("data/latest_context.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

    async def collect_and_process_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """Collects raw data and processes it into AI-ready context."""
        # 1. Collect Data (Async)
        collector = DataCollector()
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
            "stocks": processed_stocks
        }

    async def collect_and_process_morning_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """Collects and processes morning pre-market data."""
        collector = DataCollector()
        raw_data = await collector.collect_morning_data(portfolio)

        processor = DataProcessor()
        processed_data = processor.process_morning_data(raw_data, portfolio)
        processed_data["context_date"] = datetime.now().strftime('%Y-%m-%d')

        logger.info(f"Morning data collected. Global indices: {len(processed_data.get('global_indices', []))}, "
                     f"Commodities: {len(processed_data.get('commodities', []))}, "
                     f"Stocks: {len(processed_data.get('stocks', []))}")
        return processed_data

    def post_process_result(self, analysis_result: Dict, ai_input: Dict, mode: str = 'midday') -> Dict:
        """Injects real-time data back into analysis result for display."""
        if mode == 'morning':
            return self._post_process_morning(analysis_result, ai_input)

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
                action['current_price'] = current_price

                sign = "+" if pct > 0 else ""
                color = "🔴" if pct > 0 else "🟢"
                action['pct_change_str'] = f"`{color} {sign}{pct}%`"

                # 🔧 FIX: 传递 T+1 相关字段到 actions
                if 'tradeable' in stock_obj:
                    action['tradeable'] = stock_obj['tradeable']
                if 'signal_note' in stock_obj:
                    action['signal_note'] = stock_obj['signal_note']
                # 传递多维指标字段
                if 'signal' in stock_obj:
                    action['signal'] = stock_obj['signal']
                if 'confidence' in stock_obj:
                    action['confidence'] = stock_obj['confidence']
                if 'tech_summary' in stock_obj:
                    action['tech_summary'] = stock_obj['tech_summary']
                structured_stock = structured_map.get(code)
                if structured_stock:
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
        ai_input = None

        # --- Step 1: Data Preparation ---
        if replay:
            if self.data_path.exists():
                logger.info("Replay Mode: Loading data from local JSON file...")
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    ai_input = json.load(f)
            else:
                latest_record = self.db.get_latest_record(mode=mode)
                if latest_record:
                    logger.info("Replay Mode: Loading data from SQLite DB...")
                    ai_input = latest_record
                else:
                     logger.error("No historical data found for replay.")
                     return {"error": "No replay data"}
        else:
            if not portfolio:
                logger.warning("Portfolio is empty.")
                return {"error": "Portfolio is empty"}
            
            try:
                if mode == 'morning':
                    ai_input = await self.collect_and_process_morning_data(portfolio)
                else:
                    ai_input = await self.collect_and_process_data(portfolio)
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
        if mode in ('midday', 'close'):
            quality_input = evaluate_input_quality(ai_input, mode=mode)
            ai_input["quality_input"] = quality_input
            ai_input["structured_report"] = build_structured_report(
                ai_input,
                mode=mode,
                quality_status=quality_input["status"],
            )
            if quality_input["status"] == "blocked" and not dry_run:
                return self._build_blocked_report(mode, ai_input["structured_report"], quality_input["issues"])

        # --- Step 2: AI Analysis ---
        analysis_result = {}
        
        try:
            if dry_run:
                logger.info("Dry Run Mode: Mocking AI response.")
                for s in ai_input.get('stocks', []):
                    logger.info(f"[DRY-RUN TAGS] {s['name']} Tech: {s.get('tech_summary')}")
                analysis_result = {
                    "market_sentiment": "DryRun", 
                    "summary": "This is a dry run.", 
                    "actions": [],
                    "quality_status": quality_input["status"],
                    "quality_issues": quality_input["issues"],
                    "structured_report": ai_input.get("structured_report"),
                    "data_timestamp": ai_input.get("structured_report", {}).get("data_timestamp"),
                    "source_labels": ai_input.get("structured_report", {}).get("source_labels", []),
                }
            elif mode in ("midday", "close") and quality_input["status"] == "degraded":
                analysis_result = self._build_degraded_report(mode, ai_input["structured_report"], quality_input["issues"])
            else:
                analyst = GeminiClient()
                if mode == 'midday':
                    last_close = self.db.get_last_close_analysis()
                    ai_input['yesterday_context'] = last_close
                    analysis_result = analyst.analyze(ai_input)
                elif mode == 'close':
                    system_prompt = self.config['prompts'].get('close_review')
                    if system_prompt:
                        analysis_result = analyst.analyze_with_prompt(ai_input, system_prompt)
                    else:
                        analysis_result = analyst.analyze(ai_input)
                elif mode == 'morning':
                    system_prompt = self.config['prompts'].get('morning_brief')
                    if system_prompt:
                        analysis_result = analyst.analyze_morning(ai_input, system_prompt)
                    else:
                        logger.error("Morning brief prompt not found in config!")
                        return {"error": "Missing morning_brief prompt"}

            # Unified Post-Processing
            analysis_result = self.post_process_result(analysis_result, ai_input, mode=mode)
            if mode in ("midday", "close") and not dry_run:
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
                    )
                    analysis_result = self.post_process_result(analysis_result, ai_input, mode=mode)
                if "quality_status" not in analysis_result:
                    analysis_result["quality_status"] = "normal" if output_quality["status"] == "normal" else "degraded"
                analysis_result["quality_issues"] = output_quality["issues"] if output_quality["issues"] else quality_input["issues"]
            elif mode in ("midday", "close"):
                analysis_result.setdefault("quality_status", quality_input["status"])
                analysis_result.setdefault("quality_issues", quality_input["issues"])
            
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
                        elif mode == 'close':
                            reporter.send_close_report(analysis_result)
                        elif mode == 'morning':
                            reporter.send_morning_report(analysis_result)
                    else:
                        reporter = FeishuClient()
                        if mode == 'midday':
                            reporter.send_card(analysis_result)
                        elif mode == 'close':
                            reporter.send_close_card(analysis_result)
                        elif mode == 'morning':
                            reporter.send_morning_card(analysis_result)
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

    def _build_blocked_report(self, mode: str, structured_report: Dict[str, Any], issues: List[str]) -> Dict[str, Any]:
        return {
            "error": "Insufficient input quality for report generation",
            "mode": mode,
            "quality_status": "blocked",
            "quality_issues": issues,
            "structured_report": structured_report,
            "data_timestamp": structured_report.get("data_timestamp"),
            "source_labels": structured_report.get("source_labels", []),
        }

    def _build_degraded_report(self, mode: str, structured_report: Dict[str, Any], issues: List[str]) -> Dict[str, Any]:
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
            evidence_text = " / ".join(stock.get("news_evidence", [])[:2]) or stock.get("tech_evidence", "")
            if mode == "close":
                base_action["today_review"] = "结构化快报"
                base_action["tomorrow_plan"] = stock.get("operation")
                base_action["reason"] = evidence_text
            else:
                base_action["reason"] = evidence_text or "证据不足，采用结构化技术快报"
            actions.append(base_action)

        top = {
            "quality_status": "degraded",
            "quality_issues": issues,
            "structured_report": structured_report,
            "data_timestamp": structured_report.get("data_timestamp"),
            "source_labels": structured_report.get("source_labels", []),
            "actions": actions,
        }
        if mode == "close":
            top.update({
                "market_summary": "证据不足，降级输出",
                "market_temperature": "结构化快报",
            })
        else:
            top.update({
                "market_sentiment": "结构化快报",
                "volume_analysis": "N/A",
                "macro_summary": "证据不足，降级输出",
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
        if self._detect_accuracy_query(question):
            return self._run_accuracy_report()

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

    def _run_accuracy_report(self) -> str:
        """Generate a formatted accuracy report."""
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
