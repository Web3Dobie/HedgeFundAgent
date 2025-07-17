# utils/ib_gateway_client.py
# Enhanced IB Gateway integration with connection pooling and error handling

import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from contextlib import contextmanager
import threading
from dataclasses import dataclass

from ib_insync import *
from dotenv import load_dotenv

from utils.config import LOG_DIR
from data.ticker_blocks import *

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@dataclass
class PriceData:
    """Structured price data response"""
    symbol: str
    price: float
    change_percent: float
    timestamp: str
    currency: str = "USD"
    volume: Optional[int] = None

class IBGatewayManager:
    """
    Production-ready IB Gateway manager with connection pooling,
    automatic reconnection, and comprehensive error handling.
    """
    
    def __init__(self, host='135.225.86.140', port=7497, max_clients=5):
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.client_pool = []
        self.available_clients = []
        self.pool_lock = threading.Lock()
        self.next_client_id = 1
        
        # Connection settings
        self.connection_timeout = 10  # seconds
        self.data_timeout = 5  # seconds for market data requests
        self.reconnect_attempts = 3
        
        logger.info(f"🔧 Initialized IB Gateway Manager for {host}:{port}")
    
    def _create_client(self) -> IB:
        """Create a new IB client with proper configuration"""
        try:
            ib = IB()
            client_id = self.next_client_id
            self.next_client_id += 1
            
            ib.connect(self.host, self.port, client_id, timeout=self.connection_timeout)
            ib.reqMarketDataType(3)  # Delayed market data
            
            logger.info(f"✅ Created IB client #{client_id}")
            return ib
            
        except Exception as e:
            logger.error(f"❌ Failed to create IB client: {e}")
            raise ConnectionError(f"Cannot connect to IB Gateway: {e}")
    
    @contextmanager
    def get_client(self):
        """Context manager for getting/returning IB clients from pool"""
        client = None
        try:
            with self.pool_lock:
                if self.available_clients:
                    client = self.available_clients.pop()
                elif len(self.client_pool) < self.max_clients:
                    client = self._create_client()
                    self.client_pool.append(client)
                else:
                    # Wait for available client
                    logger.warning("⏳ All IB clients busy, waiting...")
                    time.sleep(1)
                    if self.available_clients:
                        client = self.available_clients.pop()
                    else:
                        raise ConnectionError("No IB clients available")
            
            # Verify connection
            if not client.isConnected():
                logger.warning("🔄 Reconnecting stale IB client")
                client = self._create_client()
            
            yield client
            
        except Exception as e:
            logger.error(f"❌ IB client error: {e}")
            # Don't return broken client to pool
            if client and client.isConnected():
                client.disconnect()
            raise
            
        finally:
            # Return client to pool if still connected
            if client and client.isConnected():
                with self.pool_lock:
                    self.available_clients.append(client)
    
    def parse_symbol(self, symbol: str) -> Contract:
        """
        Enhanced symbol parser with better error handling and more contract types
        """
        try:
            if '-' not in symbol:
                # Plain stock symbol
                return Stock(symbol, 'SMART', 'USD')
            
            parts = symbol.split('-')
            if len(parts) != 3:
                logger.warning(f"Invalid symbol format: {symbol}, using as stock")
                return Stock(symbol, 'SMART', 'USD')
            
            sym, contract_type, currency = parts
            
            if contract_type == 'STK':
                return Stock(sym, 'SMART', currency)
                
            elif contract_type == 'FUT':
                return self._create_future_contract(sym, currency)
                
            elif contract_type == 'CASH':
                return Forex(sym)
                
            elif contract_type == 'IND':
                return self._create_index_contract(sym, currency)
                
            else:
                logger.warning(f"Unknown contract type: {contract_type}")
                return Stock(sym, 'SMART', currency)
                
        except Exception as e:
            logger.error(f"Error parsing symbol {symbol}: {e}")
            raise ValueError(f"Cannot parse symbol {symbol}: {e}")
    
    def _create_future_contract(self, symbol: str, currency: str) -> Future:
        """Create futures contract with proper exchange mapping"""
        exchange_map = {
            'ES': 'CME', 'YM': 'CBOT', 'NQ': 'CME', 'RTY': 'CME',
            'GC': 'COMEX', 'SI': 'COMEX', 'CL': 'NYMEX', 
            'NG': 'NYMEX', 'HG': 'COMEX', 'ZN': 'CBOT'
        }
        exchange = exchange_map.get(symbol, 'CME')
        
        # Dynamic expiry calculation - use next quarterly expiry
        now = datetime.now()
        quarter_months = [3, 6, 9, 12]
        next_quarter = next((m for m in quarter_months if m > now.month), quarter_months[0])
        
        if next_quarter == quarter_months[0]:  # Next year
            expiry_year = now.year + 1
        else:
            expiry_year = now.year
        
        # Third Friday of the month (futures expiry)
        expiry_day = 21 - (datetime(expiry_year, next_quarter, 1).weekday() + 2) % 7
        expiry = f"{expiry_year}{next_quarter:02d}{expiry_day:02d}"
        
        return Future(symbol, expiry, exchange)
    
    def _create_index_contract(self, symbol: str, currency: str) -> Index:
        """Create index contract with proper exchange mapping"""
        exchange_map = {
            'N225': 'OSE.JPN', 'HSI': 'HKFE', 'KOSPI': 'KRX',
            'SX5E': 'DTB', 'UKX': 'LIFFE', 'DAX': 'DTB', 
            'CAC': 'MONEP', '300': 'SSE',
            'IRX': 'CBOE', 'FVX': 'CBOE', 'TNX': 'CBOE', 'TYX': 'CBOE'
        }
        exchange = exchange_map.get(symbol, 'SMART')
        return Index(symbol, exchange, currency)
    
    def get_price_data(self, symbol: str) -> PriceData:
        """
        Get current price data with comprehensive error handling
        """
        with self.get_client() as ib:
            try:
                contract = self.parse_symbol(symbol)
                logger.debug(f"📊 Requesting price for {symbol}")
                
                # Get recent historical data for change calculation
                end_time = datetime.now()
                hist_bars = ib.reqHistoricalData(
                    contract,
                    endDateTime=end_time.strftime('%Y%m%d %H:%M:%S'),
                    durationStr='3 D',
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    timeout=self.data_timeout
                )
                
                if len(hist_bars) < 2:
                    raise ValueError(f"Insufficient historical data for {symbol}")
                
                # Get live market data
                ticker = ib.reqMktData(contract, '', False, False)
                ib.sleep(self.data_timeout)
                
                # Determine current price
                current_price = self._get_best_price(ticker, hist_bars[-1])
                prev_close = float(hist_bars[-2].close)
                
                if prev_close <= 0:
                    raise ValueError(f"Invalid previous close for {symbol}")
                
                # Calculate metrics
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                # Format price based on asset type  
                if 'CASH' in symbol:  # FX
                    formatted_price = round(current_price, 4)
                elif 'IND' in symbol and any(x in symbol for x in ['IRX', 'FVX', 'TNX', 'TYX']):  # Yields
                    formatted_price = round(current_price, 3)
                else:
                    formatted_price = round(current_price, 2)
                
                result = PriceData(
                    symbol=symbol,
                    price=formatted_price,
                    change_percent=round(change_pct, 2),
                    timestamp=hist_bars[-1].date.strftime('%Y-%m-%d'),
                    currency=getattr(contract, 'currency', 'USD'),
                    volume=getattr(hist_bars[-1], 'volume', None)
                )
                
                logger.debug(f"✅ {symbol}: ${formatted_price} ({change_pct:+.2f}%)")
                return result
                
            except Exception as e:
                logger.error(f"❌ Error fetching {symbol}: {e}")
                raise
    
    def _get_best_price(self, ticker, latest_bar) -> float:
        """Get the best available current price"""
        # Try market price first
        if hasattr(ticker, 'marketPrice') and ticker.marketPrice() and ticker.marketPrice() > 0:
            return float(ticker.marketPrice())
        
        # Try last price
        if hasattr(ticker, 'last') and ticker.last and ticker.last > 0:
            return float(ticker.last)
        
        # Try mid price from bid/ask
        if (hasattr(ticker, 'bid') and hasattr(ticker, 'ask') and 
            ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0):
            return (float(ticker.bid) + float(ticker.ask)) / 2
        
        # Fall back to latest close
        return float(latest_bar.close)
    
    def get_historical_data(self, symbol: str, period: str = "1mo") -> pd.DataFrame:
        """
        Get historical data with proper period mapping
        """
        with self.get_client() as ib:
            try:
                contract = self.parse_symbol(symbol)
                
                # Map periods to IB duration strings
                period_map = {
                    '1d': '1 D', '5d': '5 D', '1mo': '1 M', 
                    '3mo': '3 M', '6mo': '6 M', '1y': '1 Y', '2y': '2 Y'
                }
                duration = period_map.get(period, '1 M')
                
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr=duration,
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    timeout=self.data_timeout * 2  # Longer timeout for historical data
                )
                
                if not bars:
                    logger.warning(f"No historical data for {symbol}")
                    return pd.DataFrame()
                
                # Convert to DataFrame
                df = util.df(bars)
                df.set_index('date', inplace=True)
                
                # Rename columns to match yfinance format
                column_map = {
                    'open': 'Open', 'high': 'High', 'low': 'Low',
                    'close': 'Close', 'volume': 'Volume'
                }
                df = df.rename(columns=column_map)
                
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
                
            except Exception as e:
                logger.error(f"Error fetching historical data for {symbol}: {e}")
                return pd.DataFrame()
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, PriceData]:
        """
        Efficiently fetch multiple prices with batch processing
        """
        results = {}
        failed = []
        
        for symbol in symbols:
            try:
                results[symbol] = self.get_price_data(symbol)
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                failed.append(symbol)
        
        if failed:
            logger.warning(f"Failed to fetch {len(failed)} symbols: {failed}")
        
        logger.info(f"✅ Fetched {len(results)}/{len(symbols)} symbols successfully")
        return results
    
    def disconnect_all(self):
        """Clean shutdown of all connections"""
        with self.pool_lock:
            for client in self.client_pool:
                try:
                    if client.isConnected():
                        client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting client: {e}")
            
            self.client_pool.clear()
            self.available_clients.clear()
        
        logger.info("🔌 Disconnected all IB clients")

# Global instance
_ib_manager = None

def get_ib_manager() -> IBGatewayManager:
    """Get or create global IB manager instance"""
    global _ib_manager
    if _ib_manager is None:
        _ib_manager = IBGatewayManager()
    return _ib_manager

# Update your existing functions to use the new manager
def fetch_last_price_yf(symbol: str) -> dict:
    """
    Updated function using new IB manager - maintains API compatibility
    """
    manager = get_ib_manager()
    price_data = manager.get_price_data(symbol)
    
    return {
        "price": price_data.price,
        "change_percent": price_data.change_percent,
        "timestamp": price_data.timestamp
    }

def fetch_ticker_data(ticker: str, period="1mo") -> pd.DataFrame:
    """
    Updated historical data function using new IB manager
    """
    manager = get_ib_manager()
    return manager.get_historical_data(ticker, period)

def get_top_movers_from_constituents(limit=5, include_extended=False) -> dict:
    """
    Enhanced top movers using batch processing
    """
    from utils.text_utils import TICKER_INFO
    
    symbols = list(TICKER_INFO.keys())[:20]  # Limit for performance
    manager = get_ib_manager()
    
    try:
        price_data = manager.get_multiple_prices(symbols)
        
        # Convert to tuple format for sorting
        data = [
            (symbol, price_data[symbol].price, price_data[symbol].change_percent)
            for symbol, data_obj in price_data.items()
        ]
        
        movers = {
            "top_gainers": sorted(data, key=lambda x: -x[2])[:limit],
            "top_losers": sorted(data, key=lambda x: x[2])[:limit]
        }
        
        if include_extended:
            logger.warning("Extended hours data not implemented")
            movers["pre_market"] = []
            movers["post_market"] = []
        
        return movers
        
    except Exception as e:
        logger.error(f"Error getting top movers: {e}")
        return {"top_gainers": [], "top_losers": [], "pre_market": [], "post_market": []}

# Testing function
def test_ib_integration():
    """Test the enhanced IB integration"""
    test_symbols = [
        "AAPL",              # Stock
        "ES-FUT-USD",        # S&P 500 futures  
        "EURUSD-CASH-EUR",   # FX pair
        "TNX-IND-USD",       # 10Y Treasury yield
        "GC-FUT-USD"         # Gold futures
    ]
    
    manager = get_ib_manager()
    
    print("🧪 Testing IB Gateway Integration")
    print("=" * 50)
    
    for symbol in test_symbols:
        try:
            start_time = time.time()
            data = manager.get_price_data(symbol)
            elapsed = time.time() - start_time
            
            print(f"✅ {symbol:15} | ${data.price:>8} | {data.change_percent:>+6.2f}% | {elapsed:.2f}s")
            
        except Exception as e:
            print(f"❌ {symbol:15} | ERROR: {e}")
    
    print("\n🔄 Testing batch processing...")
    start_time = time.time()
    batch_results = manager.get_multiple_prices(test_symbols[:3])
    elapsed = time.time() - start_time
    print(f"✅ Batch fetched {len(batch_results)} symbols in {elapsed:.2f}s")
    
    # Clean shutdown
    manager.disconnect_all()
    print("🔌 Test complete - disconnected all clients")

if __name__ == "__main__":
    test_ib_integration()