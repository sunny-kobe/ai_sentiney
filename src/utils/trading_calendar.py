from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from typing import Any, Dict, Optional

import akshare as ak
import pandas as pd

from src.utils.logger import logger


def _normalize_target_date(target_date: Optional[date | datetime]) -> date:
    if target_date is None:
        return datetime.now().date()
    if isinstance(target_date, datetime):
        return target_date.date()
    return target_date


def is_trading_day(target_date: Optional[date | datetime] = None) -> Dict[str, Any]:
    """
    Determine whether the target day is an A-share trading day.
    Falls back to weekday semantics if the exchange calendar is unavailable.
    """
    day = _normalize_target_date(target_date)

    try:
        df = ak.tool_trade_date_hist_sina()
        if df is not None and not df.empty:
            trade_dates = pd.to_datetime(df.iloc[:, 0]).dt.date
            is_open = day in set(trade_dates.tolist())
            return {
                "date": day.isoformat(),
                "is_trading_day": is_open,
                "source": "exchange_calendar",
                "fallback": False,
            }
    except Exception as exc:
        logger.warning(f"Trading calendar lookup failed for {day}: {exc}")

    return {
        "date": day.isoformat(),
        "is_trading_day": day.weekday() < 5,
        "source": "weekday_fallback",
        "fallback": True,
    }


def should_run_market_report(
    mode: str,
    publish: bool,
    target_date: Optional[date | datetime] = None,
    *,
    replay: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Decide whether an automated market report should run.
    Manual replay / dry-run are always allowed.
    """
    calendar = is_trading_day(target_date)

    if replay or dry_run:
        return {
            "should_run": True,
            "skip_reason": None,
            "calendar": calendar,
            "mode": mode,
            "publish": publish,
        }

    if not calendar["is_trading_day"]:
        return {
            "should_run": False,
            "skip_reason": "non_trading_day",
            "calendar": calendar,
            "mode": mode,
            "publish": publish,
        }

    return {
        "should_run": True,
        "skip_reason": None,
        "calendar": calendar,
        "mode": mode,
        "publish": publish,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="A-share trading day guard")
    parser.add_argument("--mode", required=True, choices=["morning", "midday", "close", "swing"])
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--date", dest="target_date", default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None
    decision = should_run_market_report(
        mode=args.mode,
        publish=args.publish,
        target_date=target_date,
    )
    print(json.dumps(decision, ensure_ascii=False))
    return 0 if decision["should_run"] else 78


if __name__ == "__main__":
    sys.exit(main())
