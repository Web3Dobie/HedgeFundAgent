import yfinance as yf
import pandas as pd


def fetch_ticker_data(ticker: str, period="1mo") -> pd.DataFrame:
    """
    Fetch historical data for a specific ticker over a given period.
    :param ticker: The stock ticker symbol (e.g., 'AAPL').
    :param period: Time range (e.g., '1mo', '6mo', '1y'). Default is 1 month.
    :return: Pandas DataFrame containing historical data.
    """
    data = yf.Ticker(ticker).history(period=period)
    print(f"Fetched data for {ticker} over {period}.")
    print(data)
    return data

ticker_data = fetch_ticker_data('AAPL', '1wk')


def fetch_top_movers():
    """
    Fetch top gainers and losers in the market.
    :return: Dictionary containing top gainers and losers.
    """
    # Placeholder logic; replace with an actual API or source for top movers
    # Example hardcoded list (you can use a scraping library or an external API)
    top_gainers = ['TSLA', 'NVDA', 'AMD'] 
    top_losers = ['INTC', 'DIS', 'NFLX']
    
    return {'gainers': top_gainers, 'losers': top_losers}
