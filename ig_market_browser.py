# ig_market_browser.py
"""
Simple IG Market Browser - Find EPICs for specific instruments
Searches for your failing symbols and returns exact EPIC codes
"""

import logging
from typing import Dict, List, Optional
from utils.ig_market_data import get_ig_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IGMarketBrowser:
    def __init__(self):
        """Initialize with working IG client"""
        self.ig_client = get_ig_client()
        self.found_epics = {}
    
    def search_instrument(self, search_term: str) -> List[Dict]:
        """Search for instruments and return results"""
        try:
            # Ensure connection using your working pattern
            if not self.ig_client.ig_service:
                logger.error("IG service not initialized")
                return []
                
            if not self.ig_client.connected:
                logger.info("Creating IG session...")
                self.ig_client.ig_service.create_session()
                self.ig_client.connected = True
                logger.info("✅ Connected to IG API")
            
            # Search markets
            logger.info(f"Searching for: '{search_term}'")
            results = self.ig_client.ig_service.search_markets(search_term)
            
            if 'markets' in results:
                instruments = []
                for market in results['markets']:
                    instruments.append({
                        'epic': market.get('epic'),
                        'instrument_name': market.get('instrumentName'),
                        'market_name': market.get('marketName'),
                        'instrument_type': market.get('instrumentType'),
                        'currency': market.get('currency')
                    })
                return instruments
            else:
                logger.warning(f"No 'markets' key in results for '{search_term}'")
                return []
                
        except Exception as e:
            logger.error(f"Search failed for '{search_term}': {e}")
            return []
    
    def find_failing_symbol_epics(self) -> Dict[str, str]:
        """Find EPICs for all your failing symbols"""
        
        # Map failing symbols to search terms
        search_mapping = {
            "000001.SS": ["China A50", "A50", "China"],
            "^STOXX50E": ["Euro Stoxx", "STOXX50", "EU Stocks 50"],
            "GC=F": ["Gold", "Spot Gold"],
            "SI=F": ["Silver", "Spot Silver"],
            "CL=F": ["Oil", "Crude Oil", "WTI"],
            "BZ=F": ["Brent", "Brent Oil", "Brent Crude"],
            "NG=F": ["Natural Gas", "Gas"],
            "HG=F": ["Copper", "High Grade Copper"],
            "^KS11": ["KOSPI", "Korea"]
        }
        
        found_epics = {}
        
        for symbol, search_terms in search_mapping.items():
            logger.info(f"\n{'='*50}")
            logger.info(f"Finding EPIC for {symbol}")
            logger.info(f"{'='*50}")
            
            for search_term in search_terms:
                results = self.search_instrument(search_term)
                
                if results:
                    logger.info(f"✅ Found {len(results)} results for '{search_term}':")
                    
                    for i, result in enumerate(results[:3]):  # Show top 3
                        logger.info(f"  {i+1}. {result['instrument_name']}")
                        logger.info(f"     EPIC: {result['epic']}")
                        logger.info(f"     Type: {result['instrument_type']}")
                        logger.info(f"     Currency: {result['currency']}")
                    
                    # Auto-select first result as most likely
                    if results[0]['epic']:
                        found_epics[symbol] = results[0]['epic']
                        logger.info(f"  → Selected: {results[0]['epic']}")
                        break
                else:
                    logger.info(f"❌ No results for '{search_term}'")
            
            if symbol not in found_epics:
                logger.warning(f"❌ No EPIC found for {symbol}")
        
        return found_epics
    
    def test_epic(self, epic: str) -> bool:
        """Test if an EPIC works by fetching price"""
        try:
            # Ensure session is maintained
            if not self.ig_client.connected:
                logger.info("Reconnecting to IG...")
                self.ig_client.ig_service.create_session()
                self.ig_client.connected = True
                
            response = self.ig_client.ig_service.fetch_market_by_epic(epic)
            if response and 'snapshot' in response:
                snapshot = response['snapshot']
                bid = snapshot.get('bid')
                offer = snapshot.get('offer')
                if bid or offer:
                    return True
            return False
        except Exception as e:
            logger.error(f"EPIC test failed for {epic}: {e}")
            return False
    
    def validate_epics(self, epics: Dict[str, str]) -> Dict[str, str]:
        """Test all found EPICs to confirm they work"""
        working_epics = {}
        
        logger.info(f"\n{'='*50}")
        logger.info("TESTING FOUND EPICs")
        logger.info(f"{'='*50}")
        
        for symbol, epic in epics.items():
            logger.info(f"Testing {symbol} → {epic}")
            if self.test_epic(epic):
                logger.info(f"✅ WORKS!")
                working_epics[symbol] = epic
            else:
                logger.info(f"❌ Failed")
        
        return working_epics

def main():
    """Find EPICs for failing symbols"""
    print("🔍 IG Market Browser - Finding EPICs for failing symbols")
    print("="*60)
    
    browser = IGMarketBrowser()
    
    # Find EPICs
    found_epics = browser.find_failing_symbol_epics()
    
    if not found_epics:
        print("\n❌ No EPICs found - check IG connection")
        return
    
    # Test EPICs
    working_epics = browser.validate_epics(found_epics)
    
    # Results
    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")
    
    if working_epics:
        print(f"✅ CONFIRMED WORKING EPICs ({len(working_epics)}):")
        print("\n# Add these to your IG_EPIC_MAPPING:")
        for symbol, epic in working_epics.items():
            print(f'    "{symbol}": "{epic}",')
        
        print(f"\n🎯 SUCCESS: {len(working_epics)} symbols will use IG")
    else:
        print("❌ No working EPICs found")
    
    failed_symbols = {"000001.SS", "^STOXX50E", "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "^KS11"} - set(working_epics.keys())
    if failed_symbols:
        print(f"\n❌ FALLBACK TO YFINANCE ({len(failed_symbols)}):")
        for symbol in failed_symbols:
            print(f"    # {symbol}")
    
    return working_epics

if __name__ == "__main__":
    main()