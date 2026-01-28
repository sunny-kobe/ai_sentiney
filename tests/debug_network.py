import time
import socket
import requests
from urllib.parse import urlparse

TARGETS = [
    "http://qt.gtimg.cn/q=sh600519", # Tencent (Known Good)
    "http://datacenter-web.eastmoney.com/api/data/v1/get", # Efinance Internal URL (HTTP)
    "https://datacenter-web.eastmoney.com/api/data/v1/get", # Efinance Internal URL (HTTPS)
    "https://push2.eastmoney.com/api/qt/clist/get", # AkShare/Efinance Spot (HTTPS)
    "https://www.baidu.com" # Control
]

def check_dns(url):
    domain = urlparse(url).netloc
    try:
        ip = socket.gethostbyname(domain)
        print(f"[DNS] ✅ {domain} -> {ip}")
        return True
    except Exception as e:
        print(f"[DNS] ❌ {domain} -> Failed: {e}")
        return False

def check_http(url):
    try:
        start = time.time()
        # Short timeout to fail fast
        resp = requests.get(url, timeout=5)
        elapsed = time.time() - start
        status = resp.status_code
        # Eastmoney APIs usually return 200 even for empty params
        print(f"[HTTP] ✅ {url} -> Status: {status}, Time: {elapsed:.2f}s")
        return True
    except requests.exceptions.ConnectTimeout:
        print(f"[HTTP] ❌ {url} -> Connection Timed Out")
    except requests.exceptions.ReadTimeout:
        print(f"[HTTP] ❌ {url} -> Read Timed Out")
    except requests.exceptions.ConnectionError as e:
        print(f"[HTTP] ❌ {url} -> Connection Error: {e}")
    except Exception as e:
        print(f"[HTTP] ❌ {url} -> Unexpected: {e}")
    return False

if __name__ == "__main__":
    print("=== NETWORK DIAGNOSTICS ===")
    for url in TARGETS:
        print(f"\nTesting: {url}")
        if check_dns(url):
            check_http(url)
    print("\n=== END DIAGNOSTICS ===")
