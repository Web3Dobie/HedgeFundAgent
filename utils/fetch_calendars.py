# utils/fetch_calendars.py
"""
Enhanced calendar fetching module with Financial Modeling Prep Economic Calendar API
Replaces unreliable scraping with professional API
"""

import requests
from datetime import datetime, timedelta
import finnhub
import os
import json
import pandas as pd
from dotenv import load_dotenv
import sys

# Fix import path when running directly
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from utils.config import FINNHUB_API_KEY
except ImportError:
    # Fallback when running directly - load from environment
    load_dotenv()
    FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

load_dotenv()

# Financial Modeling Prep API Key (add to your .env file)
FMP_API_KEY = os.getenv("FMP_API_KEY")  # Add this to your .env file
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

def get_ipo_calendar(start_date: str = None, end_date: str = None) -> list:
    """
    Fetches IPO calendar from Finnhub for the next 14 days.
    """
    if not start_date:
        start_date = datetime.utcnow().date().isoformat()
    if not end_date:
        end_date = (datetime.utcnow().date() + timedelta(days=14)).isoformat()

    try:
        result = finnhub_client.ipo_calendar(_from=start_date, to=end_date)
        return result.get("ipoCalendar", [])
    except Exception as e:
        print(f"Error fetching IPO calendar: {e}")
        return []

def get_earnings_calendar(start_date: str = None, end_date: str = None) -> list:
    """
    Fetches earnings calendar from Finnhub within the given date range.
    """
    if not start_date:
        start_date = datetime.utcnow().date().isoformat()
    if not end_date:
        end_date = start_date

    try:
        result = finnhub_client.earnings_calendar(
            _from=start_date, to=end_date, symbol="", international=False
        )
        return result.get("earningsCalendar", [])
    except Exception as e:
        print(f"Error fetching earnings calendar: {e}")
        return []

def get_fmp_economic_calendar(start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    Fetches economic calendar from Financial Modeling Prep API
    Free tier: 250 calls/day - perfect for 1-2 daily briefings
    """
    if not FMP_API_KEY:
        print("❌ FMP_API_KEY not found in environment variables")
        return pd.DataFrame()
    
    if not start_date:
        start_date = datetime.utcnow().date().isoformat()
    if not end_date:
        # Get events for today + next 2 days to capture all relevant events
        end_date = (datetime.utcnow().date() + timedelta(days=2)).isoformat()
    
    url = f"{FMP_BASE_URL}/economic_calendar"
    params = {
        "from": start_date,
        "to": end_date,
        "apikey": FMP_API_KEY
    }
    
    try:
        print(f"📡 Fetching FMP economic calendar from {start_date} to {end_date}...")
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if not data or not isinstance(data, list):
            print("⚠️ FMP returned empty or invalid economic calendar data")
            return pd.DataFrame()
        
        # Process the data into our standard format
        events = []
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        
        for event in data:
            try:
                # Parse the event data
                event_name = event.get('event', '').strip()
                country = event.get('country', 'Unknown')
                currency = get_currency_from_country(country)
                
                # Handle date/time - FMP uses UTC
                event_date = event.get('date', '')
                if event_date:
                    # Convert to our standard format if needed
                    try:
                        event_datetime = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                        time_str = event_datetime.strftime('%H:%M')
                        date_str = event_datetime.strftime('%Y-%m-%d')
                    except:
                        time_str = "TBD"
                        date_str = today_str
                else:
                    time_str = "TBD"
                    date_str = today_str
                
                # Get values (handle different possible formats)
                actual = str(event.get('actual', '')).strip() or '-'
                forecast = str(event.get('estimate', '') or event.get('forecast', '')).strip() or '-'
                previous = str(event.get('previous', '')).strip() or '-'
                
                # Only include meaningful events
                if event_name and len(event_name) > 3:
                    events.append({
                        "date": date_str,
                        "time": time_str,
                        "currency": currency,
                        "event": event_name[:70],  # Truncate long names
                        "actual": actual,
                        "forecast": forecast,
                        "previous": previous,
                        "country": country[:20]  # Add country for reference
                    })
            except Exception as e:
                print(f"⚠️ Error processing event: {e}")
                continue
        
        if events:
            df = pd.DataFrame(events)
            # Sort by time, with TBD times at the end
            df['sort_time'] = df['time'].apply(lambda x: '99:99' if x == 'TBD' else x)
            df = df.sort_values(['date', 'sort_time']).drop('sort_time', axis=1)
            
            print(f"✅ FMP economic calendar: {len(df)} events fetched")
            return df
        else:
            print("⚠️ No valid events found in FMP response")
            return pd.DataFrame()
            
    except requests.exceptions.RequestException as e:
        print(f"❌ FMP API request failed: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"❌ FMP economic calendar error: {e}")
        return pd.DataFrame()

def get_currency_from_country(country: str) -> str:
    """
    Map country names to their primary currencies
    """
    country_currency_map = {
        'United States': 'USD',
        'US': 'USD',
        'USA': 'USD',
        'Eurozone': 'EUR',
        'Germany': 'EUR',
        'France': 'EUR',
        'Italy': 'EUR',
        'Spain': 'EUR',
        'United Kingdom': 'GBP',
        'UK': 'GBP',
        'Japan': 'JPY',
        'Canada': 'CAD',
        'Australia': 'AUD',
        'Switzerland': 'CHF',
        'New Zealand': 'NZD',
        'China': 'CNY',
        'South Korea': 'KRW',
        'India': 'INR',
        'Brazil': 'BRL',
        'Mexico': 'MXN',
        'Russia': 'RUB',
        'South Africa': 'ZAR'
    }
    
    for country_key, currency in country_currency_map.items():
        if country_key.lower() in country.lower():
            return currency
    
    return 'USD'  # Default fallback

def scrape_investing_econ_calendar():
    """
    Updated main function that uses FMP API instead of unreliable scraping
    Falls back to hardcoded major events if API fails
    """
    print("📅 Fetching economic calendar from Financial Modeling Prep API...")
    
    # Try FMP API first
    df = get_fmp_economic_calendar()
    
    if not df.empty:
        print(f"✅ Successfully fetched {len(df)} economic events from FMP")
        return df
    
    # Fallback to hardcoded major events for current week
    print("⚠️ FMP API failed, using fallback major events...")
    return get_fallback_economic_events()

def get_fallback_economic_events() -> pd.DataFrame:
    """
    Hardcoded major economic events as fallback when APIs fail
    Updated weekly with key events
    """
    today = datetime.utcnow().date()
    today_str = today.isoformat()
    
    # Major recurring events - update weekly
    major_events = [
        {
            "date": today_str,
            "time": "08:30",
            "currency": "USD",
            "event": "US Non-Farm Payrolls (Check if First Friday)",
            "actual": "-",
            "forecast": "-",
            "previous": "-"
        },
        {
            "date": today_str,
            "time": "08:30",
            "currency": "USD",
            "event": "US Consumer Price Index (Check if Mid Month)",
            "actual": "-",
            "forecast": "-",
            "previous": "-"
        },
        {
            "date": today_str,
            "time": "14:00",
            "currency": "USD",
            "event": "Federal Reserve Announcements (Check Fed Calendar)",
            "actual": "-",
            "forecast": "-",
            "previous": "-"
        },
        {
            "date": today_str,
            "time": "09:00",
            "currency": "EUR",
            "event": "Eurozone Economic Data Releases",
            "actual": "-",
            "forecast": "-",
            "previous": "-"
        },
        {
            "date": today_str,
            "time": "TBD",
            "currency": "USD",
            "event": "Check Financial Modeling Prep API Status",
            "actual": "-",
            "forecast": "API should be working",
            "previous": "-"
        }
    ]
    
    df = pd.DataFrame(major_events)
    print(f"✅ Fallback calendar: {len(df)} major events")
    return df

# Test function for FMP API
def test_fmp_economic_calendar():
    """
    Test function to verify FMP economic calendar is working
    """
    print("🧪 Testing FMP Economic Calendar API...")
    
    if not FMP_API_KEY:
        print("❌ FMP_API_KEY not set in environment variables")
        print("Add FMP_API_KEY=your_key_here to your .env file")
        return False
    
    try:
        df = get_fmp_economic_calendar()
        if not df.empty:
            print(f"✅ Test successful: {len(df)} events found")
            print("\nSample events:")
            print(df[['time', 'currency', 'event', 'country']].head())
            return True
        else:
            print("⚠️ Test returned empty results")
            return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

# Main test
if __name__ == "__main__":
    print("Testing Enhanced Economic Calendar with FMP API...")
    
    # Test FMP API
    test_fmp_economic_calendar()
    
    print("\n" + "="*50)
    
    # Test main function
    econ_df = scrape_investing_econ_calendar()
    print(f"\nMain function result: {len(econ_df)} events")
    if not econ_df.empty:
        print("\nFirst 5 events:")
        print(econ_df[['time', 'currency', 'event']].head())
    
    # Test other calendars
    print(f"\n📊 IPO calendar: {len(get_ipo_calendar())} IPOs")
    print(f"📊 Earnings calendar: {len(get_earnings_calendar())} earnings")