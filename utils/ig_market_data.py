# utils/ig_market_data.py
"""
IG Index API Client with yfinance fallback - COMPLETE MODULE
Enhanced with price normalization and better EPIC mappings
"""

import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import yfinance as yf

try:
    from trading_ig import IGService
    from trading_ig.config import config as ig_config
    IG_AVAILABLE = True
except ImportError:
    IG_AVAILABLE = False
    logging.warning("trading-ig not installed. Install with: pip install trading-ig")

from .config import (
    IG_USERNAME, IG_PASSWORD, IG_API_KEY, IG_ACC_TYPE, IG_ACC_NUMBER
)

logger = logging.getLogger(__name__)

class IGMarketDataError(Exception):
    """Base exception for IG market data errors"""
    pass

class IGConnectionError(IGMarketDataError):
    """IG API connection errors"""
    pass

class IGRateLimitError(IGMarketDataError):
    """IG API rate limit errors"""
    pass

# SPREAD BETTING IG EPIC Symbol Mapping - COMPLETE UPDATED VERSION
# CLEANED IG EPIC MAPPING - Only working EPICs
# Generated from successful test results to eliminate error spam
IG_EPIC_MAPPING = {
    # US EQUITY (all working)
    "^GSPC": "IX.D.SPTRD.DAILY.IP",
    "^IXIC": "IX.D.NASDAQ.CASH.IP", 
    "^DJI": "IX.D.DOW.DAILY.IP",
    "^RUT": "IX.D.RUSSELL.DAILY.IP",
    
    # EUROPE EQUITY (all working)
    "^GDAXI": "IX.D.DAX.DAILY.IP",
    "^FTSE": "IX.D.FTSE.DAILY.IP",
    "^STOXX50E": "IX.D.STXE.CASH.IP",
    "^FCHI": "IX.D.CAC.DAILY.IP",
    
    # ASIA EQUITY (all working)
    "^N225": "IX.D.NIKKEI.DAILY.IP",
    "^HSI": "IX.D.HANGSENG.DAILY.IP",
    "000001.SS": "IX.D.XINHUA.DFB.IP",
    "^KS11": "IX.D.EMGMKT.DFB.IP",
    
    # FOREX (all working)
    "EURUSD=X": "CS.D.EURUSD.TODAY.IP",
    "USDJPY=X": "CS.D.USDJPY.TODAY.IP",
    "GBPUSD=X": "CS.D.GBPUSD.TODAY.IP",
    "USDCHF=X": "CS.D.USDCHF.TODAY.IP",
    "AUDUSD=X": "CS.D.AUDUSD.TODAY.IP",
    "USDCAD=X": "CS.D.USDCAD.TODAY.IP",
    "EURGBP=X": "CS.D.EURGBP.TODAY.IP",
    "EURJPY=X": "CS.D.EURJPY.TODAY.IP",
    
    # COMMODITIES (all working)
    "GC=F": "CS.D.USCGC.TODAY.IP",
    "SI=F": "CS.D.USCSI.TODAY.IP",          # Spot Silver
    "CL=F": "CC.D.CL.USS.IP",               # Oil - US Crude
    "BZ=F": "CC.D.LCO.USS.IP",              # Oil - Brent Crude
    "NG=F": "CC.D.NG.USS.IP",               # Natural Gas
    "HG=F": "MT.D.HG.Month1.IP",            # High Grade Copper
    
    # RATES (all working)
    #"^TNX": "IX.D.US10Y.DAILY.IP",
    #"^IRX": "IX.D.US13W.DAILY.IP",
    #"^TYX": "IX.D.US30Y.DAILY.IP",
    
    # CRYPTO (except Bitcoin - uses yfinance)
    "ETH-USD": "CS.D.ETHEREUM.CFD.IP",
    "SOL-USD": "CS.D.SOLANA.CFD.IP",
    "XRP-USD": "CS.D.RIPPLE.CFD.IP",
    "ADA-USD": "CS.D.CARDANO.CFD.IP"
}

# REMOVE ALL ALTERNATIVES TO STOP ERROR SPAM
# Since we now have verified working EPICs, we don't need the error-prone alternatives
EPIC_ALTERNATIVES = {}

# Keep existing helper functions but remove failed EPIC retry logic

# Reverse mapping for lookups
EPIC_TO_SYMBOL = {v: k for k, v in IG_EPIC_MAPPING.items()}

class IGMarketDataClient:
    """
    IG Index API client with intelligent yfinance fallback
    Enhanced with price normalization and better error handling
    """
    
    def __init__(self, use_demo: bool = False):
        """
        Initialize IG client
        
        Args:
            use_demo: Use demo account for testing (default: False for live)
        """
        self.ig_service = None
        self.connected = False
        self.use_demo = use_demo
        self.last_request_time = 0
        self.min_request_interval = 1.5  # Seconds between requests (40/min limit)
        
        # Rate limiting counters
        self.requests_this_minute = 0
        self.minute_start_time = time.time()
        
        # Cache failed EPICs to avoid repeated attempts
        self.failed_epics = set()
        
        self._initialize_ig_service()
    
    def _initialize_ig_service(self):
        """Initialize IG Service with credentials"""
        if not IG_AVAILABLE:
            logger.warning("IG trading library not available, using yfinance only")
            return
            
        try:
            # Use environment variables or config
            username = IG_USERNAME
            password = IG_PASSWORD  
            api_key = IG_API_KEY
            acc_type = IG_ACC_TYPE or ("DEMO" if self.use_demo else "LIVE")
            
            if not all([username, password, api_key]):
                logger.warning("IG credentials not configured, using yfinance only")
                return
                
            self.ig_service = IGService(username, password, api_key, acc_type)
            logger.info(f"IG Service initialized ({acc_type} mode)")
            
        except Exception as e:
            logger.error(f"Failed to initialize IG service: {e}")
            self.ig_service = None
    
    def _connect_to_ig(self) -> bool:
        """Establish connection to IG API"""
        if not self.ig_service:
            return False
            
        try:
            if not self.connected:
                self.ig_service.create_session()
                self.connected = True
                logger.info("✅ Connected to IG API")
                
                # Switch to specified account if needed
                if hasattr(self, 'acc_number') and self.acc_number:
                    self.ig_service.switch_account(self.acc_number, False)
                    
            return True
            
        except Exception as e:
            logger.error(f"❌ IG connection failed: {e}")
            self.connected = False
            return False
    
    def _rate_limit_check(self):
        """Check and enforce rate limits (40 requests/minute)"""
        current_time = time.time()
        
        # Reset counter every minute
        if current_time - self.minute_start_time >= 60:
            self.requests_this_minute = 0
            self.minute_start_time = current_time
        
        # Enforce rate limit
        if self.requests_this_minute >= 35:  # Buffer below 40/min limit
            sleep_time = 60 - (current_time - self.minute_start_time)
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self.requests_this_minute = 0
                self.minute_start_time = time.time()
        
        # Minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
        self.requests_this_minute += 1
    
    def _normalize_ig_price(self, price: float, epic: str, symbol: str) -> float:
        """
        Normalize IG prices to standard format
        Spread betting account uses specific scaling
        """
        
        # Forex pairs with .TODAY.IP (spread betting) - divide by 10,000
        if "CS.D." in epic and ".TODAY.IP" in epic:
            # Check if it's actually a commodity (Gold, Silver, etc.)
            if any(commodity in epic.upper() for commodity in ["GOLD", "SILVER", "COPPER", "USC"]):
                # Spot commodities - return as-is, no division needed
                logger.debug(f"Spot commodity {symbol}: {price} (no normalization)")
                return price
            elif "USDJPY" in symbol:
                # USD/JPY special case: divide by 100
                normalized_price = price / 100
                logger.debug(f"Normalized USD/JPY spread bet: {price} -> {normalized_price}")
                return normalized_price
            else:
                # All other forex pairs: divide by 10,000
                normalized_price = price / 10000
                logger.debug(f"Normalized forex spread bet {symbol}: {price} -> {normalized_price}")
                return normalized_price
        
        # Forex pairs with .CFD.IP - divide by 10,000
        elif "CS.D." in epic and ".CFD.IP" in epic:
            if "USDJPY" in symbol:
                normalized_price = price / 100
                return normalized_price
            else:
                normalized_price = price / 10000
                return normalized_price
        
        # Index and commodity spread bets/CFDs - usually correct as-is
        elif "IX.D." in epic:
            return price
        
        # Default: return as-is
        return price
    
    def _symbol_to_epic(self, symbol: str) -> Optional[str]:
        """Convert yfinance symbol to IG EPIC with alternatives"""
        # Direct mapping
        if symbol in IG_EPIC_MAPPING:
            epic = IG_EPIC_MAPPING[symbol]
            
            # Check if this EPIC previously failed
            if epic in self.failed_epics:
                # Try alternatives if available
                if symbol in EPIC_ALTERNATIVES:
                    for alt_epic in EPIC_ALTERNATIVES[symbol]:
                        if alt_epic not in self.failed_epics:
                            logger.debug(f"Using alternative EPIC for {symbol}: {alt_epic}")
                            return alt_epic
                return None
            
            return epic
        
        # Handle individual stocks (if needed)
        if len(symbol) <= 5 and "." not in symbol and "=" not in symbol:
            # Individual stock - IG may have different format
            # For now, return None to use yfinance
            return None
            
        return None
    
    def _get_ig_price_with_alternatives(self, symbol: str) -> Dict[str, Union[float, str]]:
        """Try to get price from IG with alternative EPICs if needed"""
        
        # Get primary EPIC
        epic = self._symbol_to_epic(symbol)
        if not epic:
            raise IGMarketDataError(f"No IG EPIC available for {symbol}")
        
        # Try primary EPIC
        try:
            return self._get_ig_price(epic, symbol)
        except IGMarketDataError as e:
            # Mark this EPIC as failed
            self.failed_epics.add(epic)
            logger.warning(f"Primary EPIC {epic} failed for {symbol}: {e}")
            
            # Try alternatives if available
            if symbol in EPIC_ALTERNATIVES:
                for alt_epic in EPIC_ALTERNATIVES[symbol]:
                    if alt_epic not in self.failed_epics:
                        try:
                            logger.info(f"Trying alternative EPIC {alt_epic} for {symbol}")
                            return self._get_ig_price(alt_epic, symbol)
                        except IGMarketDataError as alt_e:
                            self.failed_epics.add(alt_epic)
                            logger.warning(f"Alternative EPIC {alt_epic} failed: {alt_e}")
                            continue
            
            # All EPICs failed
            raise IGMarketDataError(f"All IG EPICs failed for {symbol}")
    
    def _get_ig_price(self, epic: str, original_symbol: str) -> Dict[str, Union[float, str]]:
        """Get price from IG API with normalization"""
        self._rate_limit_check()
        
        try:
            # Ensure we're connected (re-authenticate if needed)
            if not self._connect_to_ig():
                raise IGMarketDataError(f'Failed to connect to IG API for {epic}')
            
            # Get market details
            response = self.ig_service.fetch_market_by_epic(epic)
            
            if not response or 'snapshot' not in response:
                raise IGMarketDataError(f"Invalid response for {epic}")
            
            snapshot = response['snapshot']
            
            # Extract price data
            bid = float(snapshot.get('bid', 0))
            offer = float(snapshot.get('offer', 0))
            raw_price = (bid + offer) / 2 if bid and offer else bid or offer
            
            # NORMALIZE PRICE HERE
            price = self._normalize_ig_price(raw_price, epic, original_symbol)
            
            # Calculate change percentage
            net_change = float(snapshot.get('netChange', 0))
            change_percent = float(snapshot.get('percentageChange', 0))
            
            # Get timestamp
            update_time = snapshot.get('updateTime', '')
            if not update_time:
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            result = {
                "price": round(price, 5),  # Use normalized price
                "change_percent": round(change_percent, 2),
                "timestamp": update_time,
                "source": "IG Index",
                "symbol": original_symbol,
                "epic": epic,
                "bid": bid,
                "offer": offer,
                "raw_price": raw_price  # Keep original for debugging
            }
            
            logger.debug(f"✅ IG price for {original_symbol}: ${price:.2f} ({change_percent:+.2f}%)")
            return result
            
        except Exception as e:
            logger.error(f"IG API error for {epic}: {e}")
            raise IGMarketDataError(f"IG API failed: {e}")
    
    def get_price(self, symbol: str) -> Dict[str, Union[float, str]]:
        """
        Get current price for a symbol with IG + yfinance fallback
        
        Args:
            symbol: Symbol (yfinance format like 'AAPL', '^GSPC', 'EURUSD=X')
            
        Returns:
            dict: {"price": float, "change_percent": float, "timestamp": str, "source": str}
        """
        # Try IG Index first
        try:
            if self._connect_to_ig():
                return self._get_ig_price_with_alternatives(symbol)
        except Exception as e:
            logger.warning(f"IG API failed for {symbol}: {e}")
        
        # Fallback to yfinance
        return self._get_yfinance_price(symbol)
    
    def _get_yfinance_price(self, symbol: str) -> Dict[str, Union[float, str]]:
        """Get price from yfinance (fallback)"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period="2d")
            
            if hist.empty:
                raise Exception(f"No data for {symbol}")
            
            current_price = float(hist['Close'].iloc[-1])
            prev_price = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
            
            change_percent = ((current_price - prev_price) / prev_price * 100) if prev_price else 0
            
            result = {
                "price": round(current_price, 4),
                "change_percent": round(change_percent, 2),
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source": "yfinance",
                "symbol": symbol
            }
            
            logger.debug(f"✅ yfinance price for {symbol}: ${current_price:.2f} ({change_percent:+.2f}%)")
            return result
            
        except Exception as e:
            logger.error(f"yfinance failed for {symbol}: {e}")
            return {
                "price": 0.0,
                "change_percent": 0.0,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source": "error",
                "symbol": symbol,
                "error": str(e)
            }
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get prices for multiple symbols efficiently
        
        Args:
            symbols: List of symbols to fetch
            
        Returns:
            Dict mapping symbols to price data
        """
        results = {}
        
        # Separate IG-compatible vs yfinance-only symbols
        ig_symbols = []
        yf_symbols = []
        
        for symbol in symbols:
            if self._symbol_to_epic(symbol):
                ig_symbols.append(symbol)
            else:
                yf_symbols.append(symbol)
        
        # Process IG symbols
        for symbol in ig_symbols:
            try:
                results[symbol] = self.get_price(symbol)
            except Exception as e:
                logger.error(f"Failed to get price for {symbol}: {e}")
                results[symbol] = self._get_yfinance_price(symbol)
        
        # Batch process yfinance symbols
        if yf_symbols:
            yf_results = self._get_yfinance_multiple(yf_symbols)
            results.update(yf_results)
        
        return results
    
    def _get_yfinance_multiple(self, symbols: List[str]) -> Dict[str, Dict]:
        """Efficiently get multiple prices from yfinance"""
        results = {}
        
        try:
            # Use yfinance's download function for batch processing
            data = yf.download(symbols, period="2d", interval="1d", group_by="ticker")
            
            for symbol in symbols:
                try:
                    if len(symbols) == 1:
                        symbol_data = data
                    else:
                        symbol_data = data[symbol] if symbol in data.columns.levels[0] else None
                    
                    if symbol_data is not None and not symbol_data.empty:
                        current_price = float(symbol_data['Close'].iloc[-1])
                        prev_price = float(symbol_data['Close'].iloc[-2]) if len(symbol_data) > 1 else current_price
                        change_percent = ((current_price - prev_price) / prev_price * 100) if prev_price else 0
                        
                        results[symbol] = {
                            "price": round(current_price, 4),
                            "change_percent": round(change_percent, 2),
                            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "source": "yfinance_batch",
                            "symbol": symbol
                        }
                    else:
                        results[symbol] = self._get_yfinance_price(symbol)
                        
                except Exception as e:
                    logger.error(f"Error processing {symbol} in batch: {e}")
                    results[symbol] = self._get_yfinance_price(symbol)
        
        except Exception as e:
            logger.error(f"Batch yfinance download failed: {e}")
            # Fall back to individual requests
            for symbol in symbols:
                results[symbol] = self._get_yfinance_price(symbol)
        
        return results
    
    def get_historical_data(self, symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
        """
        Get historical data with IG + yfinance fallback
        
        Args:
            symbol: Symbol to fetch
            period: Period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            
        Returns:
            DataFrame with OHLCV data
        """
        # Try IG Index first for supported symbols
        try:
            if self._connect_to_ig():
                epic = self._symbol_to_epic(symbol)
                if epic and epic not in self.failed_epics:
                    return self._get_ig_historical(epic, period)
        except Exception as e:
            logger.warning(f"IG historical data failed for {symbol}: {e}")
        
        # Fallback to yfinance
        return self._get_yfinance_historical(symbol, period)
    
    def _get_ig_historical(self, epic: str, period: str) -> Optional[pd.DataFrame]:
        """Get historical data from IG API"""
        self._rate_limit_check()
        
        try:
            # Convert period to IG format
            resolution = "D"  # Daily
            num_points = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}.get(period, 365)
            
            response = self.ig_service.fetch_historical_prices_by_epic_and_num_points(
                epic, resolution, num_points
            )
            
            if 'prices' in response:
                prices = response['prices']
                if 'ask' in prices:
                    df = prices['ask'].copy()
                    df.columns = ['Open', 'High', 'Low', 'Close']
                    return df
            
            return None
            
        except Exception as e:
            logger.error(f"IG historical data error for {epic}: {e}")
            return None
    
    def _get_yfinance_historical(self, symbol: str, period: str) -> Optional[pd.DataFrame]:
        """Get historical data from yfinance"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            return data
        except Exception as e:
            logger.error(f"yfinance historical data failed for {symbol}: {e}")
            return None
    
    def get_market_status(self) -> Dict[str, str]:
        """Get current market status"""
        try:
            if self._connect_to_ig():
                # IG doesn't have a direct market status endpoint
                # We can infer from successful price fetches
                test_epic = "IX.D.SPTRD.DAILY.IP"  # S&P 500
                response = self.ig_service.fetch_market_by_epic(test_epic)
                if response and 'snapshot' in response:
                    return {"status": "open", "source": "IG Index"}
        except:
            pass
        
        # Fallback - check major market hours
        now = datetime.now()
        weekday = now.weekday()  # 0 = Monday, 6 = Sunday
        
        if weekday < 5:  # Monday to Friday
            return {"status": "likely_open", "source": "time_based"}
        else:
            return {"status": "likely_closed", "source": "time_based"}
    
    def get_epic_info(self, symbol: str) -> Optional[Dict]:
        """Get EPIC information for debugging"""
        epic = self._symbol_to_epic(symbol)
        if epic:
            return {
                "symbol": symbol,
                "epic": epic,
                "alternatives": EPIC_ALTERNATIVES.get(symbol, []),
                "failed": epic in self.failed_epics
            }
        return None
    
    def clear_failed_epics(self):
        """Clear the failed EPICs cache - useful for retrying"""
        self.failed_epics.clear()
        logger.info("Cleared failed EPICs cache")
    
    def disconnect(self):
        """Clean disconnect from IG API"""
        if self.ig_service and self.connected:
            try:
                # IG API doesn't have explicit disconnect
                self.connected = False
                logger.info("Disconnected from IG API")
            except Exception as e:
                logger.error(f"Error disconnecting from IG: {e}")

# Global client instance
_ig_client = None

def get_ig_client(use_demo: bool = False) -> IGMarketDataClient:
    """Get or create global IG client instance"""
    global _ig_client
    if _ig_client is None:
        _ig_client = IGMarketDataClient(use_demo=use_demo)
    return _ig_client