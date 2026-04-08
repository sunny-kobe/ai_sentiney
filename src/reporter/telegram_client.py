import requests
from typing import Any, Dict

from src.utils.config_loader import ConfigLoader
from src.utils.lab_hint_formatter import build_lab_hint_detail, build_lab_hint_header
from src.utils.logger import logger
from src.utils.report_payload_normalizer import normalize_report_for_display


def _build_validation_hint(data: Dict[str, Any]) -> str:
    compact = data.get("validation_compact") or ((data.get("validation_report") or {}).get("compact")) or {}
    if not compact:
        return ""

    live_window = f"{compact.get('live_primary_window')}日" if compact.get("live_primary_window") else "暂无"
    synthetic_window = f"{compact.get('synthetic_primary_window')}日" if compact.get("synthetic_primary_window") else "暂无"
    offensive_text = "允许" if compact.get("offensive_allowed") else "关闭"
    reason = str(compact.get("offensive_reason", "") or "").strip()
    reason_suffix = f"（{reason}）" if reason else ""
    return (
        f"真实样本: {live_window}{int(compact.get('live_sample_count', 0) or 0)}笔"
        f" | 历史样本: {synthetic_window}{int(compact.get('synthetic_sample_count', 0) or 0)}笔"
        f" | 进攻权限: {offensive_text}{reason_suffix}"
    )


def _build_lab_hint(data: Dict[str, Any]) -> str:
    hint = data.get("lab_hint") or {}
    if not hint:
        return ""
    return build_lab_hint_detail(hint)


class TelegramClient:
    def __init__(self):
        self.config = ConfigLoader().config
        keys = self.config.get("api_keys", {})
        self.bot_token = keys.get("telegram_bot_token", "")
        self.chat_id = keys.get("telegram_chat_id", "")
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram config missing (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")

    def send_midday_report(self, data: Dict[str, Any]):
        message = self._build_midday_text(data)
        self._send_message(message)

    def send_preclose_report(self, data: Dict[str, Any]):
        message = self._build_preclose_text(data)
        self._send_message(message)

    def send_close_report(self, data: Dict[str, Any]):
        message = self._build_close_text(data)
        self._send_message(message)

    def send_morning_report(self, data: Dict[str, Any]):
        message = self._build_morning_text(data)
        self._send_message(message)

    def send_swing_report(self, data: Dict[str, Any]):
        message = self._build_swing_text(data)
        self._send_message(message)

    def _send_message(self, message: str):
        if not self.bot_token or not self.chat_id:
            logger.warning("Skipping Telegram push (missing token/chat_id).")
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message[:3900],  # keep under Telegram message limit
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            resp = response.json()
            if not resp.get("ok"):
                logger.error(f"Telegram API error: {resp}")
            else:
                logger.info("Telegram message sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def _build_midday_text(self, data: Dict[str, Any]) -> str:
        return self._build_intraday_text(data, title="🛡️ Sentinel 午盘分析", summary_label="点评")

    def _build_preclose_text(self, data: Dict[str, Any]) -> str:
        return self._build_intraday_text(data, title="🛡️ Sentinel 收盘前执行", summary_label="执行摘要")

    def _build_intraday_text(self, data: Dict[str, Any], *, title: str, summary_label: str) -> str:
        data = normalize_report_for_display(data)
        lines = [
            title,
            f"质量: {data.get('quality_status', 'normal')}",
            f"时间: {data.get('data_timestamp', 'N/A')}",
            f"来源: {', '.join(data.get('source_labels', []))}" if data.get('source_labels') else "来源: N/A",
            f"情绪: {data.get('market_sentiment', 'N/A')}",
            f"{summary_label}: {data.get('macro_summary', 'N/A')}",
        ]
        if data.get("quality_detail"):
            lines.append(f"原因: {data.get('quality_detail')}")
        for action in data.get("actions", [])[:8]:
            signal = str(action.get('signal') or action.get('action') or action.get('operation', ''))
            signal_upper = signal.upper()
            if signal in ('增配',) or signal_upper in ('OPPORTUNITY', 'ACCUMULATE'):
                prefix = "🟣"
            elif signal in ('减配', '回避') or signal_upper in ('DANGER', 'WARNING'):
                prefix = "🔴"
            else:
                prefix = "-"
            lines.append(
                f"{prefix} {action.get('name', '')}({action.get('code', '')}) "
                f"{action.get('pct_change_str', '')} "
                f"{action.get('operation', action.get('signal', ''))}"
            )
        return "\n".join(lines)

    def _build_close_text(self, data: Dict[str, Any]) -> str:
        data = normalize_report_for_display(data)
        lines = [
            "🛡️ Sentinel 收盘复盘",
            f"质量: {data.get('quality_status', 'normal')}",
            f"时间: {data.get('data_timestamp', 'N/A')}",
            f"来源: {', '.join(data.get('source_labels', []))}" if data.get('source_labels') else "来源: N/A",
            f"总结: {data.get('market_summary', 'N/A')}",
            f"温度: {data.get('market_temperature', 'N/A')}",
        ]
        if data.get("quality_detail"):
            lines.append(f"原因: {data.get('quality_detail')}")
        for action in data.get("actions", [])[:8]:
            lines.append(
                f"- {action.get('name', '')}({action.get('code', '')}) "
                f"明日: {action.get('tomorrow_plan', '')}"
            )
        return "\n".join(lines)

    def _build_morning_text(self, data: Dict[str, Any]) -> str:
        lines = [
            "🛡️ Sentinel 早报",
            f"隔夜综述: {data.get('global_overnight_summary', 'N/A')}",
            f"A股展望: {data.get('a_share_outlook', 'N/A')}",
        ]
        for action in data.get("actions", [])[:8]:
            lines.append(
                f"- {action.get('name', '')}({action.get('code', '')}) "
                f"策略: {action.get('strategy', '')}"
            )
        return "\n".join(lines)

    def _build_swing_text(self, data: Dict[str, Any]) -> str:
        position_plan = data.get("position_plan") or {}
        header_hint = build_lab_hint_header(data.get("lab_hint") or {})
        lines = [
            "🧭 Sentinel 中长期助手",
        ]
        if header_hint:
            lines.append(header_hint)
        lines.extend(
            [
            f"时间: {data.get('data_timestamp', 'N/A')}",
            f"来源: {', '.join(data.get('source_labels', []))}" if data.get('source_labels') else "来源: N/A",
            "今日结论:",
            data.get('market_conclusion', '暂无结论'),
            "验证摘要:",
            data.get("validation_summary", "暂无验证摘要"),
            ]
        )
        validation_hint = _build_validation_hint(data)
        if validation_hint:
            lines.append(validation_hint)
        execution_readiness = str(data.get("execution_readiness", "") or "").strip()
        quality_summary = str(data.get("quality_summary", "") or "").strip()
        if execution_readiness or quality_summary:
            lines.append("执行提示:")
            if execution_readiness:
                lines.append(f"可执行度: {execution_readiness}")
            if quality_summary:
                lines.append(quality_summary)
        lab_hint = _build_lab_hint(data)
        if lab_hint:
            lines.append(lab_hint)
        lines.extend(
            [
                "账户动作:",
                f"当前总仓位: {position_plan.get('current_total_exposure', 'N/A')}",
                f"建议总仓位: {position_plan.get('total_exposure', 'N/A')}",
                f"现金目标: {position_plan.get('cash_target', 'N/A')}",
                f"优先动作: {'；'.join(position_plan.get('execution_order', []) or []) or '暂无'}",
            ]
        )
        validation_budgets = position_plan.get("validation_budgets") or []
        if validation_budgets:
            lines.append("方向预算:")
            for budget in validation_budgets:
                lines.append(f"- {budget.get('label', '')}: {budget.get('status', '正常')} | 预算:{budget.get('budget_range', 'N/A')}")
                lines.append(f"  原因: {budget.get('reason', '')}")
        lines.append("持仓处理:")
        for action in data.get("actions", [])[:8]:
            lines.append(
                f"- {action.get('name', '')} | {action.get('conclusion', action.get('action_label', '观察'))}"
                f" | 当前:{action.get('current_weight', '0%')}"
                f" | 目标:{action.get('target_weight', 'N/A')}"
            )
            lines.append(f"  原因: {action.get('reason', '')}")
            if action.get("validation_note"):
                lines.append(f"  验证: {action.get('validation_note', '')}")
            lines.append(f"  计划: {action.get('plan', '')}")
            lines.append(f"  风险线: {action.get('risk_line', '')}")
        lines.append("观察池机会:")
        watchlist_candidates = data.get("watchlist_candidates", []) or []
        if watchlist_candidates:
            for candidate in watchlist_candidates:
                lines.append(f"- {candidate.get('name', '')}({candidate.get('code', '')}) {candidate.get('action_label', '继续观察')}")
                lines.append(f"  原因: {candidate.get('reason', '')}")
                lines.append(f"  计划: {candidate.get('plan', '')}")
        else:
            lines.append("- 当前没有值得试仓的新方向")
        lines.append("风险清单:")
        risk_lines = [f"- {issue}" for issue in (data.get("data_issues") or [])]
        for action in data.get("actions", []):
            if action.get("action_label") in {"减配", "回避"} and action.get("risk_line"):
                risk_lines.append(f"- {action.get('name', '')}: {action.get('risk_line', '')}")
        for candidate in watchlist_candidates:
            if candidate.get("risk_line"):
                risk_lines.append(f"- {candidate.get('name', '')}: {candidate.get('risk_line', '')}")
        lines.extend(risk_lines[:3] or ["- 暂无额外风险提示"])
        return "\n".join(lines)
