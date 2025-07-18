# utils/market_data.py
"""
Updated Market Data Client - Using New Working IB Gateway
Clean, simple, uses the new official IBAPI client
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from .ib_gateway_client import get_ib_manager, PriceData, IBGatewayManager
from .fetch_token_data import get_top_tokens_data

logger = logging.getLogger(__name__)

class MarketDataError(Exception):
    """Base exception for market data errors"""
    pass

class IBConnectionError(MarketDataError):
    """IB Gateway connection errors"""
    pass

class DataUnavailableError(MarketDataError):
    """Data not available errors"""
    pass

class MarketDataClient:
    """
    Updated client using the new working IB Gateway with official IBAPI
    """
    
    def __init__(self):
        self.ib_manager = get_ib_manager()
        
    def get_price(self, symbol: str) -> Dict[str, Union[float, str]]:
        """
        Get price data for a single symbol using new IB Gateway client.
        
        Returns:
            dict: {"price": float, "change_percent": float, "timestamp": str}
        """
        try:
            price_data = self.ib_manager.get_price_data(symbol)
            return {
                "price": price_data.price,
                "change_percent": price_data.change_percent,
                "timestamp": price_data.timestamp
            }
        except Exception as e:
            logger.warning(f"IB Gateway failed for {symbol}: {e}")
            raise DataUnavailableError(f"IB Gateway data unavailable for {symbol}: {e}")
    
    def get_multiple_prices(self, symbols: Union[Dict[str, str], List[str]]) -> Dict[str, str]:
        """
        Get prices for multiple symbols using new IB Gateway client.
        
        Args:
            symbols: Dict {label: symbol} or List [symbol1, symbol2, ...]
            
        Returns:
            dict: {label: "price (±change%)" or "Weekend" or "N/A"} formatted for display
        """
        if isinstance(symbols, list):
            symbols = {sym: sym for sym in symbols}
        
        results = {}
        
        # Check for weekend first (quick check)
        if self._is_weekend():
            return {label: "Weekend" for label in symbols}
        
        # Process through new IB Gateway
        try:
            symbol_list = list(symbols.values())
            ib_results = self.ib_manager.get_multiple_prices(symbol_list)
            
            for label, symbol in symbols.items():
                if symbol in ib_results:
                    price_data = ib_results[symbol]
                    results[label] = self._format_price_display(
                        price_data.price, 
                        price_data.change_percent, 
                        symbol
                    )
                else:
                    results[label] = "N/A"
            
            return results
            
        except Exception as e:
            logger.warning(f"Batch IB request failed: {e}")
            
            # Fallback to individual calls
            for label, symbol in symbols.items():
                try:
                    price_data = self.get_price(symbol)
                    results[label] = self._format_price_display(
                        price_data["price"], 
                        price_data["change_percent"], 
                        symbol
                    )
                except Exception as e:
                    logger.warning(f"Failed to get {symbol}: {e}")
                    results[label] = "N/A"
        
        return results
    
    def get_crypto_prices(self) -> Dict[str, str]:
        """
        Get crypto prices formatted for display.
        
        Returns:
            dict: {ticker: "price (±change%)"}
        """
        try:
            tokens = get_top_tokens_data()
            return {
                token["ticker"]: f"{token['price']:.2f} ({token['change']:+.2f}%)"
                for token in tokens[:6]
            }
        except Exception as e:
            logger.error(f"Crypto prices failed: {e}")
            return {}
    
    def get_news(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Get news for a ticker (placeholder - would need historical data access)
        
        Returns:
            list: [{"headline": str, "source": str, "date": str, "url": str}, ...]
        """
        try:
            # News functionality would require historical data access
            # For now, return empty list
            logger.warning(f"News not available without historical data access")
            return []
        except Exception as e:
            logger.error(f"News failed for {ticker}: {e}")
            return []
    
    def get_top_movers(self, limit: int = 5, include_extended: bool = False) -> Dict[str, List]:
        """
        Get top market movers using new IB Gateway client.
        
        Returns:
            dict: {
                "top_gainers": [(symbol, price, change_pct), ...],
                "top_losers": [(symbol, price, change_pct), ...],
                "pre_market": [...],  # if include_extended
                "post_market": [...]  # if include_extended
            }
        """
        from .text_utils import TICKER_INFO
        symbols = list(TICKER_INFO.keys())[:20]  # Limit for performance
        
        try:
            # Use batch pricing with new client
            price_results = self.ib_manager.get_multiple_prices(symbols)
            
            # Convert to tuple format
            data = [
                (symbol, price_data.price, price_data.change_percent)
                for symbol, price_data in price_results.items()
                if price_data.change_percent != 0  # Filter out zero changes
            ]
            
            movers = {
                "top_gainers": sorted(data, key=lambda x: -x[2])[:limit],
                "top_losers": sorted(data, key=lambda x: x[2])[:limit]
            }
            
            if include_extended:
                # Extended hours not available with current setup
                logger.warning("Extended hours data not available with current setup")
                movers["pre_market"] = []
                movers["post_market"] = []
            
            return movers
            
        except Exception as e:
            logger.error(f"Error getting top movers: {e}")
            return {"top_gainers": [], "top_losers": [], "pre_market": [], "post_market": []}
    
    def _format_price_display(self, price: float, change_pct: float, symbol: str) -> str:
        """Format price for display based on asset type"""
        # Handle FX pairs (4 decimal places)
        if 'CASH' in symbol or symbol.endswith("=X"):
            price_fmt = f"{price:.4f}"
        else:
            price_fmt = f"{price:.2f}"
        
        return f"{price_fmt} ({change_pct:+.2f}%)"
    
    def _is_weekend(self) -> bool:
        """Check if it's weekend"""
        return datetime.utcnow().weekday() >= 5
    
    def health_check(self) -> Dict[str, bool]:
        """Check health of IB Gateway"""
        health = {}
        
        # IB Gateway
        try:
            with self.ib_manager.get_client() as ib:
                health['ib_gateway'] = ib.isConnected()
        except:
            health['ib_gateway'] = False
        
        return health
    
    def test_live_connection(self) -> Dict[str, any]:
        """Test live connection with sample symbols"""
        test_results = {
            "connection_status": False,
            "test_symbols": {},
            "errors": []
        }
        
        try:
            # Test connection
            health = self.health_check()
            test_results["connection_status"] = health.get('ib_gateway', False)
            
            if test_results["connection_status"]:
                # Test a few common symbols
                test_symbols = ["AAPL", "ES-FUT-USD", "MSFT"]
                
                for symbol in test_symbols:
                    try:
                        start_time = time.time()
                        price_data = self.get_price(symbol)
                        elapsed = time.time() - start_time
                        
                        test_results["test_symbols"][symbol] = {
                            "price": price_data["price"],
                            "change_percent": price_data["change_percent"],
                            "response_time": round(elapsed, 2)
                        }
                    except Exception as e:
                        test_results["errors"].append(f"{symbol}: {str(e)}")
            else:
                test_results["errors"].append("IB Gateway connection failed")
                
        except Exception as e:
            test_results["errors"].append(f"Connection test failed: {str(e)}")
        
        return test_results

# Global instance for easy access
_market_client = None

def get_market_client() -> MarketDataClient:
    """Get or create global market client instance"""
    global _market_client
    if _market_client is None:
        _market_client = MarketDataClient()
    return _market_client

# Clean, descriptive function names (keeping API compatibility)
def fetch_last_price(symbol: str) -> dict:
    """Fetch latest price data using new IB Gateway client"""
    return get_market_client().get_price(symbol)

def get_price_data(symbol: str) -> dict:
    """Modern alias for price fetching"""
    return get_market_client().get_price(symbol)

def get_top_movers_from_constituents(limit=5, include_extended=False):
    """Get top market movers"""
    return get_market_client().get_top_movers(limit, include_extended)

def fetch_stock_news(ticker: str, start_date: str, end_date: str):
    """Fetch news for a ticker (placeholder)"""
    return get_market_client().get_news(ticker, start_date, end_date)

def test_live_market_data():
    """Test function for live market data"""
    client = get_market_client()
    return client.test_live_connection()