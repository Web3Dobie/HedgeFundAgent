# utils/market_data.py
"""
Updated Market Data Client - IG Index + yfinance fallback
Replaces the existing market_data.py with enhanced capabilities
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

# Import the new IG client
from .ig_market_data import get_ig_client, IGMarketDataClient, IGMarketDataError
from .fetch_token_data import get_top_tokens_data

logger = logging.getLogger(__name__)

class MarketDataError(Exception):
    """Base exception for market data errors"""
    pass

class MarketDataClient:
    """
    Unified market data client with IG Index primary + yfinance fallback
    Drop-in replacement for existing MarketDataClient
    """
    
    def __init__(self, use_ig_demo: bool = True):
        """
        Initialize with IG Index client
        
        Args:
            use_ig_demo: Use IG demo account for testing
        """
        self.ig_client = get_ig_client(use_demo=use_ig_demo)
        logger.info("✅ MarketDataClient initialized with IG Index + yfinance fallback")
        
    def get_price(self, symbol: str) -> Dict[str, Union[float, str]]:
        """
        Get price data for a single symbol
        
        Args:
            symbol: Symbol in yfinance format (e.g., 'AAPL', '^GSPC', 'EURUSD=X')
            
        Returns:
            dict: {"price": float, "change_percent": float, "timestamp": str, "source": str}
        """
        try:
            return self.ig_client.get_price(symbol)
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            raise MarketDataError(f"Price data unavailable for {symbol}: {e}")
    
    def get_multiple_prices(self, symbols: Union[Dict[str, str], List[str]]) -> Dict[str, str]:
        """
        Get prices for multiple symbols - compatible with existing interface
        
        Args:
            symbols: Dict {name: symbol} or List [symbol1, symbol2, ...]
            
        Returns:
            dict: {symbol: "price (±change%)", ...} or {name: "price (±change%)", ...}
        """
        try:
            # Handle both dict and list inputs for backward compatibility
            if isinstance(symbols, dict):
                symbol_list = list(symbols.values())
                name_mapping = symbols
            else:
                symbol_list = symbols
                name_mapping = {sym: sym for sym in symbols}
            
            # Get raw price data
            price_data = self.ig_client.get_multiple_prices(symbol_list)
            
            # Format for existing interface: "123.45 (+2.5%)"
            formatted_results = {}
            
            for name, symbol in name_mapping.items():
                if symbol in price_data:
                    data = price_data[symbol]
                    price = data.get('price', 0)
                    change_pct = data.get('change_percent', 0)
                    
                    # Use 4 decimal places for FX pairs, 2 for everything else
                    if "=X" in symbol:  # FX pairs end with =X (e.g., EURUSD=X)
                        formatted_results[name] = f"{price:.4f} ({change_pct:+.2f}%)"
                    else:
                        formatted_results[name] = f"{price:.2f} ({change_pct:+.2f}%)"
                else:
                    formatted_results[name] = "N/A"
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Multiple price fetch failed: {e}")
            return {name: "Error" for name in (symbols.keys() if isinstance(symbols, dict) else symbols)}

    def get_raw_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get raw price data (not formatted) - useful for internal processing
        
        Returns:
            dict: {symbol: {"price": float, "change_percent": float, ...}, ...}
        """
        return self.ig_client.get_multiple_prices(symbols)
    
    def get_crypto_prices(self) -> Dict[str, str]:
        """
        Get crypto prices - uses existing crypto data source
        
        Returns:
            dict: {ticker: "price (±change%)", ...}
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
    
    def get_forex_prices(self) -> Dict[str, str]:
        """
        Get major forex pairs using IG Index
        
        Returns:
            dict: {pair: "price (±change%)", ...}
        """
        forex_symbols = {
            "EUR/USD": "EURUSD=X",
            "GBP/USD": "GBPUSD=X", 
            "USD/JPY": "USDJPY=X",
            "USD/CHF": "USDCHF=X",
            "AUD/USD": "AUDUSD=X",
            "USD/CAD": "USDCAD=X"
        }
        
        return self.get_multiple_prices(forex_symbols)
    
    def get_indices_prices(self) -> Dict[str, str]:
        """
        Get major market indices using IG Index
        
        Returns:
            dict: {index: "price (±change%)", ...}
        """
        indices_symbols = {
            "S&P 500": "^GSPC",
            "Dow Jones": "^DJI",
            "NASDAQ": "^IXIC",
            "FTSE 100": "^FTSE",
            "DAX": "^GDAXI",
            "Nikkei 225": "^N225",
            "Hang Seng": "^HSI"
        }
        
        return self.get_multiple_prices(indices_symbols)
    
    def get_commodities_prices(self) -> Dict[str, str]:
        """
        Get commodity prices using IG Index
        
        Returns:
            dict: {commodity: "price (±change%)", ...}
        """
        commodities_symbols = {
            "Gold": "GC=F",
            "Silver": "SI=F", 
            "Crude Oil": "CL=F",
            "Natural Gas": "NG=F",
            "Copper": "HG=F"
        }
        
        return self.get_multiple_prices(commodities_symbols)
    
    def get_news(self, ticker: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Get news for a ticker (placeholder - IG doesn't provide news API)
        
        Returns:
            list: [{"headline": str, "source": str, "date": str, "url": str}, ...]
        """
        logger.warning("News functionality not available with IG Index API")
        return []
    
    def get_top_movers(self, limit: int = 5, include_extended: bool = False) -> Dict[str, List]:
        """
        Get top market movers using IG Index for major symbols
        
        Returns:
            dict: {
                "top_gainers": [(symbol, price, change_pct), ...],
                "top_losers": [(symbol, price, change_pct), ...],
                "pre_market": [...],  # if include_extended
                "post_market": [...]  # if include_extended
            }
        """
        # Major symbols to check for movers
        major_symbols = [
            "^GSPC", "^DJI", "^IXIC", "^FTSE", "^GDAXI", "^N225",  # Indices
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA",      # Major stocks
            "EURUSD=X", "GBPUSD=X", "USDJPY=X",                   # Forex
            "GC=F", "CL=F", "BTC-USD"                             # Commodities/Crypto
        ]
        
        try:
            price_results = self.ig_client.get_multiple_prices(major_symbols)
            
            # Convert to tuple format and filter valid data
            data = []
            for symbol, price_data in price_results.items():
                if 'error' not in price_data and price_data.get('change_percent', 0) != 0:
                    data.append((
                        symbol,
                        price_data['price'], 
                        price_data['change_percent']
                    ))
            
            movers = {
                "top_gainers": sorted(data, key=lambda x: -x[2])[:limit],
                "top_losers": sorted(data, key=lambda x: x[2])[:limit]
            }
            
            if include_extended:
                # Extended hours not available with current setup
                logger.warning("Extended hours data not available")
                movers["pre_market"] = []
                movers["post_market"] = []
            
            return movers
            
        except Exception as e:
            logger.error(f"Error getting top movers: {e}")
            return {"top_gainers": [], "top_losers": [], "pre_market": [], "post_market": []}
    
    def get_historical_data(self, symbol: str, period: str = "1y") -> Optional[object]:
        """
        Get historical data for a symbol
        
        Args:
            symbol: Symbol to fetch
            period: Period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            
        Returns:
            DataFrame with OHLCV data
        """
        return self.ig_client.get_historical_data(symbol, period)
    
    def get_market_status(self) -> Dict[str, str]:
        """Get current market status"""
        return self.ig_client.get_market_status()
    
    def _format_price_display(self, price: float, change_pct: float, symbol: str) -> str:
        """Format price for display - maintains existing interface"""
        return f"{price:.2f} ({change_pct:+.2f}%)"
    
    def health_check(self) -> Dict[str, Union[bool, str]]:
        """
        Perform health check on data sources
        
        Returns:
            dict: Status of different data sources
        """
        health = {
            "ig_index": False,
            "yfinance": False,
            "crypto_data": False,
            "overall": False
        }
        
        # Test IG Index
        try:
            test_data = self.ig_client.get_price("^GSPC")
            health["ig_index"] = test_data.get('source') == 'IG Index'
        except:
            pass
        
        # Test yfinance fallback
        try:
            test_data = self.ig_client._get_yfinance_price("AAPL")
            health["yfinance"] = test_data.get('source') == 'yfinance'
        except:
            pass
        
        # Test crypto data
        try:
            crypto_data = self.get_crypto_prices()
            health["crypto_data"] = bool(crypto_data)
        except:
            pass
        
        # Overall health
        health["overall"] = health["ig_index"] or health["yfinance"]
        
        return health
    
    def disconnect(self):
        """Clean disconnect from all data sources"""
        try:
            self.ig_client.disconnect()
            logger.info("MarketDataClient disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting MarketDataClient: {e}")

# Global instance for backward compatibility
_market_data_client = None

def get_market_data_client(use_ig_demo: bool = True) -> MarketDataClient:
    """Get or create global market data client instance"""
    global _market_data_client
    if _market_data_client is None:
        _market_data_client = MarketDataClient(use_ig_demo=use_ig_demo)
    return _market_data_client

# Backward compatibility functions for existing code
def get_rest_client():
    """Backward compatibility - returns new MarketDataClient"""
    return get_market_data_client()

# Legacy function mappings for smooth migration
def fetch_last_price(symbol: str) -> dict:
    """Legacy function for backward compatibility"""
    client = get_market_data_client()
    return client.get_price(symbol)

def get_multiple_prices(symbols: List[str]) -> Dict[str, dict]:
    """Legacy function for backward compatibility"""
    client = get_market_data_client()
    return client.get_raw_prices(symbols)