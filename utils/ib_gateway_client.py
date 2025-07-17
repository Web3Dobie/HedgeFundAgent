# utils/ib_gateway_client.py - Updated to use your config

from utils.config import IB_GATEWAY_HOST, IB_GATEWAY_PORT, IB_MAX_CLIENTS
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional, List
from contextlib import contextmanager
from dataclasses import dataclass

from ib_insync import *

logger = logging.getLogger(__name__)

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
    IB Gateway manager using your config settings
    """
    
    def __init__(self, host=None, port=None, max_clients=None):
        # Use config values or provided overrides
        self.host = host or IB_GATEWAY_HOST
        self.port = port or IB_GATEWAY_PORT
        self.max_clients = max_clients or IB_MAX_CLIENTS
        
        self.client_pool = []
        self.available_clients = []
        self.pool_lock = threading.Lock()
        self.next_client_id = 1
        
        # Connection settings
        self.connection_timeout = 10
        self.data_timeout = 10  # Longer timeout for delayed data
        self.reconnect_attempts = 3
        
        logger.info(f"🔧 IB Manager: {self.host}:{self.port}, max_clients={self.max_clients}")
        
        # Special handling for max_clients = 1
        if self.max_clients == 1:
            logger.info("📌 Single connection mode - will create/destroy connections as needed")
    
    def _create_client(self) -> IB:
        """Create a new IB client with proper configuration"""
        try:
            ib = IB()
            client_id = self.next_client_id
            self.next_client_id += 1
            
            # For single connection mode, always use client ID 1
            if self.max_clients == 1:
                client_id = 1
            
            ib.connect(self.host, self.port, client_id, timeout=self.connection_timeout)
            ib.reqMarketDataType(3)  # Delayed market data
            
            logger.info(f"✅ Created IB client #{client_id}")
            return ib
            
        except Exception as e:
            logger.error(f"❌ Failed to create IB client: {e}")
            raise ConnectionError(f"Cannot connect to IB Gateway: {e}")
    
    @contextmanager
    def get_client(self):
        """Context manager optimized for your max_clients setting"""
        client = None
        
        if self.max_clients == 1:
            # Single connection mode - create fresh connection each time
            try:
                client = self._create_client()
                yield client
            except Exception as e:
                logger.error(f"❌ Single connection failed: {e}")
                raise
            finally:
                if client and client.isConnected():
                    client.disconnect()
                    logger.debug("🔌 Disconnected single connection")
        else:
            # Pool mode for multiple connections
            try:
                with self.pool_lock:
                    if self.available_clients:
                        client = self.available_clients.pop()
                    elif len(self.client_pool) < self.max_clients:
                        client = self._create_client()
                        self.client_pool.append(client)
                    else:
                        raise ConnectionError(f"All {self.max_clients} IB clients busy")
                
                # Verify connection
                if not client.isConnected():
                    logger.warning("🔄 Reconnecting stale IB client")
                    client = self._create_client()
                
                yield client
                
            except Exception as e:
                logger.error(f"❌ Pool connection error: {e}")
                if client:
                    try:
                        client.disconnect()
                    except:
                        pass
                    with self.pool_lock:
                        if client in self.client_pool:
                            self.client_pool.remove(client)
                raise
                
            finally:
                # Return client to pool if still connected
                if client and client.isConnected():
                    with self.pool_lock:
                        if client not in self.available_clients:
                            self.available_clients.append(client)
    
    def parse_symbol(self, symbol: str) -> Contract:
        """Parse symbol to IB contract with updated expiries"""
        try:
            if '-' not in symbol:
                return Stock(symbol, 'SMART', 'USD')
            
            parts = symbol.split('-')
            if len(parts) != 3:
                return Stock(symbol, 'SMART', 'USD')
            
            sym, contract_type, currency = parts
            
            if contract_type == 'FUT':
                # Updated expiry dates for January 2025
                futures_config = {
                    'ES': ('CME', '20250321'),      # March 2025 (H25)
                    'YM': ('CBOT', '20250321'),     
                    'NQ': ('CME', '20250321'),      
                    'RTY': ('CME', '20250321'),     
                    'GC': ('COMEX', '20250227'),    # February 2025 (G25) - most liquid
                    'SI': ('COMEX', '20250326'),    # March 2025
                    'CL': ('NYMEX', '20250220'),    # February 2025 - front month
                    'NG': ('NYMEX', '20250225'),    
                    'HG': ('COMEX', '20250226'),    
                    'ZN': ('CBOT', '20250319'),     # March 2025
                    'ZT': ('CBOT', '20250331'),     
                    'ZB': ('CBOT', '20250320'),     
                }
                
                if sym in futures_config:
                    exchange, expiry = futures_config[sym]
                    return Future(sym, expiry, exchange)
                else:
                    return Future(sym, '20250321', 'CME')
                    
            elif contract_type == 'CASH':
                forex_symbol = sym.replace('.', '')  # USD.JPY -> USDJPY
                return Forex(forex_symbol)
                
            elif contract_type == 'IND':
                exchange_map = {
                    'N225': 'OSE.JPN', 'HSI': 'HKFE', 'KOSPI': 'KRX',
                    'SX5E': 'DTB', 'UKX': 'LIFFE', 'DAX': 'DTB', 
                    'CAC': 'MONEP', '300': 'SSE'
                }
                exchange = exchange_map.get(sym, 'SMART')
                return Index(sym, exchange, currency)
            
            return Stock(sym, 'SMART', currency)
                
        except Exception as e:
            logger.error(f"Error parsing symbol {symbol}: {e}")
            raise ValueError(f"Cannot parse symbol {symbol}: {e}")
    
    def get_price_data(self, symbol: str) -> PriceData:
        """Get current price data"""
        with self.get_client() as ib:
            try:
                contract = self.parse_symbol(symbol)
                logger.debug(f"📊 Requesting price for {symbol}")
                
                # Get historical data for change calculation
                hist_bars = ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr='5 D',
                    barSizeSetting='1 day',
                    whatToShow='TRADES',
                    useRTH=True,
                    timeout=self.data_timeout
                )
                
                if len(hist_bars) < 2:
                    raise ValueError(f"Insufficient historical data for {symbol}")
                
                current_price = float(hist_bars[-1].close)
                prev_close = float(hist_bars[-2].close)
                
                if prev_close <= 0:
                    raise ValueError(f"Invalid previous close for {symbol}")
                
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                # Format price based on asset type
                if 'CASH' in symbol:
                    formatted_price = round(current_price, 4)
                elif 'IND' in symbol and any(x in symbol for x in ['IRX', 'FVX', 'TNX', 'TYX']):
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
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, PriceData]:
        """Get multiple prices - optimized for single connection mode"""
        results = {}
        failed = []
        
        if self.max_clients == 1:
            # Sequential requests with fresh connections
            for symbol in symbols:
                try:
                    result = self.get_price_data(symbol)
                    results[symbol] = result
                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.warning(f"Failed to fetch {symbol}: {e}")
                    failed.append(symbol)
        else:
            # Batch request with single connection
            with self.get_client() as ib:
                for symbol in symbols:
                    try:
                        contract = self.parse_symbol(symbol)
                        
                        hist_bars = ib.reqHistoricalData(
                            contract,
                            endDateTime='',
                            durationStr='5 D',
                            barSizeSetting='1 day',
                            whatToShow='TRADES',
                            useRTH=True,
                            timeout=self.data_timeout
                        )
                        
                        if len(hist_bars) >= 2:
                            current_price = float(hist_bars[-1].close)
                            prev_close = float(hist_bars[-2].close)
                            change_pct = ((current_price - prev_close) / prev_close) * 100
                            
                            formatted_price = round(current_price, 4) if 'CASH' in symbol else round(current_price, 2)
                            
                            results[symbol] = PriceData(
                                symbol=symbol,
                                price=formatted_price,
                                change_percent=round(change_pct, 2),
                                timestamp=hist_bars[-1].date.strftime('%Y-%m-%d'),
                                currency=getattr(contract, 'currency', 'USD')
                            )
                        else:
                            failed.append(symbol)
                            
                        time.sleep(0.2)  # Rate limiting
                        
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

# Global instance using your config
_ib_manager = None

def get_ib_manager() -> IBGatewayManager:
    """Get or create global IB manager instance using config"""
    global _ib_manager
    if _ib_manager is None:
        _ib_manager = IBGatewayManager()
    return _ib_manager

# Test function using your actual config
def test_with_your_config():
    """Test with your actual configuration"""
    print(f"🧪 Testing with Config: {IB_GATEWAY_HOST}:{IB_GATEWAY_PORT}, max_clients={IB_MAX_CLIENTS}")
    print("=" * 60)
    
    manager = get_ib_manager()
    
    test_symbols = ["AAPL", "MSFT", "ES-FUT-USD"]
    
    for symbol in test_symbols:
        try:
            start_time = time.time()
            data = manager.get_price_data(symbol)
            elapsed = time.time() - start_time
            
            print(f"✅ {symbol:15} | ${data.price:>8} | {data.change_percent:>+6.2f}% | {elapsed:.2f}s")
            
        except Exception as e:
            print(f"❌ {symbol:15} | ERROR: {e}")

if __name__ == "__main__":
    test_with_your_config()