from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence

from src.backtest.adapter import build_orders_from_actions
from src.backtest.report import summarize_backtest


def _sorted_records(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(records, key=lambda item: str(item.get("date", "")))


def _bar_map(record: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    stocks = ((record.get("raw_data") or {}).get("stocks", []) or [])
    mapping: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        code = str(stock.get("code", "") or "")
        if code:
            mapping[code] = dict(stock)
    return mapping


def _trade_price(stock: Mapping[str, Any], *, side: str, slippage_rate: float) -> float:
    base_price = float(stock.get("open") or stock.get("current_price") or stock.get("close") or 0)
    if side == "buy":
        return round(base_price * (1 + slippage_rate), 4)
    return round(base_price * (1 - slippage_rate), 4)


def _mark_price(stock: Mapping[str, Any]) -> float:
    return float(stock.get("close") or stock.get("current_price") or stock.get("open") or 0)


def _portfolio_value(cash: float, positions: Mapping[str, int], bars: Mapping[str, Mapping[str, Any]]) -> float:
    holdings_value = 0.0
    for code, shares in positions.items():
        stock = bars.get(code)
        if not stock or shares <= 0:
            continue
        holdings_value += shares * _mark_price(stock)
    return round(cash + holdings_value, 2)


def _lot_round(shares: float, lot_size: int) -> int:
    if shares <= 0:
        return 0
    return int(math.floor(shares / lot_size) * lot_size)


def run_deterministic_backtest(
    records: Sequence[Mapping[str, Any]],
    *,
    initial_cash: float = 100_000.0,
    fee_rate: float = 0.0003,
    sell_tax_rate: float = 0.001,
    slippage_rate: float = 0.0005,
    lot_size: int = 100,
) -> Dict[str, Any]:
    ordered = _sorted_records(records)
    cash = float(initial_cash)
    positions: Dict[str, int] = {}
    last_buy_date: Dict[str, str] = {}
    trades = []
    equity_curve = []
    total_fees = 0.0

    if not ordered:
        result = {
            "initial_cash": initial_cash,
            "cash": cash,
            "positions": positions,
            "trades": trades,
            "equity_curve": equity_curve,
            "total_fees": total_fees,
        }
        result.update(summarize_backtest(result))
        return result

    initial_bars = _bar_map(ordered[0])
    equity_curve.append({"date": ordered[0].get("date"), "total_value": _portfolio_value(cash, positions, initial_bars)})

    for index in range(1, len(ordered)):
        current_record = ordered[index]
        current_date = str(current_record.get("date", ""))
        current_bars = _bar_map(current_record)
        prior_actions = ((ordered[index - 1].get("ai_result") or {}).get("actions", []) or [])
        orders = build_orders_from_actions(prior_actions, trade_date=current_date)

        for order in sorted(orders, key=lambda item: item["target_weight"]):
            code = order["code"]
            stock = current_bars.get(code)
            if not stock:
                continue

            current_shares = int(positions.get(code, 0) or 0)
            total_value = _portfolio_value(cash, positions, current_bars)
            target_weight = float(order["target_weight"])
            fill_price = _trade_price(stock, side="buy" if target_weight > 0 else "sell", slippage_rate=slippage_rate)
            if fill_price <= 0:
                continue
            target_value = total_value * target_weight
            target_shares = _lot_round(target_value / fill_price, lot_size)

            if target_shares < current_shares:
                if last_buy_date.get(code) == current_date:
                    continue
                sell_shares = current_shares - target_shares
                gross = sell_shares * _trade_price(stock, side="sell", slippage_rate=slippage_rate)
                fees = gross * fee_rate + gross * sell_tax_rate
                cash += gross - fees
                total_fees += fees
                positions[code] = target_shares
                trades.append(
                    {
                        "trade_date": current_date,
                        "code": code,
                        "side": "sell",
                        "shares": sell_shares,
                        "fill_price": _trade_price(stock, side="sell", slippage_rate=slippage_rate),
                        "fees": round(fees, 2),
                    }
                )
            elif target_shares > current_shares:
                buy_shares = target_shares - current_shares
                max_affordable = _lot_round(cash / (fill_price * (1 + fee_rate)), lot_size)
                buy_shares = min(buy_shares, max_affordable)
                if buy_shares <= 0:
                    continue
                gross = buy_shares * fill_price
                fees = gross * fee_rate
                cash -= gross + fees
                total_fees += fees
                positions[code] = current_shares + buy_shares
                last_buy_date[code] = current_date
                trades.append(
                    {
                        "trade_date": current_date,
                        "code": code,
                        "side": "buy",
                        "shares": buy_shares,
                        "fill_price": fill_price,
                        "fees": round(fees, 2),
                    }
                )

        equity_curve.append({"date": current_date, "total_value": _portfolio_value(cash, positions, current_bars)})

    result = {
        "initial_cash": float(initial_cash),
        "cash": round(cash, 2),
        "positions": positions,
        "trades": trades,
        "equity_curve": equity_curve,
        "total_fees": round(total_fees, 2),
    }
    result.update(summarize_backtest(result))
    return result
