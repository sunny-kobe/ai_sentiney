import asyncio
import pandas as pd
from src.collector.sources.tencent_source import TencentSource
from src.collector.sources.akshare_source import AkshareSource

async def main():
    print("--- Debugging TencentSource ---")
    ts = TencentSource()
    try:
        df_t = ts.fetch_prices("510300", count=5)
        if df_t is not None and not df_t.empty:
            print("Tencent Data (Tail 2):")
            print(df_t.tail(2))
            
            last_close = df_t.iloc[-1]['close']
            last_date = df_t.iloc[-1]['date']
            print(f"Tencent Last: {last_date} Close: {last_close}")
        else:
            print("Tencent returned Empty or None")
    except Exception as e:
        print(f"Tencent Error: {e}")

    print("\n--- Debugging AkShareSource ---")
    as_ = AkshareSource()
    try:
        # Note: AkshareSource.fetch_prices internal logic uses ak.stock_zh_a_hist_tx
        df_a = as_.fetch_prices("510300", count=5)
        if df_a is not None and not df_a.empty:
            # AkShare source renames 'date' to 'Date'
            print("AkShare Data (Tail 2):")
            print(df_a.tail(2))
            
            last_close = df_a.iloc[-1]['Close']
            last_date = df_a.iloc[-1]['Date']
            print(f"AkShare Last: {last_date} Close: {last_close}")
        else:
            print("AkShare returned Empty or None")
    except Exception as e:
        print(f"AkShare Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
