# utils/csharp_rest_client.py
"""
Python client for C# IB Gateway REST API
Replaces direct IB Gateway connection with REST API calls
"""

import requests
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional, List, Union
from dataclasses import dataclass, asdict
import json
from urllib.parse import urljoin

from utils.config import IB_GATEWAY_HOST, IB_GATEWAY_PORT

logger = logging.getLogger(__name__)

@dataclass
class PriceData:
    """Structured price data response matching C# API"""
    symbol: str
    price: float
    change_percent: float = 0.0
    timestamp: str = ""
    currency: str = "USD"
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None

class CSharpRestApiClient:
    """
    Python client for C# IB Gateway REST API
    Provides the same interface as the old IB client but uses REST calls
    """
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        """
        Initialize the REST API client
        
        Args:
            base_url: Base URL for the C# API (e.g., "http://localhost:5000")
            timeout: Request timeout in seconds
        """
        if base_url is None:
            # Both Python client and C# REST API are on 10.0.0.5
            # Use localhost for optimal performance and reliability
            base_url = f"http://localhost:5090"
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        logger.info(f"🔗 Initialized C# REST API client: {self.base_url}")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make HTTP request to the C# API with error handling
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON as dictionary
            
        Raises:
            ConnectionError: If API is unreachable
            ValueError: If API returns error response
        """
        url = urljoin(self.base_url + "/", endpoint.lstrip('/'))
        
        try:
            logger.debug(f"🌐 {method} {url}")
            
            response = self.session.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )
            
            # Check if response is successful
            response.raise_for_status()
            
            # Parse JSON response
            try:
                data = response.json()
            except json.JSONDecodeError:
                logger.error(f"❌ Invalid JSON response from {url}")
                raise ValueError("Invalid JSON response from API")
            
            logger.debug(f"✅ API Response: {data}")
            return data
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Connection failed to {url}: {e}")
            raise ConnectionError(f"Cannot connect to C# API at {url}")
            
        except requests.exceptions.Timeout as e:
            logger.error(f"⏰ Request timeout to {url}: {e}")
            raise ConnectionError(f"Request timeout to C# API")
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ HTTP error {e.response.status_code} from {url}")
            try:
                error_data = e.response.json()
                error_msg = error_data.get('message', str(e))
            except:
                error_msg = str(e)
            raise ValueError(f"API error: {error_msg}")
    
    def get_status(self) -> Dict:
        """
        Get API and IB Gateway connection status
        
        Returns:
            Status information dictionary
        """
        try:
            return self._make_request('GET', '/api/marketdata/status')
        except Exception as e:
            logger.error(f"❌ Status check failed: {e}")
            return {
                'connected': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def connect(self) -> bool:
        """
        Connect to IB Gateway through the C# API
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self._make_request('POST', '/api/marketdata/connect')
            
            # Check various possible response formats
            if isinstance(response, dict):
                status = response.get('status', '')
                connected = status in ['connected', 'already_connected']
                
                if connected:
                    logger.info("✅ IB Gateway connected via C# API")
                    return True
                else:
                    logger.warning(f"⚠️ Connection failed: {response}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from IB Gateway through the C# API
        
        Returns:
            True if disconnection successful, False otherwise
        """
        try:
            response = self._make_request('POST', '/api/marketdata/disconnect')
            logger.info("🔌 Disconnected from IB Gateway")
            return True
            
        except Exception as e:
            logger.error(f"❌ Disconnect failed: {e}")
            return False
    
    def get_market_data(self, symbol: str) -> PriceData:
        """
        Get market data for a symbol using the new universal /price/ endpoint
        
        Args:
            symbol: Stock symbol (e.g., "AAPL", "FDAX-FUT-EUR", "ES-FUT-USD")
            
        Returns:
            PriceData object with current market information
        """
        try:
            # Use the new universal /price/ endpoint that handles all symbol types
            # including international futures with proper exchange/currency mapping
            endpoint = f'/api/marketdata/price/{symbol}'
            
            logger.info(f"📊 Requesting market data: {endpoint}")
            response = self._make_request('GET', endpoint)
            
            # Parse response into PriceData
            if isinstance(response, dict):
                # Handle both old and new response formats
                price = response.get('price', 0)
                if price == 0:
                    # Fallback to other price fields
                    price = response.get('currentPrice', response.get('lastPrice', 0))
                
                change_percent = response.get('change_percent', response.get('changePercent', 0))
                
                # Extract currency and exchange info from new endpoint
                currency = response.get('currency', 'USD')
                exchange = response.get('exchange', 'SMART')
                
                logger.info(f"✅ {symbol}: ${price} ({change_percent:+.2f}%) [{currency}@{exchange}]")
                
                return PriceData(
                    symbol=symbol,
                    price=float(price),
                    change_percent=round(change_percent, 2),
                    timestamp=response.get('timestamp', response.get('lastUpdate', datetime.now().isoformat())),
                    currency=currency,
                    volume=response.get('volume'),
                    bid=response.get('bid', response.get('bidPrice')) if response.get('bid', response.get('bidPrice', 0)) > 0 else None,
                    ask=response.get('ask', response.get('askPrice')) if response.get('ask', response.get('askPrice', 0)) > 0 else None,
                    last=response.get('last', response.get('lastPrice')) if response.get('last', response.get('lastPrice', 0)) > 0 else None,
                    bid_size=response.get('bid_size', response.get('bidSize')) if response.get('bid_size', response.get('bidSize', 0)) > 0 else None,
                    ask_size=response.get('ask_size', response.get('askSize')) if response.get('ask_size', response.get('askSize', 0)) > 0 else None
                )
            
            else:
                logger.warning(f"⚠️ Unexpected response format for {symbol}: {response}")
                raise ValueError(f"Unexpected API response format: {type(response)}")
                
        except Exception as e:
            logger.error(f"❌ Market data failed for {symbol}: {e}")
            raise
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, PriceData]:
        """
        Get market data for multiple symbols
        
        Args:
            symbols: List of symbols to fetch
            
        Returns:
            Dictionary mapping symbols to PriceData objects
        """
        results = {}
        
        for symbol in symbols:
            try:
                data = self.get_market_data(symbol)
                results[symbol] = data
                
                # Small delay to avoid overwhelming the API
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"❌ Failed to get data for {symbol}: {e}")
                # Continue with other symbols
                continue
        
        return results
    
    def health_check(self) -> bool:
        """
        Check if the C# API is healthy and responding
        
        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = self._make_request('GET', '/health')
            
            if isinstance(response, dict):
                status = response.get('status', '').lower()
                return status == 'healthy'
            
            return True  # If we got a response, assume healthy
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return False


class RestApiMarketDataClient:
    """
    Market data client that replaces the old IB Gateway client
    Provides the same interface but uses the C# REST API
    """
    
    def __init__(self, api_url: Optional[str] = None):
        """Initialize the market data client"""
        self.api_client = CSharpRestApiClient(api_url)
        self._connected = False
        logger.info("🚀 Initialized REST API Market Data Client")
    
    def connect(self) -> bool:
        """Connect to market data service"""
        try:
            # Check health first
            if not self.api_client.health_check():
                logger.error("❌ C# API is not healthy")
                return False
            
            # Connect to IB Gateway
            self._connected = self.api_client.connect()
            
            if self._connected:
                logger.info("✅ Connected to market data service")
            else:
                logger.error("❌ Failed to connect to market data service")
            
            return self._connected
            
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Disconnect from market data service"""
        try:
            self.api_client.disconnect()
            self._connected = False
            logger.info("🔌 Disconnected from market data service")
        except Exception as e:
            logger.error(f"❌ Disconnect failed: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to market data service"""
        if not self._connected:
            return False
        
        try:
            # Quick status check
            status = self.api_client.get_status()
            return status.get('connected', False)
        except:
            self._connected = False
            return False
    
    def get_price(self, symbol: str) -> Dict:
        """
        Get current price for a symbol (compatible with old interface)
        
        Args:
            symbol: Symbol to fetch (e.g., "AAPL", "FDAX-FUT-EUR", "ES-FUT-USD")
            
        Returns:
            Dictionary with price data (compatible with old format)
        """
        try:
            # Auto-connect if needed
            if not self.is_connected():
                logger.info("🔄 Auto-connecting to market data service...")
                if not self.connect():
                    raise ConnectionError("Failed to connect to market data service")
            
            # Get data from API
            price_data = self.api_client.get_market_data(symbol)
            
            # Convert to old interface format for backward compatibility
            return {
                'symbol': price_data.symbol,
                'price': price_data.price,
                'change_percent': price_data.change_percent,
                'timestamp': price_data.timestamp,
                'currency': price_data.currency,
                'volume': price_data.volume,
                'bid': price_data.bid,
                'ask': price_data.ask,
                'last': price_data.last
            }
            
        except Exception as e:
            logger.error(f"❌ Price fetch failed for {symbol}: {e}")
            raise
    
    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices for multiple symbols (compatible with old interface)"""
        try:
            if not self.is_connected():
                if not self.connect():
                    raise ConnectionError("Failed to connect to market data service")
            
            # Get data from API
            api_results = self.api_client.get_multiple_prices(symbols)
            
            # Convert to old interface format
            results = {}
            for symbol, price_data in api_results.items():
                results[symbol] = {
                    'symbol': price_data.symbol,
                    'price': price_data.price,
                    'change_percent': price_data.change_percent,
                    'timestamp': price_data.timestamp,
                    'currency': price_data.currency,
                    'volume': price_data.volume,
                    'bid': price_data.bid,
                    'ask': price_data.ask,
                    'last': price_data.last
                }
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Multiple price fetch failed: {e}")
            raise
    
    def test_connection(self) -> Dict:
        """Test the connection and return results"""
        test_results = {
            "api_healthy": False,
            "ib_connected": False,
            "test_symbols": {},
            "errors": []
        }
        
        try:
            # Test API health
            test_results["api_healthy"] = self.api_client.health_check()
            
            if test_results["api_healthy"]:
                # Test IB connection
                if self.connect():
                    test_results["ib_connected"] = True
                    
                    # Test a mix of US and international symbols
                    test_symbols = ["AAPL", "ES-FUT-USD", "FDAX-FUT-EUR", "HSI-FUT-HKD"]
                    
                    for symbol in test_symbols:
                        try:
                            start_time = time.time()
                            data = self.get_price(symbol)
                            elapsed = time.time() - start_time
                            
                            test_results["test_symbols"][symbol] = {
                                "success": True,
                                "price": data["price"],
                                "change_percent": data["change_percent"],
                                "currency": data.get("currency", "USD"),
                                "response_time": round(elapsed, 2)
                            }
                        except Exception as e:
                            test_results["test_symbols"][symbol] = {
                                "success": False,
                                "error": str(e)
                            }
                            test_results["errors"].append(f"{symbol}: {str(e)}")
                else:
                    test_results["errors"].append("Failed to connect to IB Gateway via API")
            else:
                test_results["errors"].append("C# API health check failed")
                
        except Exception as e:
            test_results["errors"].append(f"Connection test failed: {str(e)}")
        
        return test_results


# Global instance for backward compatibility
_rest_client = None

def get_rest_client() -> RestApiMarketDataClient:
    """Get or create global REST client instance"""
    global _rest_client
    if _rest_client is None:
        _rest_client = RestApiMarketDataClient()
    return _rest_client

# Backward compatibility functions (drop-in replacements)
def fetch_last_price(symbol: str) -> dict:
    """Fetch latest price data using REST API (compatible with old interface)"""
    return get_rest_client().get_price(symbol)

def get_price_data(symbol: str) -> dict:
    """Get price data using REST API"""
    return get_rest_client().get_price(symbol)

def get_multiple_prices(symbols: List[str]) -> Dict[str, dict]:
    """Get multiple prices using REST API"""
    return get_rest_client().get_multiple_prices(symbols)

def test_rest_api_connection():
    """Test the REST API connection"""
    client = get_rest_client()
    return client.test_connection()


if __name__ == "__main__":
    # Test the REST API integration
    print("🧪 Testing C# REST API Integration")
    print("=" * 50)
    
    # Test connection
    results = test_rest_api_connection()
    
    print(f"API Healthy: {'✅' if results['api_healthy'] else '❌'}")
    print(f"IB Connected: {'✅' if results['ib_connected'] else '❌'}")
    
    if results['test_symbols']:
        print("\nSymbol Tests:")
        for symbol, data in results['test_symbols'].items():
            if data['success']:
                currency = data.get('currency', 'USD')
                print(f"✅ {symbol}: {currency} {data['price']} ({data['change_percent']:+.2f}%) - {data['response_time']}s")
            else:
                print(f"❌ {symbol}: {data['error']}")
    
    if results['errors']:
        print(f"\nErrors: {results['errors']}")