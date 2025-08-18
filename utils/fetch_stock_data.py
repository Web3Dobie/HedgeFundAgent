# utils/fetch_stock_data.py
# Updated for C# REST API integration - Drop-in replacement

import pandas as pd
import requests
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from utils.config import FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY
from utils.text_utils import TICKER_INFO
from data.ticker_blocks import CRYPTO

# Import the new REST API client
from utils.csharp_rest_client import get_rest_client, RestApiMarketDataClient

load_dotenv()
logger = logging.getLogger(__name__)

# Global REST client instance
_rest_client = None

def get_market_data_client() -> RestApiMarketDataClient:
    """Get or create REST API market data client"""
    global _rest_client
    if _rest_client is None:
        _rest_client = get_rest_client()
        logger.info("✅ Initialized REST API market data client")
    return _rest_client

def fetch_last_price(symbol: str) -> dict:
    """
    Main price fetching function - now uses C# REST API with fallback
    Returns: {"price": float, "change_percent": float, "timestamp": str}
    
    Args:
        symbol: Stock symbol (e.g., "AAPL", "ES-FUT-USD", "bitcoin")
        
    Returns:
        Dictionary with price data:
        {
            'price': float,
            'change_percent': float,
            'timestamp': str,
            'currency': str,
            'volume': Optional[int]
        }
    """
    
    # Try REST API first (replaces old IB Gateway direct connection)
    try:
        client = get_market_data_client()
        
        # Handle crypto symbols
        if symbol.lower() in [c.lower() for c in CRYPTO]:
            return _fetch_crypto_price(symbol)
        
        # Get price data via REST API
        price_data = client.get_price(symbol)
        
        logger.debug(f"✅ Price fetched via REST API for {symbol}: ${price_data['price']} ({price_data['change_percent']:+.2f}%)")
        return price_data
        
    except Exception as e:
        logger.warning(f"⚠️ REST API failed for {symbol}: {e}")
        # Fall back to external APIs
        return _fetch_price_fallback(symbol)

def _fetch_crypto_price(symbol: str) -> dict:
    """Fetch crypto prices via CoinGecko API"""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': symbol.lower(),
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if symbol.lower() in data:
            price_info = data[symbol.lower()]
            return {
                "price": round(price_info['usd'], 4),
                "change_percent": round(price_info['usd_24h_change'], 2),
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "currency": "USD",
                "volume": None
            }
    except Exception as e:
        logger.error(f"CoinGecko failed for {symbol}: {e}")
        raise

def _fetch_price_fallback(symbol: str) -> dict:
    """Fallback price fetching using external APIs"""
    
    # Crypto via CoinGecko
    if symbol.lower() in [c.lower() for c in CRYPTO]:
        return _fetch_crypto_price(symbol)
    
    # Traditional assets via Alpha Vantage
    try:
        clean_symbol = symbol.split('-')[0]  # Remove IB suffixes
        
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': clean_symbol,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if 'Global Quote' in data:
            quote = data['Global Quote']
            price = float(quote['05. price'])
            change_pct = float(quote['10. change percent'].rstrip('%'))
            
            return {
                "price": round(price, 2),
                "change_percent": round(change_pct, 2),
                "timestamp": quote['07. latest trading day'],
                "currency": "USD",
                "volume": None
            }
            
    except Exception as e:
        logger.error(f"Alpha Vantage failed for {symbol}: {e}")
    
    # Return error data for compatibility
    return {
        'symbol': symbol,
        'price': 0.0,
        'change_percent': 0.0,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'currency': 'USD',
        'volume': None,
        'error': f"All data sources failed for {symbol}"
    }

def get_multiple_prices(symbols: List[str]) -> Dict[str, dict]:
    """
    Get prices for multiple symbols using C# REST API
    
    Args:
        symbols: List of symbols to fetch
        
    Returns:
        Dictionary mapping symbols to price data
    """
    try:
        client = get_market_data_client()
        return client.get_multiple_prices(symbols)
        
    except Exception as e:
        logger.error(f"❌ Multiple price fetch failed: {e}")
        # Return fallback data for all symbols
        fallback_data = {}
        for symbol in symbols:
            try:
                fallback_data[symbol] = fetch_last_price(symbol)
            except:
                fallback_data[symbol] = {
                    'symbol': symbol,
                    'price': 0.0,
                    'change_percent': 0.0,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'currency': 'USD',
                    'volume': None,
                    'error': str(e)
                }
        return fallback_data

def get_top_movers_from_constituents(limit: int = 5, include_extended: bool = False) -> dict:
    """
    Get top market movers using Yahoo Finance's pre-computed lists
    
    Args:
        limit: Number of top movers to return (default 5)
        include_extended: Include pre/post market data (not supported)
        
    Returns:
        dict: {
            'top_gainers': [{'symbol': str, 'price': float, 'change_percent': float}, ...],
            'top_losers': [{'symbol': str, 'price': float, 'change_percent': float}, ...],
            'pre_market': [],  # Empty - not supported
            'post_market': [], # Empty - not supported
            'scan_time': str,
            'total_scanned': int,
            'valid_results': int
        }
    """
    try:
        # Import yahoo_fin modules
        from yahoo_fin.stock_info import get_day_gainers, get_day_losers
        
        logger.info(f"📈 Fetching top {limit} movers from Yahoo Finance...")
        
        # Get Yahoo's pre-computed top movers
        gainers_df = get_day_gainers()
        losers_df = get_day_losers()
        
        logger.info(f"📊 Yahoo returned {len(gainers_df)} gainers, {len(losers_df)} losers")
        
        # Convert gainers to our expected format
        gainers = []
        for _, row in gainers_df.head(limit).iterrows():
            try:
                # Handle price field which might have commas
                price_str = str(row['Price (Intraday)']).replace(',', '')
                price = float(price_str)
                
                gainers.append({
                    'symbol': row['Symbol'],
                    'price': price,
                    'change_percent': row['% Change']
                })
            except (ValueError, KeyError) as e:
                logger.warning(f"⚠️ Skipping gainer {row.get('Symbol', 'UNKNOWN')}: {e}")
                continue
        
        # Convert losers to our expected format
        losers = []
        for _, row in losers_df.head(limit).iterrows():
            try:
                # Handle price field which might have commas
                price_str = str(row['Price (Intraday)']).replace(',', '')
                price = float(price_str)
                
                losers.append({
                    'symbol': row['Symbol'],
                    'price': price,
                    'change_percent': row['% Change']
                })
            except (ValueError, KeyError) as e:
                logger.warning(f"⚠️ Skipping loser {row.get('Symbol', 'UNKNOWN')}: {e}")
                continue
        
        result = {
            'top_gainers': gainers,
            'top_losers': losers,
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_scanned': len(gainers_df) + len(losers_df),
            'valid_results': len(gainers) + len(losers)
        }
        
        # Extended hours placeholder (Yahoo doesn't provide this)
        if include_extended:
            logger.warning("📋 Extended hours data not available via Yahoo Finance API")
            result["pre_market"] = []
            result["post_market"] = []
        
        logger.info(f"✅ Successfully processed {len(gainers)} gainers, {len(losers)} losers")
        return result
        
    except ImportError as e:
        logger.error(f"❌ yahoo_fin not installed: {e}")
        logger.info("💡 Install with: pip install yahoo_fin")
        return _fallback_movers_response(str(e))
        
    except Exception as e:
        logger.error(f"❌ Yahoo Finance movers failed: {e}")
        return _fallback_movers_response(str(e))

def _fallback_movers_response(error_msg: str) -> dict:
    """Return empty movers response for error cases"""
    return {
        'top_gainers': [],
        'top_losers': [],
        'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_scanned': 0,
        'valid_results': 0,
        'error': error_msg
    }

def fetch_stock_news(ticker: str, start_date: str, end_date: str) -> List[dict]:
    """
    Fetch news for a ticker using Finnhub API
    
    Args:
        ticker: Stock ticker
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        List of news articles
    """
    try:
        # Convert dates to Unix timestamps for Finnhub
        start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
        end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp())
        
        url = (
            f"https://finnhub.io/api/v1/company-news?"
            f"symbol={ticker}&from={start_date}&to={end_date}&token={FINNHUB_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        news = response.json()

        formatted_news = [
            {
                "headline": article.get("headline"),
                "source": article.get("source"),
                "date": article.get("datetime"),
                "url": article.get("url"),
            }
            for article in news
        ]
        
        logger.info(f"✅ Got {len(formatted_news)} news items from Finnhub for {ticker}")
        return formatted_news
        
    except Exception as e:
        logger.error(f"Finnhub news failed for {ticker}: {e}")
        return []

def fetch_prior_close_yield(symbol: str) -> Optional[float]:
    """
    Get previous day's yield/price using REST API or fallback calculation
    
    Args:
        symbol: Symbol to fetch
        
    Returns:
        Previous close price or None if unavailable
    """
    try:
        # Try to get current data via REST API
        client = get_market_data_client()
        data = client.get_price(symbol)
        
        # If we have current price and change percent, calculate prior close
        current_price = data.get('price', 0)
        change_percent = data.get('change_percent', 0)
        
        if current_price > 0 and change_percent != 0:
            # Calculate prior close: current / (1 + change_percent/100)
            prior_close = current_price / (1 + change_percent / 100)
            return round(prior_close, 3)
        
        # If change_percent is 0, we can't calculate reliably
        logger.warning(f"Cannot calculate prior close for {symbol} - no change data")
        return None
        
    except Exception as e:
        logger.warning(f"Prior yield fetch failed for {symbol}: {e}")
        return None

def test_rest_api_integration():
    """Test the REST API integration"""
    print("🧪 Testing REST API Integration")
    print("=" * 40)
    
    # Test connection
    try:
        client = get_market_data_client()
        test_results = client.test_connection()
        
        print(f"API Healthy: {'✅' if test_results['api_healthy'] else '❌'}")
        print(f"IB Connected: {'✅' if test_results['ib_connected'] else '❌'}")
        
        if test_results['errors']:
            print(f"Errors: {test_results['errors']}")
            return
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return
    
    # Test individual symbols
    test_symbols = ["AAPL", "MSFT", "ES", "bitcoin"]
    
    print(f"\n📊 Testing individual symbols:")
    for symbol in test_symbols:
        try:
            start_time = time.time()
            data = fetch_last_price(symbol)
            elapsed = time.time() - start_time
            
            if 'error' not in data:
                print(f"✅ {symbol:15} | ${data['price']:>8} | {data['change_percent']:>+6.2f}% | {elapsed:.2f}s")
            else:
                print(f"❌ {symbol:15} | ERROR: {data['error']}")
        except Exception as e:
            print(f"❌ {symbol:15} | EXCEPTION: {e}")
    
    # Test batch request
    print(f"\n🔄 Testing batch request:")
    try:
        batch_symbols = ["AAPL", "MSFT", "SPY", "ES"]
        start_time = time.time()
        batch_results = get_multiple_prices(batch_symbols)
        elapsed = time.time() - start_time
        
        print(f"📦 Batch results ({elapsed:.2f}s):")
        for symbol, data in batch_results.items():
            if 'error' not in data:
                print(f"   {symbol}: ${data['price']} ({data['change_percent']:+.2f}%)")
            else:
                print(f"   {symbol}: ERROR - {data['error']}")
                
    except Exception as e:
        print(f"❌ Batch request failed: {e}")
    
    # Test top movers
    print(f"\n🚀 Testing top movers:")
    try:
        start_time = time.time()
        movers = get_top_movers_from_constituents(limit=3)
        elapsed = time.time() - start_time
        
        if 'error' not in movers:
            print(f"✅ Top movers scan completed ({elapsed:.2f}s)")
            print(f"   Scanned: {movers['total_scanned']} symbols")
            print(f"   Valid: {movers['valid_results']} results")
            print(f"   Gainers: {len(movers['top_gainers'])}")
            print(f"   Losers: {len(movers['top_losers'])}")
            
            if movers['top_gainers']:
                top_gainer = movers['top_gainers'][0]
                print(f"   Top Gainer: {top_gainer['symbol']} ({top_gainer['change_percent']:+.2f}%)")
            
            if movers['top_losers']:
                top_loser = movers['top_losers'][0]
                print(f"   Top Loser: {top_loser['symbol']} ({top_loser['change_percent']:+.2f}%)")
        else:
            print(f"❌ Top movers failed: {movers['error']}")
            
    except Exception as e:
        print(f"❌ Top movers scan failed: {e}")

# Backward compatibility aliases
get_price_data = fetch_last_price  # Alias for compatibility
test_simple_integration = test_rest_api_integration  # Updated test name

if __name__ == "__main__":
    test_rest_api_integration()