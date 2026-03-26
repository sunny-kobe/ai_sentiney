from typing import Any, Dict


PRESET_LABELS = {
    "aggressive_trend_guard": "激进趋势防守",
    "aggressive_leader_focus": "激进龙头聚焦",
    "aggressive_core_rotation": "激进核心轮动",
}


def get_lab_hint_preset_label(preset: str) -> str:
    return PRESET_LABELS.get(preset or "", preset or "未知策略")


def get_lab_hint_winner_label(winner: str) -> str:
    winner_value = str(winner or "").strip().lower()
    if winner_value == "candidate":
        return "当前更优"
    if winner_value == "baseline":
        return "暂未跑赢基线"
    return "暂未拉开差距"


def build_lab_hint_header(hint: Dict[str, Any]) -> str:
    if not hint:
        return ""
    preset = get_lab_hint_preset_label(str(hint.get("preset", "") or ""))
    winner = get_lab_hint_winner_label(str(hint.get("winner", "") or ""))
    return f"实验优选: {preset}（{winner}）"


def build_lab_hint_detail(hint: Dict[str, Any], *, markdown: bool = False) -> str:
    if not hint:
        return ""
    preset_code = str(hint.get("preset", "unknown") or "unknown")
    preset_label = get_lab_hint_preset_label(preset_code)
    title = "**实验提示**" if markdown else "实验提示:"
    return (
        f"{title} {preset_label}（{preset_code}） | {hint.get('summary_text', '')}\n"
        f"分数差: {float(hint.get('score_delta', 0.0) or 0.0):.2f}"
        f" | 交易变化: {int(hint.get('trade_count_delta', 0) or 0)}"
        f" | 候选交易: {int(hint.get('candidate_trade_count', 0) or 0)}笔"
    )
