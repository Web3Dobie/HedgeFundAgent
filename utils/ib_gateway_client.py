# utils/ib_gateway_client.py - Clean Production Version

from utils.config import IB_GATEWAY_HOST, IB_GATEWAY_PORT, IB_MAX_CLIENTS
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, List, Tuple
from contextlib import contextmanager
from dataclasses import dataclass
import queue
import pytz
import calendar

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.common import BarData

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

class IBApp(EWrapper, EClient):
    """
    IB API Application using official IBAPI
    """
    
    def __init__(self):
        EClient.__init__(self, self)
        
        # Connection state
        self.is_connected = False
        self.next_order_id = None
        self.accounts = []
        
        # Data storage
        self.price_data = {}
        self.historical_data = {}
        self.data_events = {}
        
        # Threading
        self.data_ready_events = {}
        self.request_timeout = 15
        
        logger.debug("📱 Created IBApp instance")
    
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors"""
        if errorCode in [2104, 2106, 2107, 2158, 1102]:
            # These are informational messages, not errors
            logger.debug(f"ℹ️ Info {errorCode}: {errorString}")
        else:
            logger.warning(f"❌ Error {errorCode}: {errorString}")
            
            # DON'T signal waiting requests on subscription errors
            # Only signal on actual connection/data errors that prevent retries
            if errorCode in [504, 502, 503, 321, 200]:  # Connection/fatal errors
                if reqId in self.data_ready_events:
                    self.data_ready_events[reqId].set()
    
    def connectAck(self):
        """Connection acknowledged"""
        logger.info("✅ IB API connection acknowledged")
        self.is_connected = True
    
    def managedAccounts(self, accountsList):
        """Receive managed accounts"""
        self.accounts = accountsList.split(',')
        logger.info(f"📊 Managed accounts: {self.accounts}")
    
    def nextValidId(self, orderId):
        """Receive next valid order ID"""
        self.next_order_id = orderId
        logger.debug(f"🆔 Next valid order ID: {orderId}")
    
    def historicalData(self, reqId, bar):
        """Receive historical data bar"""
        if reqId not in self.historical_data:
            self.historical_data[reqId] = []
        
        # Convert BarData to dict for easier handling
        bar_dict = {
            'date': bar.date,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        }
        
        self.historical_data[reqId].append(bar_dict)
        logger.debug(f"📊 Historical bar for reqId {reqId}: {bar.date} close={bar.close}")
    
    def historicalDataEnd(self, reqId, start, end):
        """Historical data request completed"""
        logger.debug(f"✅ Historical data complete for reqId {reqId}")
        
        # Signal that data is ready
        if reqId in self.data_ready_events:
            self.data_ready_events[reqId].set()
    
    def tickPrice(self, reqId, tickType, price, attrib):
        """Receive tick price data"""
        if reqId not in self.price_data:
            self.price_data[reqId] = {}
        
        # Store different tick types (expanded for IB's actual tick types)
        tick_types = {
            1: 'bid',
            2: 'ask', 
            4: 'last',
            6: 'high',
            7: 'low',
            9: 'close',
            # Additional IB tick types we're actually receiving
            66: 'delayed_bid',      # Delayed bid
            67: 'delayed_ask',      # Delayed ask  
            68: 'delayed_last',     # Delayed last
            72: 'delayed_high',     # Delayed high
            73: 'delayed_low',      # Delayed low
            75: 'delayed_close',    # Delayed close
        }
        
        if tickType in tick_types:
            self.price_data[reqId][tick_types[tickType]] = price
            logger.debug(f"💰 Tick price reqId {reqId}: {tick_types[tickType]}={price}")
            
            # Check if we have enough data to proceed
            if reqId in self.data_ready_events:
                data = self.price_data[reqId]
                # Check for any valid price data (including delayed ticks)
                has_last = ('last' in data and data['last'] > 0) or ('delayed_last' in data and data['delayed_last'] > 0)
                has_bid_ask = (('bid' in data and 'ask' in data and data['bid'] > 0 and data['ask'] > 0) or 
                              ('delayed_bid' in data and 'delayed_ask' in data and data['delayed_bid'] > 0 and data['delayed_ask'] > 0))
                
                if has_last or has_bid_ask:
                    # We have sufficient price data
                    self.data_ready_events[reqId].set()
    
    def tickSize(self, reqId, tickType, size):
        """Receive tick size data"""
        if reqId not in self.price_data:
            self.price_data[reqId] = {}
        
        if tickType == 5:  # Volume
            self.price_data[reqId]['volume'] = size
            logger.debug(f"📊 Volume for reqId {reqId}: {size}")
    
    def tickString(self, reqId, tickType, value):
        """Receive tick string data"""
        if reqId not in self.price_data:
            self.price_data[reqId] = {}
            
        # Tick type 49 is often daily change percentage
        if tickType == 49:  # % change
            try:
                self.price_data[reqId]['change_percent'] = float(value)
                logger.debug(f"📈 Change % for reqId {reqId}: {value}%")
            except:
                pass
    
    def tickGeneric(self, reqId, tickType, value):
        """Receive generic tick data"""
        if reqId not in self.price_data:
            self.price_data[reqId] = {}
            
        # Look for daily change values
        if tickType == 45:  # Daily change points
            self.price_data[reqId]['change_points'] = value
            logger.debug(f"📊 Change points for reqId {reqId}: {value}")
        elif tickType == 46:  # Daily change percentage
            self.price_data[reqId]['change_percent'] = value
            logger.debug(f"📈 Change % for reqId {reqId}: {value}%")

class IBGatewayManager:
    """
    IB Gateway manager using official IBAPI
    """
    
    def __init__(self, host=None, port=None, max_clients=None):
        # Use config values or provided overrides
        self.host = host or IB_GATEWAY_HOST
        self.port = port or IB_GATEWAY_PORT
        self.max_clients = max_clients or IB_MAX_CLIENTS
        
        # Connection management
        self.current_app = None
        self.api_thread = None
        self.connection_lock = threading.Lock()
        self.next_req_id = 1000
        
        # Settings
        self.connection_timeout = 15
        self.data_timeout = 15
        
        # Market hours setup
        self.eastern = pytz.timezone('US/Eastern')
        
        logger.info(f"🔧 IB Manager (Official API): {self.host}:{self.port}")
    
    def get_front_month_contract(self, symbol: str) -> str:
        """
        Automatically calculate the appropriate front month contract
        Returns local symbol like 'ESU5' for current front month
        """
        now = datetime.now()
        year_digit = str(now.year)[-1]  # Last digit of year (2025 -> 5)
        
        # Month codes: F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun,
        #              N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec
        month_codes = ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z']
        
        # Define roll schedules for different futures
        roll_schedules = {
            # Quarterly contracts (Mar, Jun, Sep, Dec)
            'ES': [2, 5, 8, 11],      # H, M, U, Z (March, June, Sept, Dec)
            'NQ': [2, 5, 8, 11],      
            'YM': [2, 5, 8, 11],      
            'RTY': [2, 5, 8, 11],     
            
            # Monthly contracts
            'CL': list(range(12)),    # All months
            'NG': list(range(12)),    
            'HG': [2, 4, 6, 8, 11],   # H, K, N, U, Z (selected months)
            
            # Specific schedules
            'GC': [1, 3, 5, 7, 9, 11],  # G, J, M, Q, V, Z (Feb, Apr, Jun, Aug, Oct, Dec)
            'SI': [2, 4, 6, 8, 11],      # H, K, N, U, Z (Mar, May, Jul, Sep, Dec)
            
            # Bonds - quarterly
            'ZN': [2, 5, 8, 11],      # H, M, U, Z
            'ZT': [2, 5, 8, 11],      
            'ZB': [2, 5, 8, 11],      
        }
        
        # Get roll schedule for this symbol
        schedule = roll_schedules.get(symbol, [2, 5, 8, 11])  # Default to quarterly
        
        current_month = now.month - 1  # 0-based (Jan=0, Dec=11)
        
        # Find next available contract month
        front_month = None
        for month_idx in schedule:
            if month_idx >= current_month:
                front_month = month_idx
                break
        
        # If no month found this year, use first month of next year
        if front_month is None:
            front_month = schedule[0]
            year_digit = str(now.year + 1)[-1]
        
        # Handle December -> next year transition
        elif current_month >= 11:  # December
            # Check if we need to roll to next year
            days_in_month = calendar.monthrange(now.year, now.month)[1]
            if now.day > days_in_month - 10:  # Within 10 days of month end
                front_month = schedule[0]
                year_digit = str(now.year + 1)[-1]
        
        month_code = month_codes[front_month]
        local_symbol = f"{symbol}{month_code}{year_digit}"
        
        logger.debug(f"📅 Front month for {symbol}: {local_symbol}")
        return local_symbol
    
    def get_market_status(self, symbol: str = None) -> Tuple[str, str]:
        """
        Determine current market status and appropriate data type
        Returns: (status, description)
        """
        try:
            # Get current Eastern time
            now_et = datetime.now(self.eastern)
            weekday = now_et.weekday()  # 0=Monday, 6=Sunday
            time_only = now_et.time()
            
            # Futures trade almost 24/7 except for brief maintenance windows
            if symbol and 'FUT' in symbol:
                # Futures maintenance windows (very brief)
                maintenance_start = datetime.strptime("17:00", "%H:%M").time()  # 5 PM ET
                maintenance_end = datetime.strptime("18:00", "%H:%M").time()    # 6 PM ET
                
                if weekday < 5:  # Monday-Friday
                    if maintenance_start <= time_only <= maintenance_end:
                        return "maintenance", "Futures maintenance window"
                    else:
                        return "futures_active", "Futures trading active"
                elif weekday == 6:  # Sunday
                    if time_only >= datetime.strptime("18:00", "%H:%M").time():
                        return "futures_active", "Sunday futures session"
                    else:
                        return "weekend", "Weekend - futures closed"
                else:  # Saturday
                    return "weekend", "Weekend - futures closed"
            
            # Stock market hours logic
            # Weekend check
            if weekday >= 5:  # Saturday (5) or Sunday (6)
                return "weekend", "Weekend - markets closed"
            
            # Define market hours (Eastern Time)
            pre_market_start = datetime.strptime("04:00", "%H:%M").time()
            market_open = datetime.strptime("09:30", "%H:%M").time()
            market_close = datetime.strptime("16:00", "%H:%M").time()
            post_market_end = datetime.strptime("20:00", "%H:%M").time()
            
            if time_only < pre_market_start:
                return "closed", "Before pre-market hours"
            elif pre_market_start <= time_only < market_open:
                return "pre_market", "Pre-market hours (4:00-9:30 AM ET)"
            elif market_open <= time_only < market_close:
                return "market_hours", "Regular market hours (9:30 AM-4:00 PM ET)"
            elif market_close <= time_only < post_market_end:
                return "post_market", "Post-market hours (4:00-8:00 PM ET)"
            else:
                return "closed", "After post-market hours"
                
        except Exception as e:
            logger.warning(f"Error determining market status: {e}")
            return "unknown", "Could not determine market status"
    
    def get_market_data_settings(self, symbol: str, market_status: str) -> Tuple[int, str]:
        """
        Get appropriate market data type and generic ticks based on symbol type
        Returns: (market_data_type, generic_ticks)
        """
        # FX is always real-time (live)
        if 'CASH' in symbol or '-CASH-' in symbol:
            return 1, "233"  # Real-time for FX
        
        # Futures - delayed (subscription issue with real-time)
        if 'FUT' in symbol or '-FUT-' in symbol:
            return 3, "233"  # Delayed for futures
        
        # Stocks - use delayed data (real-time requires separate API subscription)
        if market_status in ["pre_market", "post_market"]:
            # Extended hours - delayed with valid stock tick types
            return 3, "233"  # Delayed, valid stock ticks
        else:
            # Regular hours - delayed
            return 3, "233"  # Delayed for stocks
    
    def _get_next_req_id(self):
        """Get next request ID"""
        req_id = self.next_req_id
        self.next_req_id += 1
        return req_id
    
    @contextmanager
    def get_client(self):
        """Context manager for IB client connection - always create fresh for reliability"""
        # For reliability during batch operations, always create fresh connections
        app = None
        api_thread = None
        
        try:
            app = IBApp()
            
            # Connect
            logger.debug(f"🔗 Connecting to {self.host}:{self.port}")
            app.connect(self.host, self.port, 1)
            
            # Start API thread
            api_thread = threading.Thread(target=app.run, daemon=True)
            api_thread.start()
            
            # Wait for connection
            start_time = time.time()
            while not app.is_connected and (time.time() - start_time) < self.connection_timeout:
                time.sleep(0.1)
            
            if not app.is_connected:
                raise ConnectionError("Failed to connect to IB Gateway")
            
            # Wait for next valid ID
            start_time = time.time()
            while app.next_order_id is None and (time.time() - start_time) < 5:
                time.sleep(0.1)
            
            yield app
            
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            if app:
                try:
                    app.disconnect()
                except:
                    pass
            raise
        
        finally:
            # Always disconnect to avoid connection buildup
            if app:
                try:
                    app.disconnect()
                    logger.debug("🔌 Disconnected cleanly")
                except:
                    pass
    
    def disconnect_all(self):
        """Disconnect all connections"""
        with self.connection_lock:
            if self.current_app:
                try:
                    self.current_app.disconnect()
                    logger.info("🔌 Disconnected from IB Gateway")
                except:
                    pass
                self.current_app = None
                self.api_thread = None
    
    def parse_symbol(self, symbol: str) -> Contract:
        """Parse symbol to IB contract"""
        try:
            if '-' not in symbol:
                # Simple stock
                contract = Contract()
                contract.symbol = symbol
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = "USD"
                return contract
            
            parts = symbol.split('-')
            if len(parts) != 3:
                # Default to stock
                contract = Contract()
                contract.symbol = symbol
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = "USD"
                return contract
            
            sym, contract_type, currency = parts
            contract = Contract()
            
            if contract_type == 'FUT':
                contract.symbol = sym
                contract.secType = "FUT"
                contract.currency = currency
                
                # Set exchange
                exchange_map = {
                    'ES': 'CME', 'YM': 'CBOT', 'NQ': 'CME', 'RTY': 'CME',     
                    'GC': 'COMEX', 'SI': 'COMEX', 'CL': 'NYMEX', 'NG': 'NYMEX',    
                    'HG': 'COMEX', 'ZN': 'CBOT', 'ZT': 'CBOT', 'ZB': 'CBOT',     
                }
                
                contract.exchange = exchange_map.get(sym, 'CME')
                
                # Use intelligent front month calculation
                contract.localSymbol = self.get_front_month_contract(sym)
                    
            elif contract_type == 'CASH':
                contract.symbol = sym.replace('.', '')
                contract.secType = "CASH"
                contract.exchange = "IDEALPRO"
                contract.currency = currency
                
            elif contract_type == 'IND':
                contract.symbol = sym
                contract.secType = "IND"
                contract.currency = currency
                
                exchange_map = {
                    'N225': 'OSE.JPN', 'HSI': 'HKFE', 'KOSPI': 'KRX',
                    'SX5E': 'DTB', 'UKX': 'LIFFE', 'DAX': 'DTB', 
                    'CAC': 'MONEP', '300': 'SSE'
                }
                contract.exchange = exchange_map.get(sym, 'SMART')
            
            else:
                # Default to stock
                contract.symbol = sym
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = currency
                
            return contract
                
        except Exception as e:
            logger.error(f"Error parsing symbol {symbol}: {e}")
            raise ValueError(f"Cannot parse symbol {symbol}: {e}")
    
    def get_price_data(self, symbol: str) -> PriceData:
        """Get current price data using live market data with market hours detection"""
        with self.get_client() as app:
            try:
                # Determine market status and settings
                market_status, status_desc = self.get_market_status(symbol)
                market_data_type, generic_ticks = self.get_market_data_settings(symbol, market_status)
                
                logger.debug(f"📊 Market status for {symbol}: {status_desc}")
                logger.debug(f"📊 Requesting {symbol} with data type {market_data_type}")
                
                # Check if we should even try (weekend for non-futures)
                if market_status == "weekend" and 'FUT' not in symbol:
                    raise ValueError(f"Weekend - markets closed")
                elif market_status == "maintenance":
                    raise ValueError(f"Futures maintenance window - brief downtime")
                
                contract = self.parse_symbol(symbol)
                req_id = self._get_next_req_id()
                
                # Create event for this request
                app.data_ready_events[req_id] = threading.Event()
                app.price_data[req_id] = {}
                
                # Set appropriate market data type
                app.reqMarketDataType(market_data_type)
                
                # Request live market data with appropriate settings
                app.reqMktData(
                    req_id,
                    contract,
                    generic_ticks,  # Extended hours ticks if needed
                    False,  # snapshot
                    False,  # regulatorySnapshot
                    []  # mktDataOptions
                )
                
                # Wait for sufficient data with longer timeout for extended hours
                timeout = self.data_timeout * 2 if market_status in ["pre_market", "post_market"] else self.data_timeout
                
                if not app.data_ready_events[req_id].wait(timeout):
                    # Cancel market data request
                    app.cancelMktData(req_id)
                    
                    # Provide helpful error message based on market status and symbol type
                    if 'FUT' in symbol:
                        raise TimeoutError(f"Futures data timeout for {symbol} - likely no subscription access")
                    elif market_status == "closed":
                        raise TimeoutError(f"Market closed - no {symbol} data available")
                    elif market_status in ["pre_market", "post_market"]:
                        raise TimeoutError(f"Extended hours data timeout for {symbol} - may be public holiday")
                    else:
                        raise TimeoutError(f"Live market data timeout for {symbol}")
                
                # Check if we actually got valid data or just an error
                if req_id not in app.price_data or not app.price_data[req_id]:
                    app.cancelMktData(req_id)
                    raise ValueError(f"No market data received for {symbol} - subscription issue")
                
                # Process the data
                data = app.price_data[req_id]
                logger.debug(f"📊 Raw data for {symbol}: {data}")
                
                # Determine current price (check delayed ticks too)
                current_price = None
                if 'last' in data and data['last'] > 0:
                    current_price = float(data['last'])
                elif 'delayed_last' in data and data['delayed_last'] > 0:
                    current_price = float(data['delayed_last'])
                elif 'bid' in data and 'ask' in data and data['bid'] > 0 and data['ask'] > 0:
                    current_price = float((data['bid'] + data['ask']) / 2)
                elif 'delayed_bid' in data and 'delayed_ask' in data and data['delayed_bid'] > 0 and data['delayed_ask'] > 0:
                    current_price = float((data['delayed_bid'] + data['delayed_ask']) / 2)
                elif 'close' in data and data['close'] > 0:
                    current_price = float(data['close'])
                elif 'delayed_close' in data and data['delayed_close'] > 0:
                    current_price = float(data['delayed_close'])
                
                if current_price is None:
                    app.cancelMktData(req_id)
                    
                    # Enhanced error message based on market status and symbol type
                    if 'FUT' in symbol:
                        raise ValueError(f"No {symbol} futures data - check symbol or market data permissions")
                    elif market_status == "closed":
                        raise ValueError(f"No {symbol} data - market closed")
                    elif market_status in ["pre_market", "post_market"]:
                        raise ValueError(f"No {symbol} extended hours data - possible public holiday or no trading")
                    else:
                        raise ValueError(f"No valid price data for {symbol}")
                
                # Get change percentage
                change_pct = 0.0
                if 'change_percent' in data:
                    change_pct = float(data['change_percent'])
                elif 'change_points' in data and 'close' in data and data['close'] > 0:
                    # Calculate percentage from points change
                    change_points = float(data['change_points'])
                    prev_close = current_price - change_points
                    if prev_close > 0:
                        change_pct = (change_points / prev_close) * 100
                elif 'delayed_close' in data and data['delayed_close'] > 0:
                    # Calculate from delayed close price
                    prev_close = float(data['delayed_close'])
                    if prev_close > 0:
                        change_pct = ((current_price - prev_close) / prev_close) * 100
                elif 'close' in data and data['close'] > 0:
                    # Calculate from regular close price
                    prev_close = float(data['close'])
                    if prev_close > 0:
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
                    timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    currency=getattr(contract, 'currency', 'USD'),
                    volume=data.get('volume', None)
                )
                
                logger.debug(f"✅ {symbol}: ${formatted_price} ({change_pct:+.2f}%) [{market_status}]")
                
                # Cancel market data subscription
                app.cancelMktData(req_id)
                
                # Cleanup
                del app.data_ready_events[req_id]
                del app.price_data[req_id]
                
                return result
                
            except Exception as e:
                logger.error(f"❌ Error fetching {symbol}: {e}")
                # Cleanup on error
                try:
                    app.cancelMktData(req_id)
                except:
                    pass
                if req_id in app.data_ready_events:
                    del app.data_ready_events[req_id]
                if req_id in app.price_data:
                    del app.price_data[req_id]
                raise
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, PriceData]:
        """Get multiple prices using batch requests on single connection"""
        results = {}
        failed = []
        
        if not symbols:
            return results
        
        with self.get_client() as app:
            try:
                # Dictionary to track all active requests
                active_requests = {}
                
                # Start all market data requests
                for symbol in symbols:
                    try:
                        # Determine market status and settings for this symbol
                        market_status, status_desc = self.get_market_status(symbol)
                        market_data_type, generic_ticks = self.get_market_data_settings(symbol, market_status)
                        
                        # Skip weekend symbols (except futures)
                        if market_status == "weekend" and 'FUT' not in symbol:
                            failed.append(symbol)
                            continue
                        
                        contract = self.parse_symbol(symbol)
                        req_id = self._get_next_req_id()
                        
                        # Setup request tracking
                        app.data_ready_events[req_id] = threading.Event()
                        app.price_data[req_id] = {}
                        
                        # Set market data type (only once, use first symbol's type)
                        if not active_requests:
                            app.reqMarketDataType(market_data_type)
                        
                        # Request market data
                        app.reqMktData(
                            req_id,
                            contract,
                            generic_ticks,
                            False,  # snapshot
                            False,  # regulatorySnapshot
                            []  # mktDataOptions
                        )
                        
                        active_requests[symbol] = {
                            'req_id': req_id,
                            'contract': contract,
                            'market_status': market_status
                        }
                        
                        logger.debug(f"📊 Requested {symbol} with reqId {req_id}")
                        
                        # Small delay between requests to avoid overwhelming
                        time.sleep(0.1)
                        
                    except Exception as e:
                        logger.warning(f"Failed to request {symbol}: {e}")
                        failed.append(symbol)
                
                if not active_requests:
                    logger.warning("No valid symbols to request")
                    return results
                
                logger.info(f"📡 Batch requested {len(active_requests)} symbols, waiting for responses...")
                
                # Wait for all responses with timeout
                max_wait_time = 20  # seconds
                start_time = time.time()
                completed_symbols = set()
                
                while len(completed_symbols) < len(active_requests) and (time.time() - start_time) < max_wait_time:
                    # Check each active request
                    for symbol, request_info in active_requests.items():
                        if symbol in completed_symbols:
                            continue
                            
                        req_id = request_info['req_id']
                        
                        # Check if this request has data
                        if req_id in app.price_data and app.price_data[req_id]:
                            # Check if we have sufficient data
                            data = app.price_data[req_id]
                            has_last = ('last' in data and data['last'] > 0) or ('delayed_last' in data and data['delayed_last'] > 0)
                            has_bid_ask = (('bid' in data and 'ask' in data and data['bid'] > 0 and data['ask'] > 0) or 
                                          ('delayed_bid' in data and 'delayed_ask' in data and data['delayed_bid'] > 0 and data['delayed_ask'] > 0))
                            
                            if has_last or has_bid_ask:
                                # Process this symbol's data
                                try:
                                    price_data = self._process_price_data(symbol, data, request_info['market_status'])
                                    results[symbol] = price_data
                                    completed_symbols.add(symbol)
                                    logger.debug(f"✅ Completed {symbol}: ${price_data.price}")
                                except Exception as e:
                                    logger.warning(f"Failed to process {symbol}: {e}")
                                    failed.append(symbol)
                                    completed_symbols.add(symbol)
                    
                    # Small sleep to avoid busy waiting
                    time.sleep(0.1)
                
                # Cancel all remaining subscriptions and cleanup
                for symbol, request_info in active_requests.items():
                    req_id = request_info['req_id']
                    try:
                        app.cancelMktData(request_info['contract'])
                        if req_id in app.data_ready_events:
                            del app.data_ready_events[req_id]
                        if req_id in app.price_data:
                            del app.price_data[req_id]
                    except Exception as e:
                        logger.debug(f"Cleanup error for {symbol}: {e}")
                
                # Mark any symbols that didn't complete as failed
                for symbol in active_requests:
                    if symbol not in completed_symbols:
                        failed.append(symbol)
                        logger.warning(f"Timeout waiting for {symbol}")
                
            except Exception as e:
                logger.error(f"Batch request failed: {e}")
                failed.extend([s for s in symbols if s not in results])
        
        if failed:
            logger.warning(f"Failed to fetch {len(failed)} symbols: {failed}")
        
        logger.info(f"✅ Batch completed: {len(results)}/{len(symbols)} symbols successful")
        return results
    
    def _process_price_data(self, symbol: str, data: Dict, market_status: str) -> PriceData:
        """Process raw price data into PriceData object"""
        # Determine current price (check delayed ticks too)
        current_price = None
        if 'last' in data and data['last'] > 0:
            current_price = float(data['last'])
        elif 'delayed_last' in data and data['delayed_last'] > 0:
            current_price = float(data['delayed_last'])
        elif 'bid' in data and 'ask' in data and data['bid'] > 0 and data['ask'] > 0:
            current_price = float((data['bid'] + data['ask']) / 2)
        elif 'delayed_bid' in data and 'delayed_ask' in data and data['delayed_bid'] > 0 and data['delayed_ask'] > 0:
            current_price = float((data['delayed_bid'] + data['delayed_ask']) / 2)
        elif 'close' in data and data['close'] > 0:
            current_price = float(data['close'])
        elif 'delayed_close' in data and data['delayed_close'] > 0:
            current_price = float(data['delayed_close'])
        
        if current_price is None:
            raise ValueError(f"No valid price data for {symbol}")
        
        # Get change percentage
        change_pct = 0.0
        if 'change_percent' in data:
            change_pct = float(data['change_percent'])
        elif 'change_points' in data and 'close' in data and data['close'] > 0:
            # Calculate percentage from points change
            change_points = float(data['change_points'])
            prev_close = current_price - change_points
            if prev_close > 0:
                change_pct = (change_points / prev_close) * 100
        elif 'delayed_close' in data and data['delayed_close'] > 0:
            # Calculate from delayed close price
            prev_close = float(data['delayed_close'])
            if prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100
        elif 'close' in data and data['close'] > 0:
            # Calculate from regular close price
            prev_close = float(data['close'])
            if prev_close > 0:
                change_pct = ((current_price - prev_close) / prev_close) * 100
        
        # Format price based on asset type
        if 'CASH' in symbol:
            formatted_price = round(current_price, 4)
        elif 'IND' in symbol and any(x in symbol for x in ['IRX', 'FVX', 'TNX', 'TYX']):
            formatted_price = round(current_price, 3)
        else:
            formatted_price = round(current_price, 2)
        
        return PriceData(
            symbol=symbol,
            price=formatted_price,
            change_percent=round(change_pct, 2),
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            currency="USD",  # Default, could be enhanced
            volume=data.get('volume', None)
        )

# Global instance using your config
_ib_manager = None

def get_ib_manager() -> IBGatewayManager:
    """Get or create global IB manager instance using config"""
    global _ib_manager
    if _ib_manager is None:
        _ib_manager = IBGatewayManager()
    return _ib_manager

# Test function
def test_with_official_api():
    """Test with official IBAPI"""
    print(f"🧪 Testing with Official IBAPI: {IB_GATEWAY_HOST}:{IB_GATEWAY_PORT}")
    print("=" * 60)
    
    manager = get_ib_manager()
    
    # Test futures (should be active almost 24/7)
    test_symbols = ["ES-FUT-USD", "NQ-FUT-USD", "GC-FUT-USD"]
    
    for symbol in test_symbols:
        try:
            start_time = time.time()
            data = manager.get_price_data(symbol)
            elapsed = time.time() - start_time
            
            print(f"✅ {symbol:15} | ${data.price:>8} | {data.change_percent:>+6.2f}% | {elapsed:.2f}s")
            
        except Exception as e:
            print(f"❌ {symbol:15} | ERROR: {e}")
    
    # Test batch request
    print(f"\n🔄 Testing batch request...")
    try:
        start_time = time.time()
        batch_results = manager.get_multiple_prices(["ES-FUT-USD", "NQ-FUT-USD"])
        elapsed = time.time() - start_time
        
        print(f"📦 Batch results ({elapsed:.2f}s):")
        for symbol, data in batch_results.items():
            print(f"   {symbol}: ${data.price} ({data.change_percent:+.2f}%)")
            
    except Exception as e:
        print(f"❌ Batch request failed: {e}")
    
    # Cleanup
    manager.disconnect_all()

if __name__ == "__main__":
    test_with_official_api()