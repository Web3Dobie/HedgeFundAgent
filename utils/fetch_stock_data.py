# utils/fetch_stock_data.py
# Updated for IG API + yfinance architecture - matches your actual implementation

import pandas as pd
import requests
import logging
import time
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv
from utils.config import FINNHUB_API_KEY
from utils.text_utils import TICKER_INFO
from data.ticker_blocks import CRYPTO

# Import your actual market data client (IG API + yfinance)
from utils.market_data import get_market_data_client

load_dotenv()
logger = logging.getLogger(__name__)

def fetch_last_price(symbol: str) -> dict:
    """
    Main price fetching function using IG API + yfinance fallback
    
    Args:
        symbol: Stock symbol (e.g., "AAPL", "^GSPC", "EURUSD=X")
        
    Returns:
        Dictionary with price data:
        {
            'price': float,
            'change_percent': float,
            'timestamp': str,
            'currency': str,
            'source': str
        }
    """
    try:
        # Use your market data client (IG API + yfinance fallback)
        client = get_market_data_client()
        
        # Handle crypto symbols with CoinGecko
        if symbol.lower() in [c.lower() for c in CRYPTO]:
            return _fetch_crypto_price(symbol)
        
        # Get price data via IG API (with yfinance fallback built-in)
        price_data = client.get_price(symbol)
        
        logger.debug(f"✅ Price fetched for {symbol}: ${price_data['price']} ({price_data['change_percent']:+.2f}%) via {price_data.get('source', 'unknown')}")
        return price_data
        
    except Exception as e:
        logger.error(f"❌ Price fetch failed for {symbol}: {e}")
        # Return error format for compatibility
        return {
            'symbol': symbol,
            'price': 0.0,
            'change_percent': 0.0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'currency': 'USD',
            'source': 'error',
            'error': str(e)
        }

def get_multiple_prices(symbols: Union[List[str], Dict[str, str]]) -> Dict[str, dict]:
    """
    Get prices for multiple symbols using IG API + yfinance fallback
    
    Args:
        symbols: List of symbols or dict of {label: symbol}
        
    Returns:
        Dictionary mapping symbols/labels to price data
    """
    try:
        client = get_market_data_client()
        
        if isinstance(symbols, dict):
            # Handle ticker blocks: {label: symbol}
            results = {}
            for label, symbol in symbols.items():
                try:
                    price_data = client.get_price(symbol)
                    results[label] = price_data
                    time.sleep(0.1)  # Small delay for rate limiting
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get price for {label} ({symbol}): {e}")
                    results[label] = {
                        'symbol': symbol,
                        'price': 0.0,
                        'change_percent': 0.0,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'currency': 'USD',
                        'source': 'error',
                        'error': str(e)
                    }
            return results
        
        else:
            # Handle symbol lists
            results = {}
            for symbol in symbols:
                try:
                    results[symbol] = fetch_last_price(symbol)
                    time.sleep(0.1)  # Small delay for rate limiting
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get price for {symbol}: {e}")
                    results[symbol] = {
                        'symbol': symbol,
                        'price': 0.0,
                        'change_percent': 0.0,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'currency': 'USD',
                        'source': 'error',
                        'error': str(e)
                    }
            return results
            
    except Exception as e:
        logger.error(f"❌ Multiple price fetch failed: {e}")
        # Return error data for all symbols
        if isinstance(symbols, dict):
            return {label: {'error': str(e), 'price': 0.0, 'change_percent': 0.0} for label in symbols.keys()}
        else:
            return {symbol: {'error': str(e), 'price': 0.0, 'change_percent': 0.0} for symbol in symbols}

def get_top_movers_from_constituents(limit: int = 5, include_extended: bool = False) -> dict:
    """
    Get top market movers using PURE YFINANCE (no IG API fallback needed)
    As you mentioned - yfinance for top gainers/losers with no Alpha Vantage fallback
    
    Args:
        limit: Number of top movers to return
        include_extended: Include pre/post market data (not implemented)
        
    Returns:
        dict with top_gainers, top_losers, and metadata
    """
    try:
        # Import constituents
        from data.index_constituents import sp100, nasdaq100
        
        # Combine and deduplicate
        all_symbols = list(set(sp100 + nasdaq100))
        logger.info(f"🔍 Scanning {len(all_symbols)} stocks using yfinance for top movers")
        
        # Use pure yfinance for movers (as per your specification)
        valid_results = []
        batch_size = 25  # Process in batches to avoid overwhelming yfinance
        
        for i in range(0, len(all_symbols), batch_size):
            batch = all_symbols[i:i + batch_size]
            logger.debug(f"📊 Processing batch {i//batch_size + 1}: {len(batch)} symbols")
            
            # Create yfinance tickers for the batch
            try:
                tickers = yf.Tickers(' '.join(batch))
                
                for symbol in batch:
                    try:
                        ticker = tickers.tickers[symbol]
                        
                        # Get current info
                        info = ticker.info
                        if not info:
                            continue
                            
                        # Get current price and change
                        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                        prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
                        
                        if current_price and prev_close and current_price > 0 and prev_close > 0:
                            change_percent = ((current_price - prev_close) / prev_close) * 100
                            
                            # Only include significant movers
                            if abs(change_percent) > 0.1:  # More than 0.1% change
                                valid_results.append({
                                    'symbol': symbol,
                                    'price': float(current_price),
                                    'change_percent': float(change_percent)
                                })
                                
                    except Exception as e:
                        logger.debug(f"⚠️ Skipping {symbol}: {e}")
                        continue
                
                # Brief pause between batches
                time.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"⚠️ Batch {i//batch_size + 1} failed: {e}")
                continue
        
        # Sort by change percentage
        sorted_by_change = sorted(valid_results, key=lambda x: x['change_percent'], reverse=True)
        
        # Split into gainers and losers
        gainers = [item for item in sorted_by_change if item['change_percent'] > 0][:limit]
        losers = [item for item in sorted_by_change if item['change_percent'] < 0][-limit:]
        
        result = {
            'top_gainers': gainers,
            'top_losers': losers,
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_scanned': len(all_symbols),
            'valid_results': len(valid_results)
        }
        
        # Extended hours placeholder (not implemented as you mentioned)
        if include_extended:
            logger.warning("📋 Extended hours scanning not implemented")
            result["pre_market"] = []
            result["post_market"] = []
        
        logger.info(f"✅ Found {len(gainers)} gainers, {len(losers)} losers from {len(valid_results)} valid results using yfinance")
        
        # Log top results
        if gainers:
            top_gainer = gainers[0]
            logger.info(f"🚀 Top Gainer: {top_gainer['symbol']} ({top_gainer['change_percent']:+.2f}%)")
        if losers:
            top_loser = losers[0]
            logger.info(f"📉 Top Loser: {top_loser['symbol']} ({top_loser['change_percent']:+.2f}%)")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Top movers scan failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'top_gainers': [],
            'top_losers': [],
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_scanned': 0,
            'valid_results': 0,
            'error': str(e)
        }

# utils/fetch_stock_data.py - CRYPTO SECTION FIX
# Replace the crypto functions in your fetch_stock_data.py with these:

def fetch_crypto_block() -> dict:
    """Fetch crypto prices using your existing fetch_token_data module"""
    try:
        from utils.fetch_token_data import get_top_tokens_data
        
        # Get crypto data from your working CoinGecko module
        crypto_data = get_top_tokens_data()
        
        # Format for briefing display
        crypto_results = {}
        
        # Map the results to the expected format
        ticker_to_name = {
            "BTC": "Bitcoin",
            "ETH": "Ethereum", 
            "SOL": "Solana",
            "XRP": "XRP",
            "ADA": "Cardano"
        }
        
        for item in crypto_data:
            ticker = item['ticker']
            price = item['price']
            change = item['change']
            
            name = ticker_to_name.get(ticker, ticker)
            crypto_results[name] = f"${price:,.2f} ({change:+.2f}%)"
        
        # Ensure we have the expected structure even if some tokens are missing
        expected_tokens = ["Bitcoin", "Ethereum", "Solana", "XRP", "Cardano"]
        for token in expected_tokens:
            if token not in crypto_results:
                crypto_results[token] = "N/A"
        
        logger.info(f"✅ Crypto block fetched via CoinGecko: {len([v for v in crypto_results.values() if v != 'N/A'])}/5 valid")
        return crypto_results
        
    except Exception as e:
        logger.error(f"❌ Crypto block fetch failed: {e}")
        return {
            "Bitcoin": "N/A",
            "Ethereum": "N/A", 
            "Solana": "N/A",
            "XRP": "N/A",
            "Cardano": "N/A"
        }

def _fetch_crypto_price(symbol: str) -> dict:
    """
    Fetch individual crypto price using CoinGecko (for compatibility)
    """
    try:
        # Map symbol to CoinGecko ID
        symbol_map = {
            'bitcoin': 'bitcoin',
            'btc': 'bitcoin',
            'btc-usd': 'bitcoin',
            'ethereum': 'ethereum',
            'eth': 'ethereum', 
            'eth-usd': 'ethereum',
            'solana': 'solana',
            'sol': 'solana',
            'sol-usd': 'solana',
            'xrp': 'ripple',
            'xrp-usd': 'ripple',
            'cardano': 'cardano',
            'ada': 'cardano',
            'ada-usd': 'cardano'
        }
        
        coin_id = symbol_map.get(symbol.lower(), symbol.lower())
        
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if coin_id in data:
            price_info = data[coin_id]
            return {
                "price": round(price_info['usd'], 4),
                "change_percent": round(price_info.get('usd_24h_change', 0), 2),
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "currency": "USD",
                "source": "CoinGecko"
            }
        else:
            raise Exception(f"Crypto {symbol} not found in CoinGecko")
            
    except Exception as e:
        logger.error(f"❌ CoinGecko failed for {symbol}: {e}")
        return {
            'symbol': symbol,
            'price': 0.0,
            'change_percent': 0.0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'currency': 'USD',
            'source': 'error',
            'error': str(e)
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
    if not FINNHUB_API_KEY:
        logger.warning("Finnhub API key not configured - no news available")
        return []
    
    try:
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
            for article in news if article.get("headline")
        ]
        
        logger.info(f"✅ Got {len(formatted_news)} news items from Finnhub for {ticker}")
        return formatted_news
        
    except Exception as e:
        logger.error(f"❌ Finnhub news failed for {ticker}: {e}")
        return []

def fetch_prior_close_yield(symbol: str) -> Optional[float]:
    """
    Get previous day's yield/price using market data client
    
    Args:
        symbol: Symbol to fetch
        
    Returns:
        Previous close price or None if unavailable
    """
    try:
        price_data = fetch_last_price(symbol)
        
        if 'error' not in price_data and price_data.get('price', 0) > 0:
            current_price = price_data['price']
            change_percent = price_data.get('change_percent', 0)
            
            if change_percent != 0:
                # Calculate prior close: current / (1 + change_percent/100)
                prior_close = current_price / (1 + change_percent / 100)
                return round(prior_close, 3)
        
        logger.warning(f"Cannot calculate prior close for {symbol} - insufficient data")
        return None
        
    except Exception as e:
        logger.warning(f"❌ Prior yield fetch failed for {symbol}: {e}")
        return None

def test_market_data_system():
    """Test your actual IG API + yfinance system"""
    print("🧪 Testing IG API + yfinance Market Data System")
    print("=" * 50)
    
    # Test market data client
    print("1️⃣ Testing market data client...")
    try:
        client = get_market_data_client()
        print(f"✅ Client initialized: {type(client).__name__}")
    except Exception as e:
        print(f"❌ Client initialization failed: {e}")
        return False
    
    # Test IG API symbols (typical ticker block symbols)
    print("\n2️⃣ Testing IG API symbols (ticker blocks)...")
    ig_test_symbols = {
        "S&P 500": "^GSPC",
        "EUR/USD": "EURUSD=X", 
        "Gold": "GC=F",
        "FTSE 100": "^FTSE"
    }
    
    for label, symbol in ig_test_symbols.items():
        try:
            start_time = time.time()
            data = fetch_last_price(symbol)
            elapsed = time.time() - start_time
            
            if 'error' not in data and data.get('price', 0) > 0:
                source = data.get('source', 'unknown')
                print(f"✅ {label:12} | ${data['price']:>8} | {data['change_percent']:>+6.2f}% | {source:10} | {elapsed:.2f}s")
            else:
                error_msg = data.get('error', 'Unknown error')
                print(f"❌ {label:12} | ERROR: {error_msg}")
        except Exception as e:
            print(f"❌ {label:12} | EXCEPTION: {e}")
    
    # Test yfinance for individual stocks
    print("\n3️⃣ Testing yfinance for individual stocks...")
    yf_test_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
    
    for symbol in yf_test_symbols:
        try:
            start_time = time.time()
            data = fetch_last_price(symbol)
            elapsed = time.time() - start_time
            
            if 'error' not in data and data.get('price', 0) > 0:
                source = data.get('source', 'unknown')
                print(f"✅ {symbol:12} | ${data['price']:>8} | {data['change_percent']:>+6.2f}% | {source:10} | {elapsed:.2f}s")
            else:
                error_msg = data.get('error', 'Unknown error')
                print(f"❌ {symbol:12} | ERROR: {error_msg}")
        except Exception as e:
            print(f"❌ {symbol:12} | EXCEPTION: {e}")
    
    # Test top movers (pure yfinance)
    print("\n4️⃣ Testing top movers (pure yfinance)...")
    try:
        start_time = time.time()
        movers = get_top_movers_from_constituents(limit=3)
        elapsed = time.time() - start_time
        
        if 'error' not in movers:
            print(f"✅ Movers scan completed ({elapsed:.2f}s)")
            print(f"   Scanned: {movers['total_scanned']} symbols")
            print(f"   Valid: {movers['valid_results']} results")
            print(f"   Gainers: {len(movers['top_gainers'])}")
            print(f"   Losers: {len(movers['top_losers'])}")
            
            if movers['top_gainers']:
                top_gainer = movers['top_gainers'][0]
                print(f"   🚀 Top Gainer: {top_gainer['symbol']} ({top_gainer['change_percent']:+.2f}%)")
            
            if movers['top_losers']:
                top_loser = movers['top_losers'][0]
                print(f"   📉 Top Loser: {top_loser['symbol']} ({top_loser['change_percent']:+.2f}%)")
        else:
            print(f"❌ Movers scan failed: {movers['error']}")
            
    except Exception as e:
        print(f"❌ Top movers test failed: {e}")
    
    # Test crypto
    print("\n5️⃣ Testing crypto (CoinGecko)...")
    crypto_symbols = ["bitcoin", "ethereum"]
    
    for symbol in crypto_symbols:
        try:
            data = _fetch_crypto_price(symbol)
            if 'error' not in data:
                print(f"✅ {symbol:12} | ${data['price']:>8} | {data['change_percent']:>+6.2f}% | CoinGecko")
            else:
                print(f"❌ {symbol:12} | ERROR: {data['error']}")
        except Exception as e:
            print(f"❌ {symbol:12} | EXCEPTION: {e}")
    
    print(f"\n{'='*50}")
    print("✅ IG API + yfinance system test completed")
    return True

# Backward compatibility aliases
get_price_data = fetch_last_price
test_rest_api_integration = test_market_data_system

if __name__ == "__main__":
    test_market_data_system()