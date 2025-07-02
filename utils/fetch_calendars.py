import requests
from datetime import datetime, timedelta
import finnhub
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import pandas as pd
from utils.config import FINNHUB_API_KEY

load_dotenv()

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

def scrape_investing_econ_calendar():
    url = "https://www.investing.com/economic-calendar/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"id": "economicCalendarData"})
    rows = table.find_all("tr", {"class": ["js-event-item", "js-first-row"]})

    today_str = pd.Timestamp.utcnow().strftime('%Y-%m-%d')
       
    data = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 7:
            continue

        event = {
            "date": today_str,
            "time": cols[0].get_text(strip=True),
            "currency": cols[1].get_text(strip=True),
            "event": cols[3].get_text(strip=True),
            "actual": cols[4].get_text(strip=True),
            "forecast": cols[5].get_text(strip=True),
            "previous": cols[6].get_text(strip=True),
        }
        data.append(event)

    df = pd.DataFrame(data)
    return df


if __name__ == "__main__":
    df = scrape_investing_econ_calendar()
    print(df.head())