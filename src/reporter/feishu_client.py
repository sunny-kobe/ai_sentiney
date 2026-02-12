import requests
import json
import time
from typing import Dict, Any, List
from src.utils.logger import logger
from src.utils.config_loader import ConfigLoader

class FeishuClient:
    def __init__(self):
        self.config = ConfigLoader().config
        self.webhook_url = self.config['api_keys'].get('feishu_webhook')
        if not self.webhook_url:
            logger.error("Feishu Webhook URL is missing!")

    def send_card(self, analysis_result: Dict[str, Any]):
        """
        Sends an interactive card message to Feishu.
        """
        if not self.webhook_url:
            logger.warning("Skipping Feishu push (No URL)")
            return

        try:
            card_content = self._construct_card(analysis_result)
            payload = {
                "msg_type": "interactive",
                "card": card_content
            }
            
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
            
            # Check Feishu response logic
            resp_json = response.json()
            if resp_json.get("code") != 0:
                logger.error(f"Feishu Error: {resp_json}")
            else:
                logger.info("Feishu notification sent successfully.")
                
        except Exception as e:
            logger.error(f"Failed to send Feishu message: {e}")

    def _construct_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Constructs the Feishu Interactive Card JSON (Optimized V2).
        """
        market_sentiment = data.get("market_sentiment", "N/A")
        macro_summary = data.get("macro_summary", "暂无大盘点评")
        risk_alert = data.get("risk_alert", "")
        actions = data.get("actions", [])
        
        # Pass indices data manually if we can, but usually 'data' is just the AI result.
        # Wait, the AI result doesn't contain the raw indices data unless we put it there or pass it separately.
        # Ideally, we should merge the raw indices into the data passed here.
        # For now, let's assume the AI *could* mention it, OR we modify main.py to injection 'indices' into the result dict.
        # Let's rely on main.py to merge 'indices' into analysis_result before calling send_card.
        indices_info = data.get("indices_info", "暂无指数数据") 

        # Color Logic
        header_color = "blue"
        if "SELL" in str(actions) or "冰点" in market_sentiment:
            header_color = "red"
        elif "亢奋" in market_sentiment:
            header_color = "orange"
        elif "震荡" in market_sentiment:
            header_color = "grey"

        # 1. Header Section
        elements: List[Dict[str, Any]] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📈 市场情绪**: {market_sentiment}\n{indices_info}"
                }
            },
            {"tag": "hr"},
             {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**🌍 宏观/消息面**: \n{macro_summary}"
                }
            },
            {"tag": "hr"}
        ]

        # Signal Scorecard Section
        scorecard = data.get('signal_scorecard')
        if scorecard:
            sc_text = f"**📊 信号追踪** | {scorecard.get('summary_text', '')}\n"
            for e in scorecard.get('yesterday_evaluation', []):
                if e['result'] == 'NEUTRAL':
                    continue
                icon = "✅" if e['result'] == 'HIT' else "❌"
                sc_text += f"{icon} {e['name']} {e['yesterday_signal']}→{e['today_change']}%\n"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": sc_text}})
            elements.append({"tag": "hr"})

        # 2. Portfolio Grouping (Danger first)
        # 🔧 统一信号标签体系
        # Processor信号: SAFE, OVERBOUGHT, OBSERVED, WATCH, WARNING, DANGER, LIMIT_UP, LIMIT_DOWN, N/A
        # 映射到Feishu组:
        #   SELL组 (红): DANGER, WARNING, LIMIT_DOWN (跌停无法卖出，但需警示)
        #   WATCH组 (黄): WATCH, OBSERVED, OVERBOUGHT (超买需观察是否回调)
        #   HOLD组 (绿): SAFE, HOLD, LIMIT_UP (涨停继续持有)
        #   特殊组 (灰): N/A (数据不足)

        grouped_actions: Dict[str, List[Dict[str, Any]]] = {
            "SELL": [],
            "WATCH": [],
            "HOLD": [],
            "LIMIT": [],  # 涨跌停特殊组
            "UNKNOWN": []  # 数据不足
        }

        # 信号到组的映射
        SIGNAL_GROUP_MAP = {
            # SELL组 (需要减仓/离场)
            "DANGER": "SELL",
            "WARNING": "SELL",
            "SELL": "SELL",
            "LOCKED_DANGER": "SELL",  # T+1锁定但处于危险状态，仍需警示
            # WATCH组 (需要观察)
            "WATCH": "WATCH",
            "OBSERVED": "WATCH",
            "OVERBOUGHT": "WATCH",
            # HOLD组 (安全持有)
            "SAFE": "HOLD",
            "HOLD": "HOLD",
            # 涨跌停特殊处理
            "LIMIT_UP": "LIMIT",
            "LIMIT_DOWN": "LIMIT",
            # 数据不足
            "N/A": "UNKNOWN"
        }

        for stock in actions:
            act = stock.get('action', 'HOLD').upper()
            signal = stock.get('signal', act).upper()  # 优先用signal字段

            # 使用映射确定分组
            group = SIGNAL_GROUP_MAP.get(signal, SIGNAL_GROUP_MAP.get(act, "UNKNOWN"))
            grouped_actions[group].append(stock)

        # Helper to render a group
        def render_group(title, emoji, stock_list):
            if not stock_list: return
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{emoji} {title} ({len(stock_list)})**"
                }
            })
            for s in stock_list:
                name = s.get('name')
                code = s.get('code')
                reason = s.get('reason', '')
                confidence = s.get('confidence', '')
                key_level = s.get('key_level', '')
                
                # Check if we have price info inside the AI action object?
                # AI output usually doesn't strictly copy price.
                # But we can ask AI to include it, OR we merge it in main.py.
                # For simplicity, let's hope AI includes it if we prompt it, OR...
                # Actually, main.py passes raw 'ai_input' to Gemini, but 'analysis_result' comes from AI.
                # AI doesn't return 'pct_change'.
                # We need to MATCH code to raw data in main.py to get price info?
                # That's too complex for this step.
                # Better approach: Modify Prompt to ask AI to strictly echo "Price: xx, Change: xx%"?
                # Or just let AI decide.
                # But the user specifically asked for "各个股票今天的涨跌".
                # If we don't merge, we don't have it.
                # So I should merge in main.py.
                
                pct_info = s.get('pct_change_str', '') # Expect this to be injected by main.py
                
                # Modified content for midday report to include price
                price = s.get('current_price', 0)
                price_display = f" ¥{price}" if price else ""
                
                content = f"**{name}** ({code}){price_display} {pct_info}"
                
                # 🔧 FIX: 显示 T+1 锁定警告
                signal_note = s.get('signal_note', '')
                if signal_note:
                    content += f"\n> ⚠️ **{signal_note}**"

                # Highlight Operation Advice
                operation = s.get('operation', '')
                if operation:
                    # Emphasize operation (e.g. 加仓/减仓)
                    content += f"\n> 🔥 **建议**: {operation}"
                    
                if confidence: content += f" `置信度:{confidence}`"
                content += f"\n> 💡 {reason}"
                if key_level: content += f"\n> 🎯 关键位: {key_level}"

                tech_summary = s.get('tech_summary', '')
                if tech_summary:
                    content += f"\n> 📊 {tech_summary}"
                
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                })
            elements.append({"tag": "hr"})

        # Render Order: SELL -> LIMIT -> WATCH -> HOLD -> UNKNOWN
        render_group("建议离场/减仓", "🔴", grouped_actions["SELL"])
        render_group("涨跌停锁定", "🔒", grouped_actions["LIMIT"])
        render_group("重点观察/洗盘", "🟡", grouped_actions["WATCH"])
        render_group("持仓安好/躺赢", "🟢", grouped_actions["HOLD"])
        if grouped_actions["UNKNOWN"]:
            render_group("数据不足", "⚪", grouped_actions["UNKNOWN"])

        # 3. Footer with Date and Session
        from datetime import datetime
        now = datetime.now()
        date_str = now.strftime('%Y年%m月%d日')
        hour = now.hour
        
        # Determine market session
        if hour < 12:
            session = "盘中（上午）"
        elif hour < 15:
            session = "盘中（下午）"
        else:
            session = "收盘后"
            
        elements.append({
             "tag": "note",
             "elements": [
                 {
                     "tag": "plain_text",
                     "content": f"Sentinel AI V2.0 • {date_str} {session} • {time.strftime('%H:%M')}"
                 }
             ]
         })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": header_color,
                "title": {
                    "tag": "plain_text",
                    "content": "🛡️ 哨兵智能投顾 (Pro)"
                }
            },
            "elements": elements
        }
        return card

    def send_close_card(self, data: Dict[str, Any]):
        """Sends the close review card to Feishu."""
        card_content = self._construct_close_card(data)
        payload = {
            "msg_type": "interactive",
            "card": card_content
        }
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Feishu close review sent successfully.")
            else:
                logger.error(f"Feishu close push failed: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send Feishu close card: {e}")

    def send_morning_card(self, data: Dict[str, Any]):
        """Sends the morning pre-market brief card to Feishu."""
        if not self.webhook_url:
            logger.warning("Skipping Feishu push (No URL)")
            return

        try:
            card_content = self._construct_morning_card(data)
            payload = {
                "msg_type": "interactive",
                "card": card_content
            }
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            resp_json = response.json()
            if resp_json.get("code") != 0:
                logger.error(f"Feishu Error: {resp_json}")
            else:
                logger.info("Feishu morning brief sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send Feishu morning card: {e}")

    def _construct_morning_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Constructs the Feishu Interactive Card for morning pre-market brief.
        Layout: 🌍隔夜全球 → 📦大宗/汇率 → ⚠️风险事件 → 🎯A股预判 → 📋持仓策略
        """
        global_summary = data.get("global_overnight_summary", "暂无隔夜综述")
        commodity_summary = data.get("commodity_summary", "")
        treasury_impact = data.get("us_treasury_impact", "")
        a_share_outlook = data.get("a_share_outlook", "平开")
        risk_events = data.get("risk_events", [])
        actions = data.get("actions", [])

        # Header color based on outlook
        header_color = "blue"
        if "低开" in a_share_outlook or "LOW" in a_share_outlook.upper():
            header_color = "red"
        elif "高开" in a_share_outlook or "HIGH" in a_share_outlook.upper():
            header_color = "green"

        from datetime import datetime
        date_str = datetime.now().strftime('%Y年%m月%d日')

        elements = []

        # 1. 🌍 隔夜全球市场
        # Inject raw global indices if available
        global_indices_info = data.get("global_indices_info", "")
        global_section = f"**🌍 隔夜全球市场**\n{global_indices_info}\n{global_summary}"
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": global_section}
        })
        elements.append({"tag": "hr"})

        # 2. 📦 大宗商品 & 美债
        commodities_info = data.get("commodities_info", "")
        treasury_info = data.get("treasury_info", "")
        commodity_section = f"**📦 大宗商品 & 汇率**\n{commodities_info}\n{commodity_summary}"
        if treasury_impact:
            commodity_section += f"\n**💰 美债**: {treasury_info}\n{treasury_impact}"
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": commodity_section}
        })
        elements.append({"tag": "hr"})

        # 3. ⚠️ 风险事件
        if risk_events:
            risk_text = "**⚠️ 今日风险事件**\n" + "\n".join(f"• {e}" for e in risk_events)
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": risk_text}
            })
            elements.append({"tag": "hr"})

        # 4. 🎯 A股预判
        # Opening expectation emoji
        if "高开" in a_share_outlook or "HIGH" in a_share_outlook.upper():
            outlook_emoji = "⬆️"
        elif "低开" in a_share_outlook or "LOW" in a_share_outlook.upper():
            outlook_emoji = "⬇️"
        else:
            outlook_emoji = "➡️"

        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🎯 A股开盘预判** {outlook_emoji}\n{a_share_outlook}"}
        })
        elements.append({"tag": "hr"})

        # 5. 📋 持仓策略
        if actions:
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**📋 持仓开盘策略 ({len(actions)}只)**"}
            })

            for s in actions:
                name = s.get('name', '')
                code = s.get('code', '')
                driver = s.get('overnight_driver', '')
                expectation = s.get('opening_expectation', 'FLAT')
                strategy = s.get('strategy', '')
                ma20_status = s.get('ma20_status', '')
                key_level = s.get('key_level', 0)

                # Expectation emoji
                if expectation == 'HIGH_OPEN':
                    exp_emoji = "⬆️高开"
                elif expectation == 'LOW_OPEN':
                    exp_emoji = "⬇️低开"
                else:
                    exp_emoji = "➡️平开"

                content = f"**{name}** ({code}) {exp_emoji}"
                if driver:
                    content += f"\n> 🌐 驱动: {driver}"
                content += f"\n> 📊 MA20: {ma20_status}"
                if strategy:
                    content += f"\n> 🔥 **策略**: {strategy}"
                if key_level:
                    content += f"\n> 🎯 关键位: {key_level}"

                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content}
                })

            elements.append({"tag": "hr"})

        # Footer
        elements.append({
            "tag": "note",
            "elements": [{
                "tag": "plain_text",
                "content": f"Sentinel AI V2.0 • {date_str} 盘前战备简报 • {time.strftime('%H:%M')}"
            }]
        })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": header_color,
                "title": {
                    "tag": "plain_text",
                    "content": "☀️ 哨兵盘前战备简报"
                }
            },
            "elements": elements
        }

    def _construct_close_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Constructs the Feishu Interactive Card for close review.
        """
        market_summary = data.get("market_summary", "暂无总结")
        market_temperature = data.get("market_temperature", "N/A")
        actions = data.get("actions", [])

        # Temperature-based color
        header_color = "blue"
        if "冰点" in market_temperature:
            header_color = "red"
        elif "亢奋" in market_temperature:
            header_color = "orange"

        from datetime import datetime
        date_str = datetime.now().strftime('%Y年%m月%d日')

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📊 市场温度**: {market_temperature}\n**📝 今日总结**: {market_summary}"
                }
            },
            {"tag": "hr"}
        ]

        # Signal Scorecard Section
        scorecard = data.get('signal_scorecard')
        if scorecard:
            sc_text = f"**📊 信号追踪** | {scorecard.get('summary_text', '')}\n"
            for e in scorecard.get('yesterday_evaluation', []):
                if e['result'] == 'NEUTRAL':
                    continue
                icon = "✅" if e['result'] == 'HIT' else "❌"
                sc_text += f"{icon} {e['name']} {e['yesterday_signal']}→{e['today_change']}%\n"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": sc_text}})
            elements.append({"tag": "hr"})

        # Per-stock review
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📈 个股复盘 ({len(actions)}只)**"
            }
        })

        for s in actions:
            name = s.get('name', '')
            code = s.get('code', '')
            today_review = s.get('today_review', '')
            tomorrow_plan = s.get('tomorrow_plan', '')
            support = s.get('support_level', 0)
            resistance = s.get('resistance_level', 0)
            
            # Enhanced Header with Price and Pct
            price = s.get('current_price', 0)
            pct_str = s.get('pct_change_str', '')
            
            price_display = f" ¥{price}" if price else ""
            
            content = f"**{name}** ({code}){price_display} {pct_str}"
            content += f"\n> 📋 **今日**: {today_review}"
            content += f"\n> 🎯 **明日**: {tomorrow_plan}"
            if support and resistance:
                content += f"\n> 📐 支撑: {support} / 压力: {resistance}"

            tech_summary = s.get('tech_summary', '')
            confidence = s.get('confidence', '')
            if tech_summary:
                content += f"\n> 📊 {tech_summary}"
            if confidence:
                content += f" `置信度:{confidence}`"
            
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            })
        elements.append({"tag": "hr"})

        # Footer
        elements.append({
             "tag": "note",
             "elements": [
                 {
                     "tag": "plain_text",
                     "content": f"Sentinel AI V2.0 • {date_str} 收盘复盘 • {time.strftime('%H:%M')}"
                 }
             ]
         })

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": header_color,
                "title": {
                    "tag": "plain_text",
                    "content": "🌙 哨兵收盘复盘"
                }
            },
            "elements": elements
        }

if __name__ == "__main__":
    # Test
    client = FeishuClient()
    mock_data = {
        "market_sentiment": "冰点 (Cold)",
        "summary": "大盘缩量下跌，北向资金大幅流出，建议谨慎防御。",
        "actions": [
            {"code": "600519", "name": "贵州茅台", "action": "HOLD", "reason": "虽下跌但未破位"},
            {"code": "300750", "name": "宁德时代", "action": "DANGER", "reason": "放量跌破MA20"}
        ]
    }
    # client.send_card(mock_data) # Uncomment to test with real URL
    print(json.dumps(client._construct_card(mock_data), indent=2, ensure_ascii=False))
