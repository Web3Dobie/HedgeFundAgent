import requests
from utils.config import FINNHUB_API_KEY

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