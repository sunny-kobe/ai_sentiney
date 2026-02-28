"""
Signal Tracker: 信号评估引擎
评估历史信号准确性，计算滚动命中率，为 AI 自我校准提供数据基础。
纯函数模块，不依赖外部状态。
"""
import json
from typing import Dict, Any, List, Optional


# ============================================================
# 信号评估规则
# ============================================================

def evaluate_signal(signal: str, next_day_pct: float) -> str:
    """
    评估单个信号是否命中。

    Args:
        signal: 昨日信号 (DANGER/WARNING/SAFE/OVERBOUGHT/WATCH/OBSERVED/LIMIT_UP/LIMIT_DOWN)
        next_day_pct: 次日涨跌幅 (百分比，如 -3.5 表示跌3.5%)

    Returns:
        HIT / MISS / NEUTRAL
    """
    signal = signal.upper()

    # 永远 NEUTRAL 的信号
    if signal in ('WATCH', 'OBSERVED', 'LIMIT_UP', 'LIMIT_DOWN', 'HOLD', 'N/A', 'LOCKED_DANGER'):
        return 'NEUTRAL'

    if signal == 'DANGER':
        if next_day_pct < -0.5:
            return 'HIT'
        elif next_day_pct > 1.0:
            return 'MISS'
        return 'NEUTRAL'

    if signal == 'WARNING':
        if next_day_pct <= 0:
            return 'HIT'
        elif next_day_pct > 1.0:
            return 'MISS'
        return 'NEUTRAL'

    if signal == 'SAFE':
        if next_day_pct > -1.0:
            return 'HIT'
        elif next_day_pct < -2.0:
            return 'MISS'
        return 'NEUTRAL'

    if signal == 'OVERBOUGHT':
        if next_day_pct < -0.5:
            return 'HIT'
        elif next_day_pct > 1.0:
            return 'MISS'
        return 'NEUTRAL'

    return 'NEUTRAL'


# ============================================================
# 单日评估：昨日信号 vs 今日实际涨跌
# ============================================================

def evaluate_yesterday(yesterday_actions: List[Dict], today_stocks: List[Dict]) -> List[Dict]:
    """
    对比昨日每只股票的信号与今日实际涨跌。

    Args:
        yesterday_actions: 昨日 ai_result['actions'] 列表
        today_stocks: 今日 ai_input['stocks'] 列表（含 pct_change）

    Returns:
        [{"code", "name", "yesterday_signal", "confidence", "today_change", "result"}]
    """
    # 构建今日涨跌映射 (code → pct_change)
    today_map = {}
    for s in today_stocks:
        code = s.get('code', '')
        today_map[code] = s.get('pct_change', 0.0)

    results = []
    for action in yesterday_actions:
        code = action.get('code', '')
        name = action.get('name', '')
        # 支持 midday 的 signal/action 字段，也兼容 close 模式
        signal = action.get('signal', action.get('action', 'N/A')).upper()
        confidence = action.get('confidence', '')

        today_change = today_map.get(code)
        if today_change is None:
            continue  # 今日无此股票数据，跳过

        result = evaluate_signal(signal, today_change)
        results.append({
            'code': code,
            'name': name,
            'yesterday_signal': signal,
            'confidence': confidence,
            'today_change': today_change,
            'result': result,
        })

    return results


# ============================================================
# 滚动统计：多日命中率
# ============================================================

def calculate_rolling_stats(records: List[Dict], days: int = 7) -> Dict:
    """
    从多日 DB 记录计算滚动命中率。

    records 来自 db.get_records_range()，每条含 {date, raw_data, ai_result}。
    需要相邻两天配对（Day N 的信号 vs Day N+1 的涨跌）。

    Args:
        records: DB 记录列表（按日期降序）
        days: 统计天数

    Returns:
        滚动统计字典
    """
    if len(records) < 2:
        return _empty_stats(days)

    # records 按日期降序，需要反转为升序来配对
    sorted_records = sorted(records, key=lambda r: r['date'])

    all_evals = []

    for i in range(len(sorted_records) - 1):
        day_record = sorted_records[i]
        next_day_record = sorted_records[i + 1]

        ai_result = day_record.get('ai_result')
        next_raw = next_day_record.get('raw_data')

        if not ai_result or not next_raw:
            continue

        actions = ai_result.get('actions', [])
        next_stocks = next_raw.get('stocks', [])

        if not actions or not next_stocks:
            continue

        evals = evaluate_yesterday(actions, next_stocks)
        all_evals.extend(evals)

    # 过滤 NEUTRAL
    scored = [e for e in all_evals if e['result'] != 'NEUTRAL']

    if not scored:
        return _empty_stats(days)

    total = len(scored)
    hits = sum(1 for e in scored if e['result'] == 'HIT')
    hit_rate = round(hits / total, 2) if total > 0 else 0

    # 分置信度统计
    by_confidence = {}
    for e in scored:
        conf = e.get('confidence', '未知') or '未知'
        if conf not in by_confidence:
            by_confidence[conf] = {'total': 0, 'hits': 0}
        by_confidence[conf]['total'] += 1
        if e['result'] == 'HIT':
            by_confidence[conf]['hits'] += 1

    for conf, stats in by_confidence.items():
        stats['rate'] = round(stats['hits'] / stats['total'], 2) if stats['total'] > 0 else 0

    # 分信号类型统计
    by_signal = {}
    for e in scored:
        sig = e['yesterday_signal']
        if sig not in by_signal:
            by_signal[sig] = {'total': 0, 'hits': 0}
        by_signal[sig]['total'] += 1
        if e['result'] == 'HIT':
            by_signal[sig]['hits'] += 1

    for sig, stats in by_signal.items():
        stats['rate'] = round(stats['hits'] / stats['total'], 2) if stats['total'] > 0 else 0

    return {
        'period_days': days,
        'total': total,
        'hits': hits,
        'hit_rate': hit_rate,
        'by_confidence': by_confidence,
        'by_signal': by_signal,
    }


def _compute_risk_stats(by_signal: Dict) -> Dict:
    """
    Compute hit rate for risk signals only (excluding SAFE).
    SAFE signals are easy to hit (next day > -1%) and inflate overall accuracy.
    Risk signals (DANGER, WARNING, OVERBOUGHT) are the real value of the system.
    """
    risk_signals = {'DANGER', 'WARNING', 'OVERBOUGHT'}
    risk_total = 0
    risk_hits = 0
    for sig, stats in by_signal.items():
        if sig in risk_signals:
            risk_total += stats.get('total', 0)
            risk_hits += stats.get('hits', 0)
    return {
        'total': risk_total,
        'hits': risk_hits,
        'rate': round(risk_hits / risk_total, 2) if risk_total > 0 else 0,
    }


def _empty_stats(days: int) -> Dict:
    return {
        'period_days': days,
        'total': 0,
        'hits': 0,
        'hit_rate': 0,
        'by_confidence': {},
        'by_signal': {},
    }


# ============================================================
# 组装 Scorecard
# ============================================================

def build_scorecard(yesterday_eval: List[Dict], rolling_stats: Dict) -> Dict:
    """
    组装完整信号追踪报告。

    Args:
        yesterday_eval: evaluate_yesterday() 的结果
        rolling_stats: calculate_rolling_stats() 的结果

    Returns:
        {"yesterday_evaluation": [...], "rolling_stats": {...}, "summary_text": "..."}
    """
    # 生成摘要文本
    parts = []
    rate = rolling_stats.get('hit_rate', 0)
    total = rolling_stats.get('total', 0)

    if total > 0:
        parts.append(f"近{rolling_stats['period_days']}日命中率{int(rate * 100)}%({rolling_stats['hits']}/{total})")

        # 风险信号命中率（DANGER/WARNING/OVERBOUGHT，剥离 SAFE）
        by_signal = rolling_stats.get('by_signal', {})
        risk_stats = _compute_risk_stats(by_signal)
        if risk_stats['total'] > 0:
            parts.append(f"风险信号{int(risk_stats['rate'] * 100)}%({risk_stats['hits']}/{risk_stats['total']})")
        rolling_stats['risk_stats'] = risk_stats

        # 高置信度命中率
        high_conf = rolling_stats.get('by_confidence', {}).get('高', {})
        if high_conf.get('total', 0) > 0:
            parts.append(f"高置信度{int(high_conf['rate'] * 100)}%")
    else:
        parts.append("历史数据不足，暂无统计")

    summary_text = " | ".join(parts)

    return {
        'yesterday_evaluation': yesterday_eval,
        'rolling_stats': rolling_stats,
        'summary_text': summary_text,
    }
