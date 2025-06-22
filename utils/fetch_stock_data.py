import yfinance as yf   # Used for fetching historial stock data
import pandas as pd     # Used for data manipulation and analysis
import requests         # Used for making HTTP requests to external APIs
import os               # Used for environment variable management

from dotenv import load_dotenv
from utils.config import (FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY)

# Load environment variables from .env
load_dotenv()


def fetch_ticker_data(ticker: str, period="1mo") -> pd.DataFrame:
    """
    Fetch historical data for a specific ticker over a given period.
    :param ticker: The stock ticker symbol (e.g., 'AAPL').
    :param period: Time range (e.g., '1mo', '6mo', '1y'). Default is 1 month.
    :return: Pandas DataFrame containing historical data.
    """
    if not ticker:
        raise ValueError("Ticker symbol must be provided.")

    try:
        data = yf.Ticker(ticker).history(period=period)
        if data.empty:
            print(f"No data found for ticker: {ticker} over period: {period}")
        else:
            print(f"Fetched {len(data)} rows for ticker {ticker} over {period}.")
        return data
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return pd.DataFrame()  # Return an empty DataFrame on error

def fetch_top_movers(gain_threshold=5, loss_threshold=-5):
    """
    Fetch top gainers and losers from the market based on percentage changes.
    
    :param gain_threshold: % threshold above which stocks will be considered gainers.
    :param loss_threshold: % threshold below which stocks will be considered losers.
    :return: Dictionary with top gainers and losers.
    """
    try:
        url = f"https://finnhub.io/api/v1/market/movers?token={FINNHUB_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        movers = response.json()

        top_gainers = [
            (mover["symbol"], mover["changePercent"]) 
            for mover in movers["gainers"] if mover["changePercent"] >= gain_threshold
        ]

        top_losers = [
            (mover["symbol"], mover["changePercent"]) 
            for mover in movers["losers"] if mover["changePercent"] <= loss_threshold
        ]

        return {
            "top_gainers": top_gainers[:10],
            "top_losers": top_losers[:10],
        }

    except requests.RequestException as e:
        print(f"Error fetching top movers: {e}")
        return {"top_gainers": [], "top_losers": []}

def fetch_stock_news(ticker: str, start_date: str, end_date: str):
    """
    Fetch and return recent news for a given stock ticker within a specific date range.

    Args:
        ticker (str): The stock ticker symbol.
        start_date (str): The start date for fetching news (format: YYYY-MM-DD).
        end_date (str): The end date for fetching news (format: YYYY-MM-DD).

    Returns:
        list: A list of dictionaries containing news details (headline, source, date, URL).
    """
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
        response.raise_for_status()  # Raise an error for non-2xx responses
        news = response.json()

        # Extracting key details from each article
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
        print(f"Error fetching news for {ticker}: {e}")
        return []

def fetch_market_summary():
    """
    Fetch a summary of the current market status.
    :return: Dictionary containing market summary data.
    """
    try:
        url = f"https://finnhub.io/api/v1/market/status?token={FINNHUB_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        summary = response.json()
        return summary
    except requests.RequestException as e:
        print(f"Error fetching market summary: {e}")
        return {}

import requests

def fetch_eod_movers(api_key):
    """
    Fetches the top 20 gainers, losers, and most active traded tickers in the US market.

    Parameters:
    - api_key (str): Your Alpha Vantage API key.

    Returns:
    - dict: A dictionary containing top gainers, losers, and most active tickers.

    Raises:
    - Exception: If the response status code is non-200 or if the response structure is invalid.
    """
    url = f'https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={api_key}'
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx, 5xx)

        data = response.json()

        # Check for valid response structure
        if not data or "top_gainers" not in data or "top_losers" not in data or "most_active_traded" not in data:
            raise KeyError("Missing expected keys in the API response")

        return {
            "Top Gainers": data["top_gainers"],
            "Top Losers": data["top_losers"],
            "Most Active Traded": data["most_active_traded"]
        }
    
    except requests.RequestException as e:
        print(f"Error fetching EOD movers: {e}")
        return {}
    except KeyError as ke:
        print(f"Unexpected response structure: {ke} | Response: {response.text}")
        return {}

def intraday_ticker_data_equities(symbol: str) -> dict:
    """
    Fetch intraday price data for a global equity symbol using Alpha Vantage API.
    """
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if "Global Quote" in data:
            return {
                "symbol": data["Global Quote"]["01. symbol"],
                "price": float(data["Global Quote"]["05. price"]),
                "volume": int(data["Global Quote"]["06. volume"]),
                "latest_trading_day": data["Global Quote"]["07. latest trading day"],
            }
        else:
            logging.warning(f"No intraday data found for {symbol}. Response: {data}")
            return {}
    except Exception as e:
        logging.error(f"Error fetching intraday data for {symbol}: {e}")
        return {}

def get_last_brent_price(api_key: str, interval: str = "daily") -> float:
    """
    Fetch the last available price for Brent Crude Oil using Alpha Vantage's BRENT API.
    
    :param api_key: Your Alpha Vantage API key
    :param interval: The data interval ('daily', 'weekly', or 'monthly'). Default is 'daily'
    :return: Last available price as a float, or None if unavailable
    """
    url = f"https://www.alphavantage.co/query?function=BRENT&interval={interval}&apikey={api_key}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Extract the time series based on the interval provided
        time_series_key = f"Time Series ({interval.capitalize()})"
        
        if time_series_key in data:
            # Get the most recent timestamp in the time series
            latest_date = next(iter(data[time_series_key]))
            last_price = float(data[time_series_key][latest_date]["1. open"])
            return last_price
        else:
            logging.warning(f"No data found for Brent Crude Oil with interval '{interval}'. Response: {data}")
            return None
    except Exception as e:
        logging.error(f"Error fetching Brent price data: {e}")
        return None
  
