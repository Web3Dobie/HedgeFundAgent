import yfinance as yf   # Used for fetching historial stock data
import pandas as pd     # Used for data manipulation and analysis
import requests         # Used for making HTTP requests to external APIs
import os               # Used for environment variable management
import logging          # Used for logging errors and information
import json             # Used for handling JSON data
from tvscreener import StockScreener
from datetime import datetime, timedelta
from utils.text_utils import TICKER_INFO

from dotenv import load_dotenv
from utils.config import (FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY)

logger = logging.getLogger(__name__)

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

def fetch_prior_close_yield(symbol: str) -> float:
    """
    Get previous day's closing yield (%) for treasury instruments.
    Yahoo symbols like ^IRX (2Y), ^TNX (10Y), ^TYX (30Y) return yield * 100.
    """
    df = fetch_ticker_data(symbol, period="2d")
    if len(df) >= 2:
        return round(df["Close"].iloc[-2], 2)  # Convert from 428 → 4.28%
    return None


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

def fetch_last_price_yf(symbol: str) -> dict:
    # Suppress noisy yfinance logs
    logging.getLogger("yfinance").setLevel(logging.WARNING)

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")

        if hist.empty or len(hist) < 1:
            return {}

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest

        price = latest["Close"]
        prev_close = prev["Close"]
        change_pct = (price - prev_close) / prev_close * 100
        timestamp = latest.name.date().isoformat()

        return {
            "price": round(price, 4) if symbol.endswith("=X") else round(price, 2),
            "change_percent": round(change_pct, 2),
            "timestamp": timestamp
        }

    except Exception as e:
        logging.error(f"[YF] Error fetching data for {symbol}: {e}")
        return {}

def get_top_movers_from_constituents(limit=5, include_extended=False) -> dict:
    """
    Fetches top gainers and losers from SP100 + NASDAQ100 based on % change.
    Optionally includes pre-market or post-market movers.

    Returns:
        dict with gainers/losers and optionally pre/post movers.
    """
    combined = sorted(TICKER_INFO.keys())
    data = []
    pre_data = []
    post_data = []

    for symbol in combined:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d")
            info = ticker.info

            if len(hist) < 2:
                continue

            prev_close = hist.iloc[-2]["Close"]
            last_close = hist.iloc[-1]["Close"]
            pct_change = ((last_close - prev_close) / prev_close) * 100
            data.append((symbol, last_close, pct_change))

            if include_extended:
                if "preMarketPrice" in info and info["preMarketPrice"]:
                    pre_pct = ((info["preMarketPrice"] - last_close) / last_close) * 100
                    pre_data.append((symbol, info["preMarketPrice"], pre_pct))
                if "postMarketPrice" in info and info["postMarketPrice"]:
                    post_pct = ((info["postMarketPrice"] - last_close) / last_close) * 100
                    post_data.append((symbol, info["postMarketPrice"], post_pct))

        except Exception:
            continue

    movers = {
        "top_gainers": sorted(data, key=lambda x: -x[2])[:limit],
        "top_losers": sorted(data, key=lambda x: x[2])[:limit]
    }

    if include_extended:
        movers["pre_market"] = sorted(pre_data, key=lambda x: -x[2])[:limit]
        movers["post_market"] = sorted(post_data, key=lambda x: -x[2])[:limit]

    return movers
