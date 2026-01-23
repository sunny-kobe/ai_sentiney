import unittest
import sys
import os
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.main import post_process_result
from src.reporter.feishu_client import FeishuClient

class TestReportEnhancement(unittest.TestCase):
    def setUp(self):
        self.processed_stocks = [
            {
                "code": "600519",
                "name": "贵州茅台",
                "current_price": 1700.5,
                "pct_change": 1.25,
                "ma20": 1680.0,
                "signal": "SAFE"
            },
            {
                "code": "300750",
                "name": "宁德时代",
                "current_price": 180.2,
                "pct_change": -0.5,
                "ma20": 185.0,
                "signal": "WATCH"
            }
        ]
        self.ai_input = {
            "stocks": self.processed_stocks,
            "indices": {"上证指数": {"change_pct": 0.5}}
        }

    def test_post_process_result_injection(self):
        analysis_result = {
            "actions": [
                {"code": "600519", "name": "贵州茅台", "today_review": "稳健", "tomorrow_plan": "持股", "support_level": 1650, "resistance_level": 1750},
                {"code": "300750", "name": "宁德时代", "today_review": "调整", "tomorrow_plan": "观望", "support_level": 175, "resistance_level": 190}
            ]
        }
        
        processed_result = post_process_result(analysis_result, self.ai_input)
        
        # Verify injection for first stock
        action1 = processed_result['actions'][0]
        self.assertEqual(action1['current_price'], 1700.5)
        self.assertIn("1.25%", action1['pct_change_str'])
        self.assertIn("🔴", action1['pct_change_str'])
        
        # Verify injection for second stock
        action2 = processed_result['actions'][1]
        self.assertEqual(action2['current_price'], 180.2)
        self.assertIn("-0.5%", action2['pct_change_str'])
        self.assertIn("🟢", action2['pct_change_str'])

    def test_feishu_card_rendering(self):
        analysis_result = {
            "market_summary": "测试市场",
            "market_temperature": "正常",
            "actions": [
                {
                    "code": "600519", 
                    "name": "贵州茅台", 
                    "current_price": 1700.5, 
                    "pct_change_str": "`🔴 +1.25%`",
                    "today_review": "今日复盘内容",
                    "tomorrow_plan": "明日计划内容",
                    "support_level": 1650,
                    "resistance_level": 1750
                }
            ]
        }
        
        client = FeishuClient()
        card = client._construct_close_card(analysis_result)
        
        # Verify card content
        found_price_info = False
        for element in card['elements']:
            if element.get('tag') == 'div':
                content = element.get('text', {}).get('content', '')
                if "**贵州茅台** (600519) ¥1700.5 `🔴 +1.25%`" in content:
                    found_price_info = True
                    break
        
        self.assertTrue(found_price_info, "Price and pct info not found in card elements")

if __name__ == "__main__":
    unittest.main()
