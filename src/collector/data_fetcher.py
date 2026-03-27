import asyncio
import functools
import re
import sys
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.thread import _threads_queues, _worker
from dataclasses import dataclass, field, asdict
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from src.utils.config_loader import ConfigLoader
from src.utils.logger import logger
from src.collector.sources.efinance_source import EfinanceSource
from src.collector.sources.akshare_source import AkshareSource
from src.collector.sources.tencent_source import TencentSource

from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class CircuitBreakerState:
    """
    🔧 优化后的熔断器状态
    - 要求连续3次失败才熔断
    - 30秒后进入半开状态，允许一次尝试
    """
    failure_count: int = 0
    is_open: bool = False  # True = 熔断中
    last_failure_time: float = 0.0

    # 配置
    FAILURE_THRESHOLD: int = 3  # 连续失败N次才熔断
    RECOVERY_TIMEOUT: float = 30.0  # 熔断后30秒进入半开状态


class DaemonThreadPoolExecutor(ThreadPoolExecutor):
    """Thread pool whose workers do not block process exit when third-party calls hang."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._worker_bootstrap_mode: Optional[str] = None
        self._worker_bootstrap_logged = False

    def _resolve_worker_bootstrap_mode(self) -> str:
        if self._worker_bootstrap_mode:
            return self._worker_bootstrap_mode

        if hasattr(self, "_initializer") and hasattr(self, "_initargs"):
            self._worker_bootstrap_mode = "legacy_initializer_args"
        elif hasattr(self, "_create_worker_context"):
            self._worker_bootstrap_mode = "worker_context_args"
        else:
            raise RuntimeError(
                "Unsupported ThreadPoolExecutor worker bootstrap "
                f"for Python {sys.version.split()[0]}: "
                f"initializer={hasattr(self, '_initializer')} "
                f"initargs={hasattr(self, '_initargs')} "
                f"worker_context={hasattr(self, '_create_worker_context')}"
            )
        return self._worker_bootstrap_mode

    def _build_worker_args(self):
        def weakref_cb(_, q=self._work_queue):
            q.put(None)

        executor_ref = weakref.ref(self, weakref_cb)
        mode = self._resolve_worker_bootstrap_mode()
        if mode == "legacy_initializer_args":
            worker_args = (
                self._work_queue,
                self._initializer,
                self._initargs,
            )
        else:
            worker_args = (
                self._create_worker_context(),
                self._work_queue,
            )
        if not self._worker_bootstrap_logged:
            logger.info(f"DaemonThreadPoolExecutor bootstrap mode: {mode}")
            self._worker_bootstrap_logged = True
        return executor_ref, worker_args

    def _adjust_thread_count(self):
        # Follow the stdlib implementation for the current Python runtime,
        # then only add daemonization to avoid hanging process exits.
        if self._idle_semaphore.acquire(timeout=0):
            return

        num_threads = len(self._threads)
        if num_threads < self._max_workers:
            thread_name = '%s_%d' % (self._thread_name_prefix or self, num_threads)
            executor_ref, worker_args = self._build_worker_args()
            thread = threading.Thread(
                name=thread_name,
                target=_worker,
                args=(executor_ref, *worker_args),
            )
            thread.daemon = True
            thread.start()
            self._threads.add(thread)
            _threads_queues[thread] = self._work_queue


class DataCollector:
    def __init__(self):
        # GitHub Actions runners / Standard Cloud Instances (2-4 vCPUs)
        self.executor = DaemonThreadPoolExecutor(max_workers=16)
        self.config = ConfigLoader().config
        self.state_file = "data/circuit_breaker_state.json"

        # Priority: Tencent -> Efinance -> AkShare
        self.sources = [TencentSource(), EfinanceSource(), AkshareSource()]

        # Read history_days from config (needed for MACD calculation)
        risk_cfg = self.config.get('risk_management', {})
        ti_cfg = risk_cfg.get('technical_indicators', {})
        self.history_days = ti_cfg.get('history_days', 60)

        # 🔧 优化: 使用结构化的熔断器状态，替代简单的disabled set
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {
            source.get_source_name(): CircuitBreakerState()
            for source in self.sources
        }
        self._load_circuit_breaker_state()

    def _init_collection_status(self, block_names: List[str]) -> Dict[str, Any]:
        return {
            "overall_status": "fresh",
            "blocks": {
                name: {
                    "status": "missing",
                    "source": None,
                    "detail": "",
                }
                for name in block_names
            },
            "issues": [],
            "source_labels": [],
        }

    def _mark_collection_block(
        self,
        collection_status: Dict[str, Any],
        block_name: str,
        status: str,
        *,
        source: Optional[str] = None,
        detail: str = "",
    ) -> None:
        block = collection_status["blocks"].setdefault(
            block_name,
            {"status": "missing", "source": None, "detail": ""},
        )
        block["status"] = status
        block["source"] = source
        block["detail"] = detail
        if source and source not in collection_status["source_labels"]:
            collection_status["source_labels"].append(source)

    def _append_collection_issue(self, collection_status: Dict[str, Any], issue: str) -> None:
        if issue and issue not in collection_status["issues"]:
            collection_status["issues"].append(issue)

    def _finalize_collection_status(self, collection_status: Dict[str, Any]) -> Dict[str, Any]:
        block_statuses = [block.get("status", "missing") for block in collection_status["blocks"].values()]
        if any(status in {"missing", "degraded"} for status in block_statuses):
            collection_status["overall_status"] = "degraded"
        else:
            collection_status["overall_status"] = "fresh"
        return collection_status

    def close(self):
        """Release thread-pool resources so CLI runs can exit cleanly."""
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _load_circuit_breaker_state(self):
        """Load circuit breaker states from disk."""
        try:
            import os
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    for name, state_dict in data.items():
                        if name in self._circuit_breakers:
                            # Restore state
                            cb = self._circuit_breakers[name]
                            cb.failure_count = state_dict.get('failure_count', 0)
                            cb.is_open = state_dict.get('is_open', False)
                            cb.last_failure_time = state_dict.get('last_failure_time', 0.0)
                logger.info("Circuit breaker states loaded from disk.")
        except Exception as e:
            logger.warning(f"Failed to load circuit breaker states: {e}")

    def _save_circuit_breaker_state(self):
        """Persist circuit breaker states to disk."""
        try:
            states = {name: asdict(cb) for name, cb in self._circuit_breakers.items()}
            with open(self.state_file, 'w') as f:
                json.dump(states, f)
        except Exception as e:
            logger.warning(f"Failed to save circuit breaker states: {e}")

    def _should_skip_source(self, source_name: str) -> bool:
        """
        检查数据源是否应该跳过（熔断中且未到恢复时间）
        """
        cb = self._circuit_breakers.get(source_name)
        if not cb:
            return False

        if not cb.is_open:
            return False

        # 检查是否到了半开恢复时间
        elapsed = time.time() - cb.last_failure_time
        if elapsed >= cb.RECOVERY_TIMEOUT:
            logger.info(f"Circuit Breaker: {source_name} entering half-open state (trying recovery)")
            return False  # 允许尝试

        return True  # 仍在熔断中

    def _record_success(self, source_name: str):
        """记录成功，重置熔断器"""
        cb = self._circuit_breakers.get(source_name)
        if cb:
            if cb.is_open:
                logger.info(f"Circuit Breaker: {source_name} recovered successfully")
            cb.failure_count = 0
            cb.is_open = False
            self._save_circuit_breaker_state()

    def _record_failure(self, source_name: str):
        """记录失败，可能触发熔断"""
        cb = self._circuit_breakers.get(source_name)
        if not cb:
            return

        cb.failure_count += 1
        cb.last_failure_time = time.time()

        if cb.failure_count >= cb.FAILURE_THRESHOLD:
            cb.is_open = True
            logger.warning(
                f"Circuit Breaker: {source_name} OPEN after {cb.failure_count} consecutive failures. "
                f"Will retry in {cb.RECOVERY_TIMEOUT}s."
            )
        else:
            logger.info(
                f"Circuit Breaker: {source_name} failure {cb.failure_count}/{cb.FAILURE_THRESHOLD}"
            )
        self._save_circuit_breaker_state()

    async def _run_blocking(self, func, *args, **kwargs):
        """
        Helper to run blocking calls in a thread executor with smart retry logic and timeout.
        """
        loop = asyncio.get_running_loop()
        timeout = kwargs.pop('timeout', 5) # Default 5s timeout (Fail Fast)
        
        @retry(
            stop=stop_after_attempt(3), 
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True
        )
        def retriable_func():
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"API Call {func.__name__} failed: {e}. Retrying...")
                raise e

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self.executor, retriable_func),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Command {func.__name__} timed out after {timeout}s.")
            raise
        except Exception as e:
            # logger.error(f"Command {func.__name__} failed definitively after retries.")
            raise e

    async def _fetch_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        """
        Try to fetch data from sources in priority order.
        🔧 优化: 使用改进的熔断器逻辑
        """
        last_exception = None
        for source in self.sources:
            source_name = source.get_source_name()

            # 熔断器检查
            if self._should_skip_source(source_name):
                continue

            try:
                func = getattr(source, method_name)
                # Run sync source method in thread pool
                result = await self._run_blocking(func, *args, **kwargs)

                # Check for validity
                if result is not None:
                    if isinstance(result, pd.DataFrame) and result.empty:
                        continue  # Try next source if Empty DataFrame
                    # 成功！重置熔断器
                    self._record_success(source_name)
                    return result
            except Exception as e:
                logger.warning(f"Source {source_name} failed for {method_name}: {e}")
                # 记录失败（可能触发熔断）
                self._record_failure(source_name)
                last_exception = e
                continue

        logger.error(f"All sources failed for {method_name}.")
        return None

    def _get_dynamic_start_date(self, days_lookback: int = 60) -> str:
        return (datetime.now() - timedelta(days=days_lookback)).strftime("%Y%m%d")

    async def get_market_breadth(self) -> str:
        """
        Fetches market breadth (Rise/Fall ratio).
        """
        logger.info("Fetching market breadth...")
        # Try abstraction first, or fallback to current manual logic if needed?
        # Current logic is specific with 'stock_zh_a_spot_em'.
        # Let's rely on AkShareSource's fetch_market_breadth for simplicity?
        # But wait, AkshareSource's impl was a placeholder that returns string.
        # The original logic calculated it from spot data.
        # Let's stick to using fetch_market_breadth from interfaces.
        res = await self._fetch_with_fallback('fetch_market_breadth')
        return res if res else "Unknown"

    async def get_north_funds(self) -> float:
        """
        Fetches Real-time Northbound Fund Net Inflow (Unit: 100 million).
        Kept specific to AkShare for now as it's specialized.
        """
        logger.info("Fetching Northbound funds...")
        try:
            df = await self._run_blocking(ak.stock_hsgt_fund_flow_summary_em)
            if df is None or df.empty:
                return 0.0

            mask = df.astype(str).apply(lambda x: x.str.contains('北向')).any(axis=1)
            north_rows = df[mask]
            
            if north_rows.empty:
                return 0.0
            
            # Heuristic to find value column
            value_col = next((col for col in df.columns if '净流入' in str(col)), None)
            
            if not value_col:
                raw_val = north_rows.iloc[0, 1]
            else:
                raw_val = north_rows.iloc[0][value_col]

            val_str = str(raw_val)
            val_clean = re.sub(r'[^\d\.\-]', '', val_str)
            
            try:
                return round(float(val_clean), 2)
            except ValueError:
                return 0.0

        except Exception as e:
            logger.error(f"Error fetching North funds: {e}")
            return 0.0

    async def get_indices(self) -> Dict[str, Dict]:
        """
        Fetches major indices.
        """
        try:
             df = await self._run_blocking(ak.stock_zh_index_spot_sina)
             target_map = {
                 "上证指数": "sh000001",
                 "深证成指": "sz399001", 
                 "创业板指": "sz399006"
             }
             results = {}
             for name in target_map.keys():
                 row = df[df['名称'] == name]
                 if not row.empty:
                     try:
                         results[name] = {
                             "current": float(row.iloc[0]['最新价']),
                             "change_pct": float(row.iloc[0]['涨跌幅'])
                         }
                     except (ValueError, KeyError):
                         continue
             return results
        except Exception as e:
            logger.error(f"Failed to fetch indices: {e}")
            return {}

    async def get_macro_news(self) -> Dict[str, List[str]]:
        """
        Fetches macro news.
        """
        logger.info("Fetching macro news...")
        result: Dict[str, List[str]] = {"telegraph": [], "ai_tech": []}
        
        try:
            today_str = datetime.now().strftime('%Y%m%d')
            df_news = await self._run_blocking(ak.news_cctv, date=today_str)
            
            if df_news is None or df_news.empty:
                 yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
                 df_news = await self._run_blocking(ak.news_cctv, date=yesterday_str)

            if df_news is not None and not df_news.empty:
                result["telegraph"] = df_news.head(10)['title'].tolist()
            else:
                df_global = await self._run_blocking(ak.stock_info_global_em)
                if df_global is not None and not df_global.empty:
                    result["telegraph"] = df_global.head(10)['标题'].tolist()

        except Exception as e:
            logger.warning(f"Failed to fetch macro news: {e}")
        
        ai_keywords = ['人工智能', 'AI', '芯片', '半导体', '算力', '大模型', 'GPU', '英伟达', '华为', '科技', '机器']
        if result["telegraph"]:
            result["ai_tech"] = [
                n for n in result["telegraph"] 
                if any(k in n for k in ai_keywords)
            ][:5]
        
        return result

    async def collect_all(self, portfolio: List[Dict]):
        """
        Main entry point. Orchestrates parallel data fetching.
        """
        logger.info("Starting Batch Data Collection (Dual Source)...")
        collection_status = self._init_collection_status(
            [
                "bulk_spot",
                "market_breadth",
                "north_funds",
                "indices",
                "macro_news",
                "stock_quotes",
                "stock_history",
                "stock_news",
            ]
        )
        
        global_tasks = [
            self.get_market_breadth(),
            self.get_north_funds(),
            self.get_indices(),
            self.get_macro_news()
        ]
        
        # 2. Fetch Spot Data via Fallback
        # This will try Efinance first, then AkShare
        df_all_spot = await self._fetch_with_fallback('fetch_spot_data', timeout=3)
        if df_all_spot is None:
            df_all_spot = pd.DataFrame()
            logger.warning("All sources failed to fetch bulk spot data. Will rely on individual fetch.")
            self._mark_collection_block(
                collection_status,
                "bulk_spot",
                "missing",
                detail="bulk spot fetch failed; relying on single-quote fallback",
            )
            self._append_collection_issue(collection_status, "bulk spot unavailable; switched to single-quote fallback")
        else:
            self._mark_collection_block(collection_status, "bulk_spot", "fresh", source="spot")
        
        stock_tasks = []
        for stock in portfolio:
            code = stock['code']
            stock_tasks.append(self._fetch_individual_stock_extras(code, stock.get('name', 'Unknown'), df_all_spot))
            
        try:
            global_results = await asyncio.gather(*global_tasks, return_exceptions=True)
            stock_results = await asyncio.gather(*stock_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Critical error during gather: {e}")
            # Try to salvage whatever we have
            global_results = [None] * 4
            stock_results = []

        market_breadth = global_results[0] if global_results and not isinstance(global_results[0], Exception) else "Error"
        north_funds = global_results[1] if global_results and not isinstance(global_results[1], Exception) else 0.0
        indices = global_results[2] if global_results and not isinstance(global_results[2], Exception) else {}
        macro_news = global_results[3] if global_results and not isinstance(global_results[3], Exception) else {"telegraph": [], "ai_tech": []}

        if market_breadth and market_breadth not in {"Unknown", "Error", "N/A (Tencent)"}:
            self._mark_collection_block(collection_status, "market_breadth", "fresh", source="market_breadth")
        else:
            self._mark_collection_block(collection_status, "market_breadth", "missing", detail="market breadth unavailable")
            self._append_collection_issue(collection_status, "market breadth unavailable")

        if indices:
            self._mark_collection_block(collection_status, "indices", "fresh", source="indices")
        else:
            self._mark_collection_block(collection_status, "indices", "missing", detail="indices unavailable")
            self._append_collection_issue(collection_status, "indices unavailable")

        if macro_news.get("telegraph"):
            self._mark_collection_block(collection_status, "macro_news", "fresh", source="macro_news")
        else:
            self._mark_collection_block(collection_status, "macro_news", "missing", detail="macro news unavailable")
            self._append_collection_issue(collection_status, "macro news unavailable")

        self._mark_collection_block(collection_status, "north_funds", "fresh", source="north_funds")
        
        valid_stocks = []
        if stock_results:
            valid_stocks = [res for res in stock_results if not isinstance(res, Exception) and isinstance(res, dict) and "error" not in res]

        quote_statuses = [stock.get("quote_status", "missing") for stock in valid_stocks]
        history_statuses = [stock.get("history_status", "missing") for stock in valid_stocks]
        news_statuses = [stock.get("news_status", "missing") for stock in valid_stocks]

        if valid_stocks and any(status == "fresh" for status in quote_statuses):
            self._mark_collection_block(collection_status, "stock_quotes", "fresh", source="stock_quotes")
        else:
            self._mark_collection_block(collection_status, "stock_quotes", "missing", detail="no real-time quotes collected")
            self._append_collection_issue(collection_status, "real-time stock quotes unavailable")

        if valid_stocks and all(status == "fresh" for status in history_statuses):
            self._mark_collection_block(collection_status, "stock_history", "fresh", source="stock_history")
        elif valid_stocks and any(status == "fresh" for status in history_statuses):
            self._mark_collection_block(collection_status, "stock_history", "degraded", detail="some stock history missing")
            self._append_collection_issue(collection_status, "partial stock history missing")
        else:
            self._mark_collection_block(collection_status, "stock_history", "missing", detail="stock history unavailable")
            self._append_collection_issue(collection_status, "stock history unavailable")

        if valid_stocks and any(status == "fresh" for status in news_statuses):
            self._mark_collection_block(collection_status, "stock_news", "fresh", source="stock_news")
        else:
            self._mark_collection_block(collection_status, "stock_news", "missing", detail="stock news unavailable")
            self._append_collection_issue(collection_status, "stock news unavailable")

        self._finalize_collection_status(collection_status)

        return {
            "market_breadth": market_breadth,
            "north_funds": north_funds,
            "indices": indices,
            "macro_news": macro_news,
            "stocks": valid_stocks,
            "collection_status": collection_status,
            "data_issues": collection_status["issues"],
            "source_labels": collection_status["source_labels"],
        }

    # ============================================================
    # Morning Mode: 盘前外盘数据采集
    # ============================================================

    async def get_global_indices(self) -> List[Dict]:
        """
        获取隔夜全球指数（美股/恒生/美元指数等）。
        Uses ak.index_global_spot_em()
        """
        logger.info("Fetching global indices...")
        try:
            df = await self._run_blocking(ak.index_global_spot_em, timeout=20)
            if df is None or df.empty:
                return []

            targets = ['标普500', '纳斯达克', '道琼斯', '恒生指数', '美元指数',
                        '纳斯达克100', '日经225']
            results = []
            for name in targets:
                row = df[df['名称'].str.contains(name, na=False)]
                if not row.empty:
                    try:
                        results.append({
                            "name": name,
                            "current": float(row.iloc[0].get('最新价', 0)),
                            "change_pct": float(row.iloc[0].get('涨跌幅', 0)),
                            "change_amount": float(row.iloc[0].get('涨跌额', 0)),
                        })
                    except (ValueError, KeyError):
                        continue
            return results
        except Exception as e:
            logger.error(f"Failed to fetch global indices: {e}")
            return []

    async def get_commodity_futures(self) -> List[Dict]:
        """
        获取隔夜大宗商品期货（黄金/白银/铜/原油）。
        Uses ak.futures_global_spot_em()
        """
        logger.info("Fetching commodity futures...")
        try:
            df = await self._run_blocking(ak.futures_global_spot_em, timeout=20)
            if df is None or df.empty:
                return []

            targets = ['黄金', '白银', '铜', 'WTI原油', '布伦特原油', 'COMEX铜']
            results = []
            for name in targets:
                row = df[df['名称'].str.contains(name, na=False)]
                if not row.empty:
                    try:
                        results.append({
                            "name": row.iloc[0].get('名称', name),
                            "current": float(row.iloc[0].get('最新价', 0)),
                            "change_pct": float(row.iloc[0].get('涨跌幅', 0)),
                        })
                    except (ValueError, KeyError):
                        continue
            return results
        except Exception as e:
            logger.error(f"Failed to fetch commodity futures: {e}")
            return []

    async def get_us_treasury_yields(self) -> Dict:
        """
        获取美债收益率（2Y/10Y/利差）。
        Uses ak.bond_zh_us_rate() with pandas date filtering.
        """
        logger.info("Fetching US treasury yields...")
        try:
            df = await self._run_blocking(ak.bond_zh_us_rate, start_date="2024-01-01", timeout=20)
            if df is None or df.empty:
                return {}

            # Get most recent row
            latest = df.iloc[-1]
            yield_2y = float(latest.get('美国国债收益率2年', 0))
            yield_10y = float(latest.get('美国国债收益率10年', 0))
            spread = round(yield_10y - yield_2y, 4)

            result = {
                "yield_2y": yield_2y,
                "yield_10y": yield_10y,
                "spread_10y_2y": spread,
            }

            # Calculate change if we have at least 2 rows
            if len(df) >= 2:
                prev = df.iloc[-2]
                prev_10y = float(prev.get('美国国债收益率10年', 0))
                result["yield_10y_change"] = round(yield_10y - prev_10y, 4)

            return result
        except Exception as e:
            logger.error(f"Failed to fetch US treasury yields: {e}")
            return {}

    async def _fetch_morning_stock_context(self, code: str, name: str) -> Dict:
        """
        获取持仓股票的盘前上下文（昨日收盘价 + MA20，无实时价）。
        """
        try:
            df_hist = await self._fetch_with_fallback('fetch_prices', code=code, count=self.history_days)
            if df_hist is None or df_hist.empty:
                return {"code": code, "name": name, "error": "no_history"}

            # Determine close column
            if 'close' in df_hist.columns:
                close_col = 'close'
            elif '收盘' in df_hist.columns:
                close_col = '收盘'
            elif 'Close' in df_hist.columns:
                close_col = 'Close'
            else:
                return {"code": code, "name": name, "error": "no_close_column"}

            last_close = float(df_hist.iloc[-1][close_col])

            # Calculate MA20 from pure historical closes (no real-time stitching)
            ma_window = self.config.get('risk_management', {}).get('ma_window', 20)
            closes = df_hist[close_col].tail(ma_window).tolist()
            ma20 = sum(closes) / len(closes) if closes else 0.0
            bias_pct = (last_close - ma20) / ma20 if ma20 > 0 else 0.0

            # Determine MA20 status
            if bias_pct > 0.01:
                ma20_status = "ABOVE"
            elif bias_pct < -0.01:
                ma20_status = "BELOW"
            else:
                ma20_status = "NEAR"

            return {
                "code": code,
                "name": name,
                "last_close": round(last_close, 3),
                "ma20": round(ma20, 3),
                "bias_pct": round(bias_pct, 4),
                "ma20_status": ma20_status,
            }
        except Exception as e:
            logger.error(f"Failed to fetch morning context for {code}: {e}")
            return {"code": code, "name": name, "error": str(e)}

    async def collect_morning_data(self, portfolio: List[Dict]) -> Dict[str, Any]:
        """
        早报模式的主入口。并行采集外盘数据 + 昨日持仓上下文。
        """
        logger.info("Starting Morning Pre-Market Data Collection...")
        collection_status = self._init_collection_status(
            ["global_indices", "commodities", "us_treasury", "macro_news", "stocks"]
        )

        # Global overnight data tasks
        global_tasks = [
            self.get_global_indices(),
            self.get_commodity_futures(),
            self.get_us_treasury_yields(),
            self.get_macro_news(),
        ]

        # Per-stock historical context
        stock_tasks = [
            self._fetch_morning_stock_context(s['code'], s.get('name', 'Unknown'))
            for s in portfolio
        ]

        try:
            all_results = await asyncio.gather(*global_tasks, *stock_tasks, return_exceptions=True)
            global_results = all_results[:4]
            stock_results = all_results[4:]
        except Exception as e:
            logger.error(f"Critical error during morning gather: {e}")
            global_results = [None] * 4
            stock_results = []

        global_indices = global_results[0] if not isinstance(global_results[0], Exception) else []
        commodities = global_results[1] if not isinstance(global_results[1], Exception) else []
        us_treasury = global_results[2] if not isinstance(global_results[2], Exception) else {}
        macro_news = global_results[3] if not isinstance(global_results[3], Exception) else {"telegraph": [], "ai_tech": []}

        # Log failures for debugging
        labels = ['global_indices', 'commodities', 'us_treasury', 'macro_news']
        for i, label in enumerate(labels):
            if isinstance(global_results[i], Exception):
                logger.warning(f"Morning data {label} failed: {global_results[i]}")

        valid_stocks = [
            res for res in stock_results
            if not isinstance(res, Exception) and isinstance(res, dict) and "error" not in res
        ]

        if global_indices:
            self._mark_collection_block(collection_status, "global_indices", "fresh", source="global_indices")
        else:
            self._mark_collection_block(collection_status, "global_indices", "missing", detail="global indices unavailable")
            self._append_collection_issue(collection_status, "global indices unavailable")

        if commodities:
            self._mark_collection_block(collection_status, "commodities", "fresh", source="commodities")
        else:
            self._mark_collection_block(collection_status, "commodities", "missing", detail="commodities unavailable")
            self._append_collection_issue(collection_status, "commodities unavailable")

        if us_treasury:
            self._mark_collection_block(collection_status, "us_treasury", "fresh", source="us_treasury")
        else:
            self._mark_collection_block(collection_status, "us_treasury", "missing", detail="US treasury unavailable")
            self._append_collection_issue(collection_status, "US treasury unavailable")

        if macro_news.get("telegraph"):
            self._mark_collection_block(collection_status, "macro_news", "fresh", source="macro_news")
        else:
            self._mark_collection_block(collection_status, "macro_news", "missing", detail="macro news unavailable")
            self._append_collection_issue(collection_status, "macro news unavailable")

        if valid_stocks:
            self._mark_collection_block(collection_status, "stocks", "fresh", source="stocks")
        else:
            self._mark_collection_block(collection_status, "stocks", "missing", detail="morning stock context unavailable")
            self._append_collection_issue(collection_status, "morning stock context unavailable")

        self._finalize_collection_status(collection_status)

        return {
            "global_indices": global_indices,
            "commodities": commodities,
            "us_treasury": us_treasury,
            "macro_news": macro_news,
            "stocks": valid_stocks,
            "collection_status": collection_status,
            "data_issues": collection_status["issues"],
            "source_labels": collection_status["source_labels"],
        }

    async def _fetch_individual_stock_extras(self, code: str, stock_name: str, df_all_spot: pd.DataFrame) -> Dict:
        """
        Fetches History and News for a specific stock using fallback.
        """
        try:
            # 1. Spot Data logic
            current_price = 0.0
            pct_change = 0.0
            volume = 0.0
            turnover_rate = 0.0
            name = stock_name
            quote_status = "missing"
            history_status = "missing"
            news_status = "missing"

            if not df_all_spot.empty:
                spot_row = df_all_spot[df_all_spot['code'] == code]
                if not spot_row.empty:
                    try:
                        current_price = float(spot_row.iloc[0]['current_price'])
                        pct_change = float(spot_row.iloc[0]['pct_change'])
                        volume = float(spot_row.iloc[0].get('volume', 0))
                        turnover_rate = float(spot_row.iloc[0].get('turnover_rate', 0))
                        quote_status = "fresh"
                    except (ValueError, KeyError, IndexError):
                        pass

            # 2. Try Individual Real-Time Quote (Fallback for Spot)
            # This is critical if bulk spot fetch failed (e.g. Efinance timeout)
            if current_price == 0.0:
                quote = await self._fetch_with_fallback('fetch_single_quote', code=code, timeout=3)
                if quote:
                    try:
                        current_price = float(quote['current_price'])
                        pct_change = float(quote['pct_change'])
                        volume = float(quote.get('volume', 0))
                        turnover_rate = float(quote.get('turnover_rate', 0))
                        quote_status = "fresh"
                    except Exception as e:
                        logger.warning(f"Failed to parse quote for {code}: {e}")

            # 3. Fetch Prices (History) via Fallback
            df_hist = await self._fetch_with_fallback('fetch_prices', code=code, count=self.history_days, timeout=8)
            if df_hist is None:
                df_hist = pd.DataFrame()
                logger.warning(f"History fetch failed for {code}")
            else:
                history_status = "fresh"

            # Calculate 5-day average volume from history for volume ratio
            # 🔧 修复: 排除今日数据，确保5日均量计算准确
            avg_volume_5d = 0.0
            if not df_hist.empty:
                # Fallback for current_price if spot failed
                if current_price == 0.0:
                    try:
                        current_price = float(df_hist.iloc[-1]['close'])
                        if len(df_hist) >= 2:
                            prev_close = float(df_hist.iloc[-2]['close'])
                            if prev_close > 0:
                                pct_change = ((current_price - prev_close) / prev_close) * 100
                    except Exception:
                        pass

                # 🔧 修复: 过滤今日数据后计算5日均量
                # 问题: df_hist可能包含今日半天数据，导致均量被拉低
                # 解决: 统一使用日期判断
                if 'volume' in df_hist.columns and len(df_hist) >= 5:
                    try:
                        # 尝试按日期过滤
                        today = datetime.now().date()
                        if 'date' in df_hist.columns:
                            df_hist_copy = df_hist.copy()
                            df_hist_copy['date'] = pd.to_datetime(df_hist_copy['date'])
                            df_past = df_hist_copy[df_hist_copy['date'].dt.date < today]
                        elif '日期' in df_hist.columns:
                            df_hist_copy = df_hist.copy()
                            df_hist_copy['日期'] = pd.to_datetime(df_hist_copy['日期'])
                            df_past = df_hist_copy[df_hist_copy['日期'].dt.date < today]
                        else:
                            # 无日期列，如果数据足够多，保守切掉最后一行
                            if len(df_hist) >= 6:
                                df_past = df_hist.iloc[:-1]
                            else:
                                df_past = df_hist # 只能硬着头皮用了
                        
                        if len(df_past) >= 5:
                            avg_volume_5d = float(df_past.tail(5)['volume'].mean())
                        elif len(df_past) > 0:
                            # 至少有一些数据
                            avg_volume_5d = float(df_past['volume'].mean())
                        else:
                             avg_volume_5d = 0.0

                    except Exception as e:
                        logger.warning(f"Failed to calculate avg_volume_5d for {code}: {e}")
                        # 降级到原逻辑
                        if len(df_hist) >= 6:
                             avg_volume_5d = float(df_hist.tail(6).head(5)['volume'].mean())
                        else:
                             avg_volume_5d = float(df_hist['volume'].mean())

                df_hist = df_hist.tail(self.history_days)
            
            # 3. Fetch News via Fallback
            news_str = await self._fetch_with_fallback('fetch_news', code=code, count=5, timeout=3)
            # news_str returns string separated by ;
            news_list = news_str.split("; ") if news_str else []
            if news_list:
                news_status = "fresh"

            return {
                "code": code,
                "name": name,
                "current_price": current_price,
                "pct_change": pct_change,
                "volume": volume,
                "turnover_rate": turnover_rate,
                "avg_volume_5d": avg_volume_5d,
                "history": df_hist,
                "news": news_list,
                "quote_status": quote_status,
                "history_status": history_status,
                "news_status": news_status,
            }
            
        except Exception as e:
            logger.error(f"Failed individual fetch for {code}: {e}")
            return {"code": code, "error": str(e)}

if __name__ == "__main__":
    # Smoke Test
    class MockConfig:
        config = {'portfolio': [{'code': '600519', 'name': '茅台'}]}
    
    start_t = datetime.now()
    collector = DataCollector()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(collector.collect_all(MockConfig.config['portfolio']))
    
    print(f"Time taken: {datetime.now() - start_t}")
    print(f"Market Breadth: {result['market_breadth']}")
    print(f"North Funds: {result['north_funds']}")
    if result['stocks']:
        print(f"Sample Stock Price: {result['stocks'][0]['current_price']}")
        print(f"Sample Hist Shape: {result['stocks'][0]['history'].shape}")
