import requests
from typing import Any, Dict

from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger


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
        lines = [
            "🛡️ Sentinel 午盘分析",
            f"质量: {data.get('quality_status', 'normal')}",
            f"时间: {data.get('data_timestamp', 'N/A')}",
            f"来源: {', '.join(data.get('source_labels', []))}" if data.get('source_labels') else "来源: N/A",
            f"情绪: {data.get('market_sentiment', 'N/A')}",
            f"点评: {data.get('macro_summary', 'N/A')}",
        ]
        for action in data.get("actions", [])[:8]:
            signal = action.get('signal', action.get('action', '')).upper()
            if signal in ('OPPORTUNITY', 'ACCUMULATE'):
                prefix = "🟣"
            elif signal in ('DANGER', 'WARNING'):
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
        lines = [
            "🛡️ Sentinel 收盘复盘",
            f"质量: {data.get('quality_status', 'normal')}",
            f"时间: {data.get('data_timestamp', 'N/A')}",
            f"来源: {', '.join(data.get('source_labels', []))}" if data.get('source_labels') else "来源: N/A",
            f"总结: {data.get('market_summary', 'N/A')}",
            f"温度: {data.get('market_temperature', 'N/A')}",
        ]
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
        lines = [
            "🛡️ Sentinel 中期策略",
            f"时间: {data.get('data_timestamp', 'N/A')}",
            f"来源: {', '.join(data.get('source_labels', []))}" if data.get('source_labels') else "来源: N/A",
            f"市场结论: {data.get('market_conclusion', '暂无结论')}",
            "仓位计划:",
            f"总仓位: {position_plan.get('total_exposure', 'N/A')}",
            f"核心仓: {position_plan.get('core_target', 'N/A')}",
            f"卫星仓: {position_plan.get('satellite_target', 'N/A')}",
            f"现金: {position_plan.get('cash_target', 'N/A')}",
            "组合动作:",
        ]
        for label in ("增配", "持有", "减配", "回避", "观察"):
            items = data.get("portfolio_actions", {}).get(label, [])
            if not items:
                continue
            names = "、".join(item.get("name", "") for item in items if item.get("name"))
            lines.append(f"{label}: {names}")

        lines.append("持仓清单:")
        for action in data.get("actions", [])[:8]:
            lines.append(
                f"- {action.get('name', '')} | {action.get('conclusion', action.get('action_label', '观察'))}"
                f" | {action.get('position_bucket', 'N/A')} | {action.get('target_weight', 'N/A')}"
            )
            lines.append(f"  计划: {action.get('plan', '')}")
            lines.append(f"  风险线: {action.get('risk_line', '')}")
        return "\n".join(lines)
