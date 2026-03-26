from __future__ import annotations

from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from src.backtest.engine import run_deterministic_backtest
from src.backtest.walkforward import run_walkforward_validation
from src.processor.swing_tracker import build_swing_scorecard
from src.service.performance_gate import build_default_performance_context, gate_offensive_setup
from src.service.portfolio_advisor import build_investor_snapshot
from src.service.swing_strategy import build_swing_report, infer_cluster, resolve_benchmark_code
from src.validation.diagnostics import DiagnosisRequest, DiagnosisSummary, DiagnosticGroup
from src.validation.history import slice_records
from src.validation.models import ValidationRequest, ValidationResult


class ValidationService:
    def __init__(self, db: Any, config: Optional[Dict[str, Any]] = None):
        self.db = db
        self.config = config or {}

    def _get_swing_strategy_preferences(self) -> Dict[str, Any]:
        swing_config = ((self.config.get("strategy") or {}).get("swing") or {})
        return build_investor_snapshot(
            portfolio=self.config.get("portfolio", []),
            watchlist=self.config.get("watchlist", []),
            portfolio_state=self.config.get("portfolio_state", {}),
            swing_config=swing_config,
        ).get("strategy_preferences", {})

    def _investor_universe_codes(self) -> List[str]:
        swing_config = ((self.config.get("strategy") or {}).get("swing") or {})
        snapshot = build_investor_snapshot(
            portfolio=self.config.get("portfolio", []),
            watchlist=self.config.get("watchlist", []),
            portfolio_state=self.config.get("portfolio_state", {}),
            swing_config=swing_config,
        )
        return [
            str(item.get("code", "") or "")
            for item in (snapshot.get("universe") or [])
            if item.get("code")
        ]

    def _apply_request_preset(self, request: ValidationRequest) -> ValidationRequest:
        if request.codes:
            return request
        if request.preset in {"aggressive_midterm", "portfolio_focus", "defensive_retreat_check"}:
            request.codes = self._investor_universe_codes()
        return request

    def _get_swing_history_records(
        self,
        *,
        days: int = 90,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        codes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        records = self.db.get_records_range(mode="close", days=days)
        if not records:
            records = self.db.get_records_range(mode="midday", days=days)
        return slice_records(records, days=days, date_from=date_from, date_to=date_to, codes=codes)

    def _get_swing_report_records(
        self,
        *,
        days: int = 90,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        codes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        records = self.db.get_records_range(mode="swing", days=days)
        return slice_records(records, days=days, date_from=date_from, date_to=date_to, codes=codes)

    def _build_swing_benchmark_map(self, records: List[Dict[str, Any]]) -> Dict[str, str]:
        benchmark_map: Dict[str, str] = {}
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

    def _build_synthetic_swing_records(self, historical_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not historical_records:
            return []

        sorted_records = sorted(historical_records, key=lambda item: item.get("date", ""))
        synthetic_records: List[Dict[str, Any]] = []

        for index, record in enumerate(sorted_records):
            raw_data = record.get("raw_data") or {}
            if not raw_data.get("stocks"):
                continue
            report_input = dict(raw_data)
            report_input.setdefault("strategy_preferences", self._get_swing_strategy_preferences())

            context_window = sorted_records[max(0, index - 40) : index + 1]
            swing_report = build_swing_report(
                report_input,
                context_window,
                analysis_date=record.get("date") or datetime.now().strftime("%Y-%m-%d"),
            )
            stock_map = {
                str(stock.get("code", "") or ""): stock
                for stock in (raw_data.get("stocks") or [])
                if stock.get("code")
            }
            market_regime = str(swing_report.get("market_regime", "unknown") or "unknown")
            actions = [
                {
                    "code": action.get("code"),
                    "name": action.get("name"),
                    "action_label": action.get("action_label"),
                    "confidence": action.get("confidence"),
                    "signal": action.get("signal"),
                    "score": action.get("score"),
                    "target_weight": action.get("target_weight"),
                    "target_weight_range": action.get("target_weight_range"),
                    "shares": int(action.get("shares", 0) or 0),
                    "current_shares": int(action.get("current_shares", action.get("shares", 0)) or 0),
                    "relative_return_20": action.get("relative_return_20"),
                    "relative_return_40": action.get("relative_return_40"),
                    "drawdown_20": action.get("drawdown_20"),
                    "position_bucket": action.get("position_bucket"),
                    "cluster": action.get("cluster")
                    or infer_cluster(stock_map.get(str(action.get("code", "") or ""), action)),
                    "market_regime": market_regime,
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
                    "ai_result": {"actions": actions, "market_regime": market_regime},
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
        primary_window = next(
            (window for window in search_windows if stats_root.get(window, {}).get("count", 0) > 0),
            None,
        )
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
                gate = {
                    "allowed": True,
                    "reason": f"{gate.get('reason', '样本通过')}，正式回测未见明显恶化",
                }

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

            if len(evidence_parts) > 1:
                return " 参考：".join([evidence_parts[0], "；".join(evidence_parts[1:]) + "。"])
            return evidence_parts[0] if evidence_parts else "真实建议跟踪样本还不够，先继续积累。"

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

    def _build_compact_validation_snapshot(self, validation_report: Dict[str, Any]) -> Dict[str, Any]:
        live_window, live_stats = self._primary_window_stats(
            (validation_report.get("live") or {}).get("scorecard"),
            preferred_windows=(20, 10, 40),
        )
        synthetic_window, synthetic_stats = self._primary_window_stats(
            validation_report.get("scorecard"),
            preferred_windows=(20, 10, 40),
        )
        offensive_gate = (
            ((validation_report.get("performance_context") or {}).get("offensive") or {}).get("pullback_resume")
            or {}
        )
        return {
            "verdict": self._extract_validation_verdict(validation_report.get("summary_text", "")),
            "live_sample_count": int(live_stats.get("count", 0) or 0),
            "live_primary_window": live_window,
            "synthetic_sample_count": int(synthetic_stats.get("count", 0) or 0),
            "synthetic_primary_window": synthetic_window,
            "backtest_trade_count": int((validation_report.get("backtest") or {}).get("trade_count", 0) or 0),
            "walkforward_segment_count": int((validation_report.get("walkforward") or {}).get("segment_count", 0) or 0),
            "offensive_allowed": bool(offensive_gate.get("allowed")),
            "offensive_reason": str(offensive_gate.get("reason", "样本不足")),
        }

    def _build_validation_report_from_synthetic_records(
        self,
        *,
        historical_records: List[Dict[str, Any]],
        synthetic_records: List[Dict[str, Any]],
        group_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not synthetic_records:
            empty_report = {
                "live": None,
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
                "performance_context": self._build_validation_performance_context(None, None, None),
                "summary_text": self._build_validation_summary_text(None, None, None, None),
            }
            empty_report["compact"] = self._build_compact_validation_snapshot(empty_report)
            empty_report["diagnostics"] = self._build_grouped_diagnostics(
                scorecard=None,
                synthetic_records=[],
                diagnosis_request=DiagnosisRequest(group_by=group_by),
            )
            return empty_report

        sorted_records = sorted(historical_records, key=lambda item: item.get("date", ""))
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
                f"回测收益{backtest_report['total_return'] * 100:.1f}%，"
                f"最大回撤{backtest_report['max_drawdown'] * 100:.1f}%，"
                f"交易{backtest_report['trade_count']}笔"
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
        report = {
            "live": None,
            "scorecard": scorecard,
            "backtest": backtest_report,
            "walkforward": walkforward_report,
            "performance_context": self._build_validation_performance_context(scorecard, backtest_report, None),
            "summary_text": self._build_validation_summary_text(None, scorecard, backtest_report, walkforward_report),
        }
        report["compact"] = self._build_compact_validation_snapshot(report)
        report["diagnostics"] = self._build_grouped_diagnostics(
            scorecard=scorecard,
            synthetic_records=synthetic_records,
            diagnosis_request=DiagnosisRequest(group_by=group_by),
        )
        return report

    def _score_validation_report(self, report: Dict[str, Any], scoring_mode: str = "composite") -> float:
        if scoring_mode != "composite":
            scoring_mode = "composite"

        total_return = float(((report.get("backtest") or {}).get("total_return", 0.0) or 0.0))
        max_drawdown = float(((report.get("backtest") or {}).get("max_drawdown", 0.0) or 0.0))
        trade_count = int(((report.get("backtest") or {}).get("trade_count", 0) or 0))
        primary_window, stats = self._primary_window_stats(report.get("scorecard"), preferred_windows=(20, 10, 40))
        avg_relative = float(stats.get("avg_relative_return", 0.0) or 0.0)
        sample_count = int(stats.get("count", 0) or 0) if primary_window is not None else 0
        stability = min(sample_count / 20.0, 1.0)

        score = (
            (total_return * 35.0)
            + (avg_relative * 30.0)
            + (max_drawdown * 25.0)
            + (stability * 10.0)
            - (max(trade_count - 12, 0) * 0.002)
        )
        return round(score, 4)

    def _build_comparison_diff(self, baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        baseline_backtest = baseline.get("backtest") or {}
        candidate_backtest = candidate.get("backtest") or {}
        baseline_window, baseline_stats = self._primary_window_stats(baseline.get("scorecard"), preferred_windows=(20, 10, 40))
        candidate_window, candidate_stats = self._primary_window_stats(candidate.get("scorecard"), preferred_windows=(20, 10, 40))

        return {
            "baseline_primary_window": baseline_window,
            "candidate_primary_window": candidate_window,
            "total_return_delta": round(
                float(candidate_backtest.get("total_return", 0.0) or 0.0)
                - float(baseline_backtest.get("total_return", 0.0) or 0.0),
                4,
            ),
            "max_drawdown_delta": round(
                float(candidate_backtest.get("max_drawdown", 0.0) or 0.0)
                - float(baseline_backtest.get("max_drawdown", 0.0) or 0.0),
                4,
            ),
            "trade_count_delta": int(candidate_backtest.get("trade_count", 0) or 0)
            - int(baseline_backtest.get("trade_count", 0) or 0),
            "avg_relative_return_delta": round(
                float(candidate_stats.get("avg_relative_return", 0.0) or 0.0)
                - float(baseline_stats.get("avg_relative_return", 0.0) or 0.0),
                4,
            ),
            "sample_count_delta": int(candidate_stats.get("count", 0) or 0)
            - int(baseline_stats.get("count", 0) or 0),
        }

    def _build_diagnostic_rows(
        self,
        *,
        evaluations: List[Dict[str, Any]],
        metadata_by_observation: Dict[Tuple[str, str], Dict[str, Any]],
        window: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for evaluation in evaluations or []:
            windows = evaluation.get("windows") or {}
            code = str(evaluation.get("code", "") or "")
            fallback_meta = {
                "cluster": infer_cluster({"code": code, "name": evaluation.get("name", "")}),
                "market_regime": "unknown",
            }
            for raw_window, metrics in windows.items():
                if not isinstance(metrics, dict):
                    continue
                current_window = int(raw_window)
                if window is not None and current_window != int(window):
                    continue
                entry_date = str(metrics.get("entry_date", "") or "")
                meta = metadata_by_observation.get((code, entry_date)) or fallback_meta
                rows.append(
                    {
                        "code": code,
                        "name": str(evaluation.get("name", "") or ""),
                        "action_label": str(evaluation.get("action_label", "") or ""),
                        "confidence": str(evaluation.get("confidence", "未知") or "未知"),
                        "cluster": str(meta.get("cluster", fallback_meta["cluster"]) or fallback_meta["cluster"]),
                        "market_regime": str(meta.get("market_regime", "unknown") or "unknown"),
                        "window": current_window,
                        "entry_date": entry_date,
                        "absolute_return": float(metrics.get("absolute_return", 0.0) or 0.0),
                        "relative_return": float(metrics.get("relative_return", 0.0) or 0.0),
                        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
                    }
                )
        return rows

    def _aggregate_diagnostics(self, rows: List[Dict[str, Any]], group_by: str) -> Dict[str, Any]:
        group_field = {
            "action": "action_label",
            "cluster": "cluster",
            "regime": "market_regime",
            "confidence": "confidence",
        }.get(str(group_by or "").strip().lower(), group_by)
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows or []:
            key = str(row.get(group_field, "unknown") or "unknown")
            grouped[key].append(row)

        groups: List[Dict[str, Any]] = []
        for key, items in grouped.items():
            sample_count = len(items)
            groups.append(
                {
                    "key": key,
                    "sample_count": sample_count,
                    "avg_absolute_return": round(
                        sum(float(item.get("absolute_return", 0.0) or 0.0) for item in items) / sample_count, 4
                    ),
                    "avg_relative_return": round(
                        sum(float(item.get("relative_return", 0.0) or 0.0) for item in items) / sample_count, 4
                    ),
                    "avg_max_drawdown": round(
                        sum(float(item.get("max_drawdown", 0.0) or 0.0) for item in items) / sample_count, 4
                    ),
                }
            )

        groups.sort(
            key=lambda item: (
                float(item.get("avg_relative_return", 0.0)),
                float(item.get("avg_absolute_return", 0.0)),
                float(item.get("avg_max_drawdown", 0.0)),
                str(item.get("key", "")),
            )
        )
        return {"group_by": group_by, "groups": groups}

    def _build_diagnostic_metadata(
        self,
        synthetic_records: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        metadata: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for record in synthetic_records or []:
            record_date = str(record.get("date", "") or "")
            raw_stock_map = {
                str(stock.get("code", "") or ""): stock
                for stock in (((record.get("raw_data") or {}).get("stocks")) or [])
                if stock.get("code")
            }
            ai_result = record.get("ai_result") or {}
            market_regime = str(ai_result.get("market_regime", "unknown") or "unknown")
            for action in (ai_result.get("actions") or []):
                code = str(action.get("code", "") or "")
                if not code:
                    continue
                stock = raw_stock_map.get(code) or {"code": code, "name": action.get("name", "")}
                metadata[(code, record_date)] = {
                    "cluster": str(action.get("cluster") or infer_cluster(stock)),
                    "market_regime": str(action.get("market_regime", market_regime) or market_regime),
                }
        return metadata

    def _build_grouped_diagnostics(
        self,
        *,
        scorecard: Optional[Dict[str, Any]],
        synthetic_records: List[Dict[str, Any]],
        diagnosis_request: DiagnosisRequest,
    ) -> Optional[Dict[str, Any]]:
        if not diagnosis_request.group_by:
            return None

        primary_window = diagnosis_request.primary_window
        if primary_window is None:
            primary_window, _ = self._primary_window_stats(scorecard, preferred_windows=(20, 10, 40))
        if primary_window is None:
            return DiagnosisSummary(
                group_by=diagnosis_request.group_by,
                primary_window=None,
                summary_text="分组诊断样本不足，暂时无法定位主要拖累来源。",
            ).to_dict()

        rows = self._build_diagnostic_rows(
            evaluations=list((scorecard or {}).get("evaluations") or []),
            metadata_by_observation=self._build_diagnostic_metadata(synthetic_records),
            window=primary_window,
        )
        aggregate = self._aggregate_diagnostics(rows, group_by=diagnosis_request.group_by)
        groups = [DiagnosticGroup(**item) for item in (aggregate.get("groups") or [])]
        summary = DiagnosisSummary(
            group_by=diagnosis_request.group_by,
            primary_window=primary_window,
            summary_text=self._build_diagnosis_summary(
                group_by=diagnosis_request.group_by,
                primary_window=primary_window,
                groups=[group.to_dict() for group in groups],
            ),
            groups=groups,
        ).to_dict()
        if groups:
            summary["top_drag"] = groups[0].to_dict()
            summary["top_strength"] = groups[-1].to_dict()
        return summary

    def _build_diagnosis_summary(
        self,
        *,
        group_by: str,
        primary_window: int,
        groups: List[Dict[str, Any]],
    ) -> str:
        if not groups:
            return f"{primary_window}日分组诊断样本不足。"

        sorted_groups = sorted(
            groups,
            key=lambda item: (
                float(item.get("avg_relative_return", 0.0)),
                float(item.get("avg_absolute_return", 0.0)),
                float(item.get("avg_max_drawdown", 0.0)),
                str(item.get("key", "")),
            ),
        )
        top_drag = sorted_groups[0]
        strongest = sorted_groups[-1]
        drag_key = str(top_drag.get("key", "") or "")
        strong_key = str(strongest.get("key", "") or "")
        offensive_keys = {"增配", "持有", "进攻"}
        defensive_keys = {"减配", "回避", "防守", "撤退"}
        if drag_key in offensive_keys:
            bias_text = "这更像进攻侧失误，说明加仓或持有偏激进。"
        elif drag_key in defensive_keys:
            bias_text = "这更像防守侧失误，说明减仓或回避偏慢。"
        elif strong_key in defensive_keys:
            bias_text = "相对更稳的是防守侧，说明问题更像退出不够快。"
        elif strong_key in offensive_keys:
            bias_text = "相对更稳的是进攻侧，说明问题更像过早收缩。"
        elif float(top_drag.get("avg_max_drawdown", 0.0) or 0.0) <= -0.08:
            bias_text = "主要问题偏向进攻侧承受了过多波动。"
        else:
            bias_text = "暂时还看不出明显的进攻或防守偏差。"
        return (
            f"{primary_window}日按{group_by}分组看，主要拖累来自{top_drag.get('key')}组"
            f"（样本{int(top_drag.get('sample_count', 0) or 0)}，"
            f"平均收益{float(top_drag.get('avg_absolute_return', 0.0) or 0.0) * 100:.1f}%）；"
            f"相对最强的是{strongest.get('key')}组"
            f"（平均收益{float(strongest.get('avg_absolute_return', 0.0) or 0.0) * 100:.1f}%）。"
            f"{bias_text}"
        )

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

        ordered: List[Dict[str, Any]] = []
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
        if not swing_records or not close_records:
            return None

        live_records = self._build_live_validation_records(swing_records, close_records)
        if not live_records:
            return None

        scorecard = build_swing_scorecard(
            live_records,
            benchmark_map=benchmark_map or self._build_swing_benchmark_map(close_records),
            windows=windows,
        )
        if not any(
            ((scorecard.get("stats") or {}).get("overall") or {}).get(int(window), {}).get("count", 0) > 0
            for window in windows
        ):
            return None

        return {
            "scorecard": scorecard,
            "summary_text": self._build_live_validation_summary_text(scorecard),
        }

    def _compute_swing_validation_report(
        self,
        historical_records: List[Dict[str, Any]],
        request: Optional[ValidationRequest] = None,
    ) -> Optional[Dict[str, Any]]:
        if not historical_records:
            return None

        sorted_records = sorted(historical_records, key=lambda item: item.get("date", ""))
        request = request or ValidationRequest(mode="swing", days=max(len(sorted_records), 90))
        swing_records = self._get_swing_report_records(
            days=max(request.days or len(sorted_records) or 90, len(sorted_records), 90),
            date_from=request.date_from,
            date_to=request.date_to,
            codes=request.codes,
        )
        live_report = self._compute_live_swing_validation_report(
            swing_records,
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
                "performance_context": self._build_validation_performance_context(
                    None,
                    None,
                    (live_report or {}).get("scorecard"),
                ),
                "summary_text": self._build_validation_summary_text(live_report, None, None, None),
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
        performance_context = self._build_validation_performance_context(
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
            "summary_text": self._build_validation_summary_text(
                live_report,
                scorecard,
                backtest_report,
                walkforward_report,
            ),
        }

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
    ) -> ValidationResult:
        request = ValidationRequest(
            mode=mode,
            days=days,
            date_from=date_from,
            date_to=date_to,
            codes=codes or [],
            preset=preset,
        )
        diagnosis_request = DiagnosisRequest(group_by=group_by)
        request = self._apply_request_preset(request)
        if request.mode != "swing":
            return ValidationResult(
                mode=request.mode,
                investor_summary="仅 `swing` 模式支持历史验证。",
                compact={"verdict": "unsupported"},
            )

        historical_records = self._get_swing_history_records(
            days=request.days or 90,
            date_from=request.date_from,
            date_to=request.date_to,
            codes=request.codes,
        )
        validation_report = self._compute_swing_validation_report(historical_records, request=request)
        if not validation_report:
            return ValidationResult(
                mode=request.mode,
                investor_summary="中期策略统计数据不足，暂无报告。",
                compact={"verdict": "insufficient_data"},
            )

        latest_record_date = max(
            (str(record.get("date", "") or "") for record in historical_records if record.get("date")),
            default="",
        ) or None
        compact = self._build_compact_validation_snapshot(validation_report)
        diagnostics = self._build_grouped_diagnostics(
            scorecard=validation_report.get("scorecard"),
            synthetic_records=self._build_synthetic_swing_records(sorted(historical_records, key=lambda item: item.get("date", ""))),
            diagnosis_request=diagnosis_request,
        )

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
        if diagnostics:
            lines.append(f"诊断: {diagnostics.get('summary_text', '暂无分组诊断')}")
            for group in diagnostics.get("groups", [])[:5]:
                lines.append(
                    "  "
                    f"{group.get('key')}: 样本{int(group.get('sample_count', 0) or 0)} | "
                    f"平均收益{float(group.get('avg_absolute_return', 0.0) or 0.0) * 100:.1f}% | "
                    f"平均超额{float(group.get('avg_relative_return', 0.0) or 0.0) * 100:.1f}% | "
                    f"平均回撤{float(group.get('avg_max_drawdown', 0.0) or 0.0) * 100:.1f}%"
                )

        return ValidationResult(
            mode=request.mode,
            as_of_date=latest_record_date,
            investor_summary=validation_report.get("summary_text", "中期策略统计数据不足，暂无报告。"),
            compact=compact,
            text="\n".join(lines),
            diagnostics=diagnostics,
            details={
                "request": request.to_dict(),
                "diagnosis_request": diagnosis_request.to_dict(),
                **({"diagnostics": diagnostics} if diagnostics else {}),
                **validation_report,
            },
        )

    def build_validation_snapshot(self, **kwargs: Any) -> Dict[str, Any]:
        return self.build_validation_result(**kwargs).to_dict()
