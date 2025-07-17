# utils/fetch_stock_data.py
# Simplified IB Gateway integration - only what you actually use

import pandas as pd
import requests
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from ib_insync import *

from dotenv import load_dotenv
from utils.config import FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY
from utils.text_utils import TICKER_INFO
from data.ticker_blocks import CRYPTO

load_dotenv()
logger = logging.getLogger(__name__)

# Simple global IB client
_ib = None

def get_ib_connection():
    """Get or create IB connection"""
    global _ib
    if _ib is None or not _ib.isConnected():
        try:
            _ib = IB()
            _ib.connect('135.225.86.140', 7497, 1)
            _ib.reqMarketDataType(3)  # Delayed data
            logger.info("✅ Connected to IB Gateway")
        except Exception as e:
            logger.warning(f"⚠️ IB Gateway unavailable: {e}")
            _ib = None
    return _ib

def parse_ib_symbol(symbol: str):
    """Parse symbol to IB contract - simplified version"""
    if '-' not in symbol:
        return Stock(symbol, 'SMART', 'USD')
    
    parts = symbol.split('-')
    if len(parts) != 3:
        return Stock(symbol, 'SMART', 'USD')
    
    sym, contract_type, currency = parts
    
    if contract_type == 'FUT':
        exchange_map = {
            'ES': 'CME', 'YM': 'CBOT', 'NQ': 'CME', 'RTY': 'CME',
            'GC': 'COMEX', 'SI': 'COMEX', 'CL': 'NYMEX', 
            'NG': 'NYMEX', 'HG': 'COMEX', 'ZN': 'CBOT'
        }
        exchange = exchange_map.get(sym, 'CME')
        expiry = '20250321'  # Update quarterly
        return Future(sym, expiry, exchange)
        
    elif contract_type == 'CASH':
        return Forex(sym)
        
    elif contract_type == 'IND':
        exchange_map = {
            'N225': 'OSE.JPN', 'HSI': 'HKFE', 'KOSPI': 'KRX',
            'SX5E': 'DTB', 'UKX': 'LIFFE', 'DAX': 'DTB', 
            'CAC': 'MONEP', '300': 'SSE',
            'IRX': 'CBOE', 'FVX': 'CBOE', 'TNX': 'CBOE', 'TYX': 'CBOE'
        }
        exchange = exchange_map.get(sym, 'SMART')
        return Index(sym, exchange, currency)
    
    return Stock(sym, 'SMART', currency)

def fetch_last_price(symbol: str) -> dict:
    """
    Main price fetching function - IB Gateway with API fallback
    Returns: {"price": float, "change_percent": float, "timestamp": str}
    """
    
    # Try IB Gateway first
    ib = get_ib_connection()
    if ib:
        try:
            contract = parse_ib_symbol(symbol)
            
            # Get historical for change calculation
            hist = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='3 D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True
            )
            
            if len(hist) >= 2:
                # Get current price
                ticker = ib.reqMktData(contract)
                ib.sleep(3)
                
                current_price = ticker.marketPrice() or ticker.last or hist[-1].close
                prev_close = hist[-2].close
                
                if prev_close > 0:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    
                    # Format price
                    if 'CASH' in symbol:
                        formatted_price = round(float(current_price), 4)
                    else:
                        formatted_price = round(float(current_price), 2)
                    
                    return {
                        "price": formatted_price,
                        "change_percent": round(change_pct, 2),
                        "timestamp": hist[-1].date.strftime('%Y-%m-%d')
                    }
                    
        except Exception as e:
            logger.warning(f"IB failed for {symbol}: {e}")
    
    # Fallback to APIs
    return _fetch_price_fallback(symbol)

def _fetch_price_fallback(symbol: str) -> dict:
    """Fallback price fetching"""
    
    # Crypto via CoinGecko
    if symbol.lower() in CRYPTO:
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
                    "timestamp": datetime.now().strftime('%Y-%m-%d')
                }
        except Exception as e:
            logger.error(f"CoinGecko failed for {symbol}: {e}")
    
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
                "timestamp": quote['07. latest trading day']
            }
            
    except Exception as e:
        logger.error(f"Alpha Vantage failed for {symbol}: {e}")
    
    raise ConnectionError(f"All data sources failed for {symbol}")

def get_top_movers_from_constituents(limit=5, include_extended=False) -> dict:
    """
    Get top movers - simplified for your briefings
    """
    symbols = list(TICKER_INFO.keys())[:20]  # Limit for performance
    data = []
    
    for symbol in symbols:
        try:
            price_data = fetch_last_price(symbol)
            price = price_data["price"]
            change_pct = price_data["change_percent"]
            data.append((symbol, price, change_pct))
            time.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.warning(f"Failed to get {symbol}: {e}")
            continue

    movers = {
        "top_gainers": sorted(data, key=lambda x: -x[2])[:limit],
        "top_losers": sorted(data, key=lambda x: x[2])[:limit]
    }

    # Extended hours - placeholder (IB setup required)
    if include_extended:
        logger.warning("Extended hours not implemented")
        movers["pre_market"] = []
        movers["post_market"] = []

    return movers

def fetch_stock_news(ticker: str, start_date: str, end_date: str):
    """
    Fetch news - IB Gateway first, Finnhub fallback
    IB Gateway provides limited news but it's real-time
    """
    
    # Try IB Gateway news first
    ib = get_ib_connection()
    if ib:
        try:
            # Create contract for news request
            contract = parse_ib_symbol(ticker)
            
            # Request news headlines (IB provides limited historical news)
            news_providers = ib.reqNewsProviders()
            if news_providers:
                # Get news articles for the contract
                # Note: IB news is more limited than Finnhub
                news_articles = ib.reqHistoricalNews(
                    conId=contract.conId if hasattr(contract, 'conId') else 0,
                    providerCodes="BRFG+DJNL+BRFUPDN",  # Common IB news providers
                    startDateTime=start_date + " 00:00:00",
                    endDateTime=end_date + " 23:59:59",
                    totalResults=10
                )
                
                if news_articles:
                    formatted_news = []
                    for article in news_articles:
                        formatted_news.append({
                            "headline": article.headline,
                            "source": article.providerCode,
                            "date": article.time,
                            "url": ""  # IB doesn't always provide URLs
                        })
                    
                    logger.info(f"✅ Got {len(formatted_news)} news items from IB for {ticker}")
                    return formatted_news
                    
        except Exception as e:
            logger.warning(f"IB news failed for {ticker}: {e}")
    
    # Fallback to Finnhub (your existing implementation)
    try:
        url = (
            f"https://finnhub.io/api/v1/company-news?"
            f"symbol={ticker}&from={start_date}&to={end_date}&token={FINNHUB_API_KEY}"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        news = response.json()

        return [
            {
                "headline": article.get("headline"),
                "source": article.get("source"),
                "date": article.get("datetime"),
                "url": article.get("url"),
            }
            for article in news
        ]
    except Exception as e:
        logger.error(f"Finnhub news failed for {ticker}: {e}")
        return []

def fetch_prior_close_yield(symbol: str) -> float:
    """Get previous day's yield - simplified"""
    try:
        ib = get_ib_connection()
        if ib:
            contract = parse_ib_symbol(symbol)
            hist = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='5 D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True
            )
            if len(hist) >= 2:
                return round(float(hist[-2].close), 3)
    except Exception as e:
        logger.warning(f"Prior yield fetch failed for {symbol}: {e}")
    
    return None

# Functions you don't actually use - removing them:
# - fetch_ticker_data() - not used in content generation
# - fetch_market_summary() - not used
# - get_multi_asset_snapshot() - not used

def test_simple_integration():
    """Simple test of what you actually use"""
    print("🧪 Testing Simplified IB Integration")
    print("=" * 40)
    
    test_symbols = ["AAPL", "ES-FUT-USD", "bitcoin"]
    
    for symbol in test_symbols:
        try:
            data = fetch_last_price(symbol)
            print(f"✅ {symbol}: ${data['price']} ({data['change_percent']:+.2f}%)")
        except Exception as e:
            print(f"❌ {symbol}: {e}")
    
    print("\n🔄 Testing top movers...")
    try:
        movers = get_top_movers_from_constituents(limit=3)
        print(f"✅ Got {len(movers['top_gainers'])} gainers, {len(movers['top_losers'])} losers")
    except Exception as e:
        print(f"❌ Top movers failed: {e}")

if __name__ == "__main__":
    test_simple_integration()