---
name: AkShare Mastery
description: Expert guide for using AkShare to fetch Chinese financial data, covering installation, proxy configuration, resilience patterns, and key interfaces.
---

# AkShare Mastery Skill

AkShare is an open-source financial data interface library for Python, built for human beings! It fetches data from various sources (Eastmoney, Sina, Xueqiu, etc.) primarily via web scraping.

## 1. Core Philosophy

- **Data Source Aggregator**: AkShare isn't a data provider itself; it's a collected interface for scraping other providers.
- **Dependency**: If the upstream source (e.g., Eastmoney) changes its API or blocks IPs, AkShare breaks.
- **No Native Proxy Config**: It uses standard Python `requests`. Proxies must be set via standard environment variables.

## 2. Installation & Mirror

For faster installation in China, use Aliyun mirror:

```bash
pip install akshare --upgrade -i https://mirrors.aliyun.com/pypi/simple/
```

## 3. Network & Proxy Configuration (Critical)

Since AkShare scrapes websites, it is vulnerable to IP blocking (403 Forbidden / Connection Reset). To use a proxy:

### Method A: Environment Variables (Recommended)

Set these before running your script.

```bash
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
python main.py
```

### Method B: Python Context (Targeted)

```python
import os
import akshare as ak

# Apply proxy globally for the process just before calling AkShare
os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

df = ak.stock_zh_a_spot_em()
```

## 4. Key Interfaces (A-Share)

### Real-time Quotes

- **Spot Data (All Stocks)**: `ak.stock_zh_a_spot_em()`
  - Source: Eastmoney
  - Columns: 代码, 名称, 最新价, 涨跌幅, ...
  - Note: High failure rate if IP is dirty.

### Historical Data

- **Daily K-line**: `ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20230101", adjust="qfq")`
  - Source: Eastmoney
  - Symbols: "000001" (no prefix usually).

### Market Breadth / Northbound

- **Northbound Funds**: `ak.stock_hsgt_fund_flow_summary_em()`

## 5. Resilience Pattern (The "Antigravity" Way)

Never call AkShare directly in production without these wrappers:

1.  **Timeout Protection**: Blocking calls _will_ hang indefinitely if the server holds the connection. Use `asyncio.wait_for` or `func_timeout`.
2.  **Retries**: Use `tenacity` library.
3.  **Validation**: Always check `if df.empty`.

```python
from tenacity import retry, stop_after_attempt
import akshare as ak

@retry(stop=stop_after_attempt(3))
def safe_fetch_spot():
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise ValueError("Empty response")
    return df
```

## 6. Troubleshooting

- **Connection Reset / Timeout**: 99% chance your IP is blocked by Eastmoney. Switch IP or wait 2-24 hours.
- **AttributeError**: AkShare updates frequently. Run `pip install akshare --upgrade`.
- **"Zero Data"**: Check if today is a trading day.
