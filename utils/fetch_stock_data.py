# utils/fetch_stock_data.py
# Pure IB Gateway implementation - no yfinance fallback

import pandas as pd
import requests
import os
import logging
import json
from datetime import datetime, timedelta
from utils.text_utils import TICKER_INFO

# IB Gateway imports
from ib_insync import *

from dotenv import load_dotenv
from utils.config import (FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY)

logger = logging.getLogger(__name__)
load_dotenv()

# Global IB client
_ib_client = None

class IBGatewayClient:
    """Pure IB Gateway client for all market data"""
    
    def __init__(self, host='135.225.86.140', port=7497, client_id=1):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.connected = False
        
    def connect(self) -> bool:
        """Connect to IB Gateway - fail fast if unavailable"""
        try:
            if not self.ib.isConnected():
                self.ib.connect(self.host, self.port, self.client_id)
                self.ib.reqMarketDataType(3)  # Delayed data
                self.connected = True
                logger.info("✅ Connected to IB Gateway")
            return True
        except Exception as e:
            logger.error(f"❌ IB Gateway connection failed: {e}")
            raise ConnectionError(f"IB Gateway unavailable: {e}")
    
    def disconnect(self):
        """Disconnect from IB Gateway"""
        if self.ib.isConnected():
            self.ib.disconnect()
            self.connected = False
            logger.info("Disconnected from IB Gateway")
    
    def parse_ib_symbol(self, symbol: str):
        """Parse IB symbol format: SYMBOL-TYPE-CURRENCY or plain symbols"""
        try:
            if '-' not in symbol:
                # Regular stock symbol (AAPL, MSFT, etc.)
                return Stock(symbol, 'SMART', 'USD')
            
            parts = symbol.split('-')
            if len(parts) != 3:
                return Stock(symbol, 'SMART', 'USD')
            
            sym, contract_type, currency = parts
            
            if contract_type == 'STK':
                return Stock(sym, 'SMART', currency)
                
            elif contract_type == 'FUT':
                # Futures mapping
                exchange_map = {
                    'ES': 'CME', 'YM': 'CBOT', 'NQ': 'CME', 'RTY': 'CME',
                    'GC': 'COMEX', 'SI': 'COMEX', 'CL': 'NYMEX', 
                    'NG': 'NYMEX', 'HG': 'COMEX', 'ZN': 'CBOT'
                }
                exchange = exchange_map.get(sym, 'CME')
                # Use March 2025 expiry - update this periodically
                expiry = '20250321'
                return Future(sym, expiry, exchange)
                
            elif contract_type == 'CASH':
                # FX pairs
                return Forex(sym)
                
            elif contract_type == 'IND':
                # Indices
                exchange_map = {
                    'N225': 'OSE.JPN',    # Nikkei
                    'HSI': 'HKFE',        # Hang Seng
                    'KOSPI': 'KRX',       # Korean
                    'SX5E': 'DTB',        # Euro Stoxx 50
                    'UKX': 'LIFFE',       # FTSE 100
                    'DAX': 'DTB',         # German DAX
                    'CAC': 'MONEP',       # French CAC
                    '300': 'SSE',         # CSI 300
                    'IRX': 'CBOE',        # 3M Treasury
                    'FVX': 'CBOE',        # 5Y Treasury
                    'TNX': 'CBOE',        # 10Y Treasury
                    'TYX': 'CBOE'         # 30Y Treasury
                }
                exchange = exchange_map.get(sym, 'SMART')
                return Index(sym, exchange, currency)
                
            else:
                logger.warning(f"Unknown contract type: {contract_type}")
                return Stock(sym, 'SMART', currency)
                
        except Exception as e:
            logger.error(f"Error parsing symbol {symbol}: {e}")
            return None
    
    def get_price_data(self, symbol: str) -> dict:
        """Get price data from IB Gateway"""
        if not self.connect():
            raise ConnectionError("Cannot connect to IB Gateway")
        
        try:
            contract = self.parse_ib_symbol(symbol)
            if not contract:
                raise ValueError(f"Could not create contract for {symbol}")
            
            logger.debug(f"Requesting data for {symbol} -> {contract}")
            
            # Get historical data for change calculation
            hist = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='2 D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True
            )
            
            if not hist:
                raise ValueError(f"No historical data available for {symbol}")
            
            # Get current market data
            ticker = self.ib.reqMktData(contract)
            self.ib.sleep(3)  # Wait longer for data
            
            # Calculate current price and change
            latest_bar = hist[-1]
            prev_bar = hist[-2] if len(hist) > 1 else latest_bar
            
            # Use market price if available, otherwise latest close
            current_price = ticker.marketPrice() if ticker.marketPrice() and ticker.marketPrice() > 0 else latest_bar.close
            prev_close = prev_bar.close
            
            if prev_close <= 0:
                raise ValueError(f"Invalid previous close price for {symbol}")
            
            change_pct = ((current_price - prev_close) / prev_close) * 100
            timestamp = latest_bar.date.date().isoformat()
            
            # Format price based on asset type
            if 'CASH' in symbol:  # FX pairs
                formatted_price = round(float(current_price), 4)
            else:
                formatted_price = round(float(current_price), 2)
            
            result = {
                "price": formatted_price,
                "change_percent": round(float(change_pct), 2),
                "timestamp": timestamp
            }
            
            logger.debug(f"✅ {symbol}: ${formatted_price} ({change_pct:+.2f}%)")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error fetching {symbol}: {e}")
            raise

def get_ib_client():
    """Get or create global IB client"""
    global _ib_client
    if _ib_client is None:
        _ib_client = IBGatewayClient()
    return _ib_client

def fetch_last_price_yf(symbol: str) -> dict:
    """
    Pure IB Gateway implementation - replaces yfinance entirely
    Returns: {"price": float, "change_percent": float, "timestamp": str}
    Raises: ConnectionError if IB Gateway unavailable
    """
    client = get_ib_client()
    return client.get_price_data(symbol)

def fetch_ticker_data(ticker: str, period="1mo") -> pd.DataFrame:
    """
    Fetch historical data using IB Gateway
    """
    client = get_ib_client()
    if not client.connect():
        raise ConnectionError("IB Gateway not available for historical data")
    
    try:
        contract = client.parse_ib_symbol(ticker)
        if not contract:
            raise ValueError(f"Could not create contract for {ticker}")
        
        # Convert period to IB duration
        period_map = {
            '1mo': '1 M',
            '3mo': '3 M', 
            '6mo': '6 M',
            '1y': '1 Y',
            '2y': '2 Y'
        }
        duration = period_map.get(period, '1 M')
        
        bars = client.ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr=duration,
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )
        
        if not bars:
            return pd.DataFrame()
        
        # Convert to pandas DataFrame
        df = util.df(bars)
        df.set_index('date', inplace=True)
        
        # Rename columns to match yfinance format
        column_map = {
            'open': 'Open',
            'high': 'High', 
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        df = df.rename(columns=column_map)
        
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        
    except Exception as e:
        logger.error(f"Error fetching historical data for {ticker}: {e}")
        return pd.DataFrame()

def fetch_prior_close_yield(symbol: str) -> float:
    """Get previous day's closing yield using IB Gateway"""
    try:
        df = fetch_ticker_data(symbol, period="5d")  # Get more days for safety
        if len(df) >= 2:
            return round(float(df["Close"].iloc[-2]), 2)
        return None
    except Exception as e:
        logger.error(f"Error fetching prior yield for {symbol}: {e}")
        return None

def fetch_stock_news(ticker: str, start_date: str, end_date: str):
    """Fetch news using Finnhub API (unchanged)"""
    if not ticker:
        raise ValueError("Ticker symbol cannot be blank.")
    
    if not start_date or not end_date:
        raise ValueError("Both start_date and end_date must be provided.")

    try:
        url = (
            f"https://finnhub.io/api/v1/company-news?"
            f"symbol={ticker}&from={start_date}&to={end_date}&token={FINNHUB_API_KEY}"
        )
        response = requests.get(url)
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
    except requests.RequestException as e:
        logger.error(f"Error fetching news for {ticker}: {e}")
        return []

def fetch_market_summary():
    """Fetch market summary using Finnhub API (unchanged)"""
    try:
        url = f"https://finnhub.io/api/v1/market/status?token={FINNHUB_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching market summary: {e}")
        return {}

def get_top_movers_from_constituents(limit=5, include_extended=False) -> dict:
    """
    Get top movers using IB Gateway data
    Note: Extended hours data requires different IB setup
    """
    combined = sorted(TICKER_INFO.keys())
    data = []
    
    client = get_ib_client()
    
    for symbol in combined[:20]:  # Limit to avoid timeouts
        try:
            price_data = fetch_last_price_yf(symbol)
            if price_data:
                price = price_data["price"]
                change_pct = price_data["change_percent"]
                data.append((symbol, price, change_pct))
        except Exception as e:
            logger.warning(f"Could not get mover data for {symbol}: {e}")
            continue

    movers = {
        "top_gainers": sorted(data, key=lambda x: -x[2])[:limit],
        "top_losers": sorted(data, key=lambda x: x[2])[:limit]
    }

    # Extended hours would require additional IB setup
    if include_extended:
        logger.warning("Extended hours data not implemented with IB Gateway yet")
        movers["pre_market"] = []
        movers["post_market"] = []

    return movers

# Test function
if __name__ == "__main__":
    # Test the pure IB implementation
    test_symbols = ["AAPL", "ES-FUT-USD", "EURUSD-CASH-EUR"]
    
    for symbol in test_symbols:
        try:
            print(f"Testing {symbol}...")
            data = fetch_last_price_yf(symbol)
            print(f"  ✅ Price: ${data['price']}, Change: {data['change_percent']:+.2f}%")
        except Exception as e:
            print(f"  ❌ Failed: {e}")