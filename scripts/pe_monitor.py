"""
PE 百分位定投监控 v3 — 修正版

修复：
1. 用 csindex 真实 PE 历史数据（10年+每日），不再用价格反推
2. 只监控宽基指数，去掉行业/小盘 ETF
3. 阈值适配 A 股（<30% 定投 / 30-70% 持有 / >70% 分批卖）
4. 明确说明：PE 百分位仅用于长期定投资金配置，不影响短期交易信号

数据源：
- 历史 PE：csindex.com.cn index-perf API 的 peg 字段（每日，10年+）
- 当前 PE：AkShare stock_zh_index_value_csindex（PE-TTM，最近20天）
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import akshare as ak
    import requests
except ImportError:
    ak = None
    requests = None

DB_PATH = Path(__file__).parent.parent / "data" / "pe_history.db"
CSINDEX_PERF_API = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# 只保留宽基指数（行业/小盘指数 PE 百分位无参考价值）
BROAD_INDEX_MAP = {
    "510300": {"name": "沪深300ETF", "index_code": "000300", "index_name": "沪深300"},
    "510500": {"name": "中证500ETF", "index_code": "000905", "index_name": "中证500"},
    "159338": {"name": "中证A500ETF", "index_code": "000510", "index_name": "中证A500"},
    "159934": {"name": "黄金ETF", "index_code": None, "index_name": "黄金"},
}

# A 股适配阈值（比美股更宽，A 股波动大）
THRESHOLDS = {
    "buy": 30,     # < 30% → 定投区
    "hold_upper": 70,  # 30-70% → 持有区
    "sell": 70,    # > 70% → 卖出区
}


def _init_db():
    """初始化 PE 历史数据库。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pe_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            index_code TEXT NOT NULL,
            index_name TEXT,
            pe_ttm REAL,
            source TEXT DEFAULT 'csindex',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, index_code)
        )
    """)
    conn.commit()
    return conn


def fetch_csindex_historical_pe(index_code: str, years: int = 10) -> List[Dict[str, Any]]:
    """
    从 csindex API 获取真实历史 PE 数据。
    csindex index-perf 的 peg 字段即为 PE 值。
    """
    if not requests:
        return []
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")
        url = f"{CSINDEX_PERF_API}?indexCode={index_code}&startDate={start_date}&endDate={end_date}"
        resp = requests.get(url, timeout=20, headers=HEADERS)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
        results = []
        for d in data:
            peg = d.get("peg")
            trade_date = d.get("tradeDate", "")
            if peg is not None and trade_date:
                try:
                    pe_val = float(peg)
                    date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                    results.append({"date": date_str, "pe_ttm": pe_val})
                except (ValueError, TypeError):
                    continue
        return results
    except Exception as e:
        print(f"[PE] 获取 {index_code} csindex 历史PE失败: {e}")
        return []


def fetch_current_pe(index_code: str) -> Optional[Dict[str, Any]]:
    """从 AkShare 获取指数当前 PE-TTM（最近20天）。"""
    if not ak:
        return None
    try:
        df = ak.stock_zh_index_value_csindex(symbol=index_code)
        if df is None or df.empty:
            return None
        row = df.iloc[-1]
        pe1 = row.get("市盈率1")
        date_str = str(row.get("日期", ""))
        return {
            "date": date_str,
            "pe_ttm": float(pe1) if pe1 and pe1 != "-" else None,
        }
    except Exception as e:
        print(f"[PE] 获取 {index_code} AkShare PE失败: {e}")
        return None


def store_pe_batch(conn: sqlite3.Connection, index_code: str, index_name: str, records: List[Dict[str, Any]], source: str = "csindex"):
    """批量存储 PE 数据。"""
    for r in records:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO pe_records (date, index_code, index_name, pe_ttm, source) VALUES (?, ?, ?, ?, ?)",
                (r["date"], index_code, index_name, r["pe_ttm"], source),
            )
        except Exception:
            pass
    conn.commit()


def get_pe_history(conn: sqlite3.Connection, index_code: str) -> List[float]:
    """获取所有历史 PE 数据。"""
    cursor = conn.execute(
        "SELECT pe_ttm FROM pe_records WHERE index_code = ? AND pe_ttm IS NOT NULL ORDER BY date",
        (index_code,),
    )
    return [row[0] for row in cursor.fetchall()]


def get_pe_stats(conn: sqlite3.Connection, index_code: str) -> Dict[str, Any]:
    """获取 PE 统计信息。"""
    history = get_pe_history(conn, index_code)
    if not history:
        return {"count": 0}
    return {
        "count": len(history),
        "min": round(min(history), 2),
        "max": round(max(history), 2),
        "avg": round(sum(history) / len(history), 2),
        "median": round(sorted(history)[len(history) // 2], 2),
    }


def calculate_percentile(current_pe: float, history: List[float]) -> Optional[float]:
    """计算当前 PE 在历史中的百分位。"""
    if not history or len(history) < 30:
        return None
    count_below = sum(1 for h in history if h < current_pe)
    return round(count_below / len(history) * 100, 1)


def get_signal(percentile: Optional[float]) -> Dict[str, str]:
    """根据百分位返回信号（A 股适配阈值）。"""
    if percentile is None:
        return {"zone": "数据不足", "emoji": "⚪", "action": "历史数据不足，无法判断"}
    if percentile < THRESHOLDS["buy"]:
        return {"zone": "定投区", "emoji": "🟢", "action": f"PE 百分位 {percentile}%，低于 {THRESHOLDS['buy']}%，适合定投"}
    elif percentile < THRESHOLDS["hold_upper"]:
        return {"zone": "持有区", "emoji": "🟡", "action": f"PE 百分位 {percentile}%，{THRESHOLDS['buy']}-{THRESHOLDS['hold_upper']}%，持有不动"}
    else:
        return {"zone": "卖出区", "emoji": "🔴", "action": f"PE 百分位 {percentile}%，高于 {THRESHOLDS['sell']}%，考虑分批卖出"}


def run_pe_monitor(backfill: bool = True) -> Dict[str, Any]:
    """运行 PE 监控。"""
    conn = _init_db()
    results = []
    today = datetime.now().strftime("%Y-%m-%d")

    for etf_code, info in BROAD_INDEX_MAP.items():
        index_code = info["index_code"]
        index_name = info["index_name"]

        if index_code is None:
            results.append({
                "etf_code": etf_code,
                "etf_name": info["name"],
                "index_name": index_name,
                "pe_ttm": None,
                "percentile": None,
                "stats": {},
                "signal": "黄金等商品类无PE估值，不适用此策略",
                "emoji": "⚪",
                "zone": "不适用",
            })
            continue

        # 检查是否需要回填历史数据
        stats = get_pe_stats(conn, index_code)
        if backfill and stats.get("count", 0) < 100:
            print(f"[PE] {index_name}: 回填 csindex 历史 PE 数据...")
            historical = fetch_csindex_historical_pe(index_code, years=10)
            if historical:
                store_pe_batch(conn, index_code, index_name, historical, "csindex")
                print(f"[PE] {index_name}: 回填 {len(historical)} 条真实 PE 数据")
            time.sleep(0.5)

        # 获取当前 PE（AkShare 真实 PE-TTM）
        pe_data = fetch_current_pe(index_code)
        if pe_data and pe_data["pe_ttm"]:
            # 存储今日真实 PE（优先使用 AkShare 的 PE-TTM）
            store_pe_batch(conn, index_code, index_name, [{"date": today, "pe_ttm": pe_data["pe_ttm"]}], "akshare")
            current_pe = pe_data["pe_ttm"]
        else:
            # 降级：用 csindex 最新数据
            historical = fetch_csindex_historical_pe(index_code, years=1)
            if historical:
                current_pe = historical[-1]["pe_ttm"]
                store_pe_batch(conn, index_code, index_name, [{"date": today, "pe_ttm": current_pe}], "csindex_fallback")
            else:
                results.append({
                    "etf_code": etf_code,
                    "etf_name": info["name"],
                    "index_name": index_name,
                    "pe_ttm": None,
                    "percentile": None,
                    "stats": {},
                    "signal": "PE 数据获取失败",
                    "emoji": "⚪",
                    "zone": "获取失败",
                })
                continue

        # 计算百分位
        history = get_pe_history(conn, index_code)
        stats = get_pe_stats(conn, index_code)
        percentile = calculate_percentile(current_pe, history)
        signal = get_signal(percentile)

        results.append({
            "etf_code": etf_code,
            "etf_name": info["name"],
            "index_name": index_name,
            "pe_ttm": current_pe,
            "percentile": percentile,
            "stats": stats,
            "signal": signal["action"],
            "emoji": signal["emoji"],
            "zone": signal["zone"],
        })

        time.sleep(0.3)

    conn.close()

    # 生成摘要
    alerts = [r for r in results if r.get("percentile") is not None and r["percentile"] < THRESHOLDS["buy"]]
    sell_alerts = [r for r in results if r.get("percentile") is not None and r["percentile"] >= THRESHOLDS["sell"]]

    summary_lines = ["📊 PE 百分位定投监控（宽基指数）"]
    summary_lines.append(f"日期: {today} | 阈值: <{THRESHOLDS['buy']}%定投 / {THRESHOLDS['buy']}-{THRESHOLDS['hold_upper']}%持有 / >{THRESHOLDS['sell']}%卖出\n")

    for r in results:
        line = f"{r['emoji']} {r['etf_name']}({r['etf_code']})"
        if r["pe_ttm"]:
            line += f" | PE: {r['pe_ttm']}"
        if r["percentile"] is not None:
            line += f" | 百分位: {r['percentile']}%"
        if r.get("stats", {}).get("count"):
            line += f" | 数据: {r['stats']['count']}天"
        line += f" | {r['zone']}"
        summary_lines.append(line)

    if alerts:
        summary_lines.append(f"\n🟢 定投信号 ({len(alerts)}只):")
        for a in alerts:
            summary_lines.append(f"  · {a['etf_name']}: PE百分位 {a['percentile']}%，适合定投")

    if sell_alerts:
        summary_lines.append(f"\n🔴 卖出信号 ({len(sell_alerts)}只):")
        for a in sell_alerts:
            summary_lines.append(f"  · {a['etf_name']}: PE百分位 {a['percentile']}%，考虑333法分批卖出")

    if not alerts and not sell_alerts:
        summary_lines.append(f"\n💡 所有标的均在持有区，无需操作。")

    summary_lines.append(f"\n⚠️ 注意：PE百分位仅用于长期定投资金配置，不影响 ai_sentiney 短期交易信号。")

    return {
        "summary": "\n".join(summary_lines),
        "results": results,
        "alerts": alerts,
        "sell_alerts": sell_alerts,
    }


if __name__ == "__main__":
    result = run_pe_monitor()
    print(result["summary"])
    print("\n--- 历史 PE 统计 ---")
    for r in result["results"]:
        s = r.get("stats", {})
        if s.get("count"):
            print(f"  {r['index_name']}: {s['count']}天 | 范围: {s['min']}~{s['max']} | 均值: {s['avg']} | 中位: {s['median']}")
