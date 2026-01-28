import akshare as ak
import sys

print("Testing AkShare Tencent Backend...")

try:
    print("1. Testing stock_zh_a_hist_tx (Tencent History)...")
    # Tencent usually needs prefix like sh600519 or just 600519? Akshare usually handles it.
    # checking doc pattern: usually symbol='sz000001'
    df = ak.stock_zh_a_hist_tx(symbol="sz000001", start_date="20240101", end_date="20240105", adjust="qfq")
    print(f"Success! Result shape: {df.shape}")
    print(df.head(2))
except Exception as e:
    print(f"Failed: {e}")

try:
    print("\n2. Testing stock_zh_a_spot (Likely Sina or other)...")
    df = ak.stock_zh_a_spot()
    print(f"Success! Result shape: {df.shape}")
    print(df.head(2))
except Exception as e:
    print(f"Failed: {e}")
