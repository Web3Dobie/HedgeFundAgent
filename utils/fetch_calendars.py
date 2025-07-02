import requests
from datetime import datetime, timedelta
import finnhub
import os
from dotenv import load_dotenv
import pandas as pd
from utils.config import FINNHUB_API_KEY

load_dotenv()

finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

def get_econ_calendar_tradingview(countries=None, days=1):
    """
    Fetch economic calendar data from TradingView internal API (no key required).
    Returns a DataFrame of upcoming economic events.
    """
    url = "https://economic-calendar.tradingview.com/events"
    today = pd.Timestamp.today().normalize()
    payload = {
        "from": (today + pd.Timedelta(hours=23)).isoformat() + ".000Z",
        "to": (today + pd.Timedelta(days=days) + pd.Timedelta(hours=22)).isoformat() + ".000Z",
    }
    if countries:
        payload["countries"] = ",".join(countries)
    headers = {"Origin": "https://in.tradingview.com"}
    try:
        resp = requests.get(url, headers=headers, params=payload)
        resp.raise_for_status()
        return pd.DataFrame(resp.json().get("result", []))
    except Exception as e:
        print(f"Error fetching TradingView econ calendar: {e}")
        return pd.DataFrame()

def get_ipo_calendar(start_date: str = None, end_date: str = None) -> list:
    """
    Fetches IPO calendar from Finnhub for the next 14 days.
    """
    if not start_date:
        start_date = datetime.utcnow().date().isoformat()
    if not end_date:
        end_date = (datetime.utcnow().date() + timedelta(days=14)).isoformat()

    try:
        return finnhub_client.ipo_calendar(_from=start_date, to=end_date).get("ipoCalendar", [])
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
        return finnhub_client.earnings_calendar(
            _from=start_date, to=end_date, symbol="", international=False
        ).get("earningsCalendar", [])
    except Exception as e:
        print(f"Error fetching earnings calendar: {e}")
        return []