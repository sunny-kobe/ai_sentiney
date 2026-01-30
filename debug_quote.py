import asyncio
import aiohttp
import time

async def fetch_tencent_quote(code_list):
    # Format: sh510300, sz000001
    codes_str = ",".join(code_list)
    url = f"http://qt.gtimg.cn/q={codes_str}"
    print(f"Fetching: {url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            text = await response.text()
            print(f"Response: {text[:200]}...") # Print first 200 chars
            
            # Parse logic
            lines = text.strip().split(';')
            for line in lines:
                if 'v_' not in line: continue
                parts = line.split('=')
                if len(parts) < 2: continue
                
                data_str = parts[1].strip('"')
                vals = data_str.split('~')
                if len(vals) > 30:
                    name = vals[1]
                    code = vals[2]
                    curr = vals[3]
                    prev_close = vals[4]
                    open_p = vals[5]
                    date_time = vals[30]
                    print(f"Code: {code}, Name: {name}, Current: {curr}, Time: {date_time}")

if __name__ == "__main__":
    # Test 510300 (SH ETF), 601899 (Purple Gold), 000603 (Silver)
    codes = ["sh510300", "sh601899", "sz000603"]
    asyncio.run(fetch_tencent_quote(codes))
