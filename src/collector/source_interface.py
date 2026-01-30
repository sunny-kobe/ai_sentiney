from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pandas as pd

class DataSource(ABC):
    """Abstract base class for market data sources."""
    
    @abstractmethod
    def get_source_name(self) -> str:
        """Return the name of the data source (e.g., 'Efinance', 'AkShare')."""
        pass

    @abstractmethod
    def fetch_market_breadth(self) -> str:
        """Fetch market breadth summary (Up/Down counts, etc)."""
        pass
    
    @abstractmethod
    def fetch_prices(self, code: str, period: str = 'daily', count: int = 20) -> Optional[pd.DataFrame]:
        """
        Fetch historical price data.
        Returns DataFrame with columns: ['date', 'open', 'high', 'low', 'close', 'volume', 'pct_chg']
        """
        pass
        
    @abstractmethod
    def fetch_news(self, code: str, count: int = 5) -> str:
        """Fetch latest news for the specific stock code."""
        pass

    @abstractmethod
    def fetch_spot_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch real-time spot data for all stocks.
        Returns DataFrame with columns: ['code', 'name', 'current_price', 'pct_change']
        """
        pass

    def fetch_single_quote(self, code: str) -> Optional[Dict]:
        """
        Fetch real-time quote for a single stock.
        Returns Dict with keys: ['code', 'name', 'current_price', 'pct_change']
        Optional to implement (default returns None).
        """
        return None
