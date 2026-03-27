import io
from contextlib import redirect_stdout

from src.main import _print_text_summary
from src.reporter.feishu_client import FeishuClient
from src.reporter.telegram_client import TelegramClient


def _make_swing_result():
    return {
        "market_regime": "防守",
        "market_conclusion": "当前偏防守，先守住已有成果，弱势方向以收缩仓位为主。",
        "validation_summary": "真实建议跟踪近90天已兑现20日建议8笔，平均跑赢基准1.6%，增配组平均收益4.2%；这套建议近期仍有效，可以继续进攻，但继续分批。",
        "validation_compact": {
            "verdict": "最近这套中期动作整体有效，可以继续进攻，但仍按分批方式执行。",
            "live_sample_count": 8,
            "live_primary_window": 20,
            "synthetic_sample_count": 12,
            "synthetic_primary_window": 20,
            "backtest_trade_count": 4,
            "walkforward_segment_count": 5,
            "offensive_allowed": True,
            "offensive_reason": "真实建议近期进攻统计仍有效，正式回测未见明显恶化",
        },
        "execution_readiness": "谨慎执行",
        "quality_summary": "核心行情完整，但市场广度和宏观消息暂时缺失。已有仓位可按计划处理，新开仓先等补齐信息。",
        "lab_hint": {
            "preset": "aggressive_leader_focus",
            "winner": "candidate",
            "summary_text": "candidate 更优；回测收益变化10.4%，最大回撤变化10.5%，交易笔数变化-181。",
            "score_delta": 6.834,
            "trade_count_delta": -181,
            "candidate_trade_count": 18,
            "total_return_delta": 0.1038,
            "max_drawdown_delta": 0.1048,
        },
        "position_plan": {
            "total_exposure": "35%-50%",
            "core_target": "25%-35%",
            "satellite_target": "0%-5%",
            "cash_target": "50%-65%",
            "current_total_exposure": "68.7%",
            "current_cash_pct": "31.3%",
            "account_total_assets": "105744.34",
            "cash_balance": "33091.73",
            "weekly_rebalance": "每周五收盘后生成计划，下一交易日分批执行。",
            "daily_rule": "下一交易日按优先级分批执行，先减弱势仓，再处理持有仓，最后考虑新增仓。",
            "execution_order": ["中证2000ETF:卖出2900份，保留约2300份", "军工ETF:先试仓5%-10%"],
            "buckets": {
                "核心仓": [{"code": "510300", "name": "沪深300ETF", "target_weight": "25%-35%"}],
                "卫星仓": [{"code": "563300", "name": "中证2000ETF", "target_weight": "0%-3%"}],
                "现金": [],
            },
            "validation_budgets": [
                {"label": "大盘核心方向", "budget_range": "25%-35%", "status": "正常", "reason": "20日验证稳定，当前不额外压缩。"},
                {"label": "中小盘方向", "budget_range": "0%-5%", "status": "受限", "reason": "20日验证偏弱，先只保留试仓级预算。"},
            ],
        },
        "portfolio_actions": {
            "增配": [],
            "持有": [{"code": "510300", "name": "沪深300ETF"}],
            "减配": [{"code": "563300", "name": "中证2000ETF"}],
            "回避": [],
        },
        "actions": [
            {
                "code": "510300",
                "name": "沪深300ETF",
                "conclusion": "持有",
                "action_label": "持有",
                "position_bucket": "核心仓",
                "target_weight": "25%-35%",
                "current_weight": "10.7%",
                "current_shares": 600,
                "current_value": "2668.80",
                "rebalance_action": "先按当前仓位拿住",
                "reason": "还站在20日线 4.01 上方，主趋势还在，承接还在配合。",
                "plan": "先把现有仓位拿住，等下一次确认转强再决定要不要加。",
                "risk_line": "收盘跌回20日线 4.01 下方，就先缩仓。",
                "validation_note": "20日验证里，大盘核心方向样本10笔，平均跑赢基准0.7%，回撤约2.6%。",
                "technical_evidence": "MACD多头，站上20日线",
            },
            {
                "code": "563300",
                "name": "中证2000ETF",
                "conclusion": "减配",
                "action_label": "减配",
                "position_bucket": "卫星仓",
                "target_weight": "0%-3%",
                "current_weight": "6.8%",
                "current_shares": 5200,
                "current_value": "7165.60",
                "rebalance_action": "卖出2900份，保留约2300份",
                "reason": "已经落到20日线 0.50 下方，已经开始转弱，承接偏弱。",
                "plan": "先收缩一部分仓位，把组合波动降下来。",
                "risk_line": "不能重新站上20日线 0.50 之前，先别加仓。",
                "validation_note": "中小盘方向的20日验证偏弱，样本6笔，平均落后基准2.4%，回撤约8.9%。",
                "technical_evidence": "MACD死叉，跌破20日线",
            },
        ],
        "watchlist_actions": {
            "转正式仓": [],
            "进入试仓区": [
                {
                    "code": "512660",
                    "name": "军工ETF",
                    "action_label": "进入试仓区",
                    "reason": "重新站上20日线，量能同步放大。",
                    "plan": "先试仓5%-10%，确认延续后再考虑转正式仓。",
                    "risk_line": "跌回20日线下方则撤回观察。",
                }
            ],
            "继续观察": [],
        },
        "watchlist_candidates": [
            {
                "code": "512660",
                "name": "军工ETF",
                "action_label": "进入试仓区",
                "reason": "重新站上20日线，量能同步放大。",
                "plan": "先试仓5%-10%，确认延续后再考虑转正式仓。",
                "risk_line": "跌回20日线下方则撤回观察。",
            }
        ],
        "technical_evidence": [
            {"code": "510300", "name": "沪深300ETF", "tech_summary": "MACD多头，站上20日线"},
            {"code": "563300", "name": "中证2000ETF", "tech_summary": "MACD死叉，跌破20日线"},
        ],
        "swing_scorecard": {"summary_text": "10日样本8，平均收益2.4%，平均回撤-1.8%"},
        "data_timestamp": "2026-03-23",
        "source_labels": ["rule_engine", "history"],
    }


def test_cli_swing_summary_uses_plain_language_sections():
    output = io.StringIO()
    with redirect_stdout(output):
        _print_text_summary(_make_swing_result(), "swing")

    rendered = output.getvalue()
    lines = rendered.splitlines()
    assert "今日结论" in rendered
    assert "账户动作" in rendered
    assert "方向预算" in rendered
    assert "持仓处理" in rendered
    assert "观察池机会" in rendered
    assert "风险清单" in rendered
    assert "验证摘要" in rendered
    assert "执行提示" in rendered
    assert "谨慎执行" in rendered
    assert "新开仓先等补齐信息" in rendered
    assert "真实建议跟踪" in rendered
    assert "实验提示" in rendered
    assert "激进龙头聚焦" in rendered
    assert any("实验优选: 激进龙头聚焦（当前更优）" in line for line in lines[:6])
    assert "当前总仓位: 68.7%" in rendered
    assert "总仓位: 35%-50%" in rendered
    assert "优先动作: 中证2000ETF:卖出2900份，保留约2300份；军工ETF:先试仓5%-10%" in rendered
    assert "[510300] 沪深300ETF | 结论:持有 | 当前:10.7% | 目标:25%-35%" in rendered
    assert "验证: 20日验证里，大盘核心方向样本10笔，平均跑赢基准0.7%，回撤约2.6%。" in rendered
    assert "大盘核心方向: 正常 | 预算:25%-35%" in rendered
    assert "[512660] 军工ETF | 动作:进入试仓区" in rendered
    assert "MACD" not in rendered
    assert "中期跟踪" not in rendered


def test_telegram_swing_text_shows_action_buckets_and_risk_lines():
    client = TelegramClient()
    text = client._build_swing_text(_make_swing_result())
    lines = text.splitlines()

    assert "今日结论" in text
    assert "账户动作" in text
    assert "方向预算" in text
    assert "现金目标: 50%-65%" in text
    assert "当前总仓位: 68.7%" in text
    assert "观察池机会" in text
    assert "执行提示" in text
    assert "谨慎执行" in text
    assert "军工ETF" in text
    assert "验证摘要" in text
    assert "真实建议跟踪" in text
    assert "真实样本: 20日8笔 | 历史样本: 20日12笔 | 进攻权限: 允许（真实建议近期进攻统计仍有效，正式回测未见明显恶化）" in text
    assert "验证: 20日验证里，大盘核心方向样本10笔，平均跑赢基准0.7%，回撤约2.6%。" in text
    assert "大盘核心方向: 正常 | 预算:25%-35%" in text
    assert "实验提示" in text
    assert "激进龙头聚焦" in text
    assert any("实验优选: 激进龙头聚焦（当前更优）" in line for line in lines[:4])
    assert "风险清单" in text


def test_feishu_swing_card_shows_plain_language_sections():
    client = FeishuClient()
    card = client._construct_swing_card(_make_swing_result())

    contents = [
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    ]
    joined = "\n".join(contents)
    assert "今日结论" in joined
    assert "账户动作" in joined
    assert "方向预算" in joined
    assert "总仓位" in joined
    assert "当前总仓位" in joined
    assert "持仓处理" in joined
    assert "观察池机会" in joined
    assert "执行提示" in joined
    assert "谨慎执行" in joined
    assert "验证摘要" in joined
    assert "真实建议跟踪" in joined
    assert "真实样本: 20日8笔 | 历史样本: 20日12笔 | 进攻权限: 允许（真实建议近期进攻统计仍有效，正式回测未见明显恶化）" in joined
    assert "验证: 20日验证里，大盘核心方向样本10笔，平均跑赢基准0.7%，回撤约2.6%。" in joined
    assert "大盘核心方向: 正常 | 预算:25%-35%" in joined
    assert "实验提示" in joined
    assert "激进龙头聚焦" in joined
    assert "实验优选: 激进龙头聚焦（当前更优）" in contents[1]
    assert "风险清单" in joined


def test_swing_rendering_surfaces_data_issues():
    result = _make_swing_result()
    result["data_issues"] = ["缓存行情未覆盖当前账户的全部标的：512660，请优先使用 --mode swing --dry-run 拉取实时数据。"]

    output = io.StringIO()
    with redirect_stdout(output):
        _print_text_summary(result, "swing")
    rendered = output.getvalue()

    telegram_text = TelegramClient()._build_swing_text(result)
    feishu_card = FeishuClient()._construct_swing_card(result)
    feishu_joined = "\n".join(
        element.get("text", {}).get("content", "")
        for element in feishu_card["elements"]
        if element.get("tag") == "div"
    )

    assert "缓存行情未覆盖当前账户的全部标的" in rendered
    assert "缓存行情未覆盖当前账户的全部标的" in telegram_text
    assert "缓存行情未覆盖当前账户的全部标的" in feishu_joined
