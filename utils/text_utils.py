"""
Text utility functions for generating tweet content:
- classify_headline_topic: Categorize headlines as macro, political, or equity
- insert_cashtags: Transforms recognized tickers into $CASHTAG format
- insert_mentions: Appends relevant Twitter handles based on context
"""

import re
import requests
import spacy
import csv
import os
import pandas as pd
from functools import lru_cache
from datetime import datetime
import logging
from utils.config import DATA_DIR

# Load spaCy model
_NLP = spacy.load("en_core_web_sm")

# Define logger
logger = logging.getLogger(__name__)


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
EXCEL_PATH = os.path.join(DATA_DIR, "index_constituents.xlsx")

### --- 1. Classify Headline Topic --- ###

def classify_headline_topic(headline: str) -> str:
    """
    Classify headline into 'equity', 'macro', or 'political'.
    Uses spaCy named entity recognition (ORG label) and keyword matching.

    Args:
        headline (str): Text of the headline.
    Returns:
        str: Category name ('equity', 'macro', 'political').
    """
    try:
        # Use spaCy to detect organizations
        doc = _NLP(headline)
        for ent in doc.ents:
            if ent.label_ == "ORG":
                return "equity"

        h = headline.lower()
        political_keywords = ["putin", "trump", "election", "senate", "vote", "white house", "parliament"]
        macro_keywords     = ["inflation", "rate hike", "interest rate", "fed", "ecb", "central bank", "gdp", "unemployment", "trade agreement"]
        equity_keywords    = ["earnings", "ipo", "stock", "dividend", "guidance", "merger", "acquisition", "ceo", "layoffs"]

        # Match keywords to categories
        if any(kw in h for kw in political_keywords):
            return "political"
        elif any(kw in h for kw in macro_keywords):
            return "macro"
        elif any(kw in h for kw in equity_keywords):
            return "equity"
        else:
            return "macro"  # Default fallback category
    except Exception as e:
        logger.error(f"Error in classify_headline_topic: {e}")
        return "macro"


### --- 2. Insert Cashtags --- ###

def fetch_equity_tickers(api_key: str) -> list[str]:
    """
    Dynamically fetch valid equity tickers from API.

    Args:
        api_key (str): Alpha Vantage API key.
    Returns:
        list[str]: List of ticker symbols.
    """
    try:
        url = f"https://www.alphavantage.co/query?function=LISTING_STATUS&apikey={api_key}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get("symbols", [])
    except Exception as e:
        logger.error(f"Error fetching equity tickers: {e}")
        return []


@lru_cache(maxsize=100)  # Cache valid tickers for performance
def validate_ticker(ticker: str) -> bool:
    """
    Validate if the ticker exists in the known list of equities.

    Args:
        ticker (str): Stock ticker symbol.
    Returns:
        bool: True if valid, False otherwise.
    """
    # Replace with dynamic fetching logic if needed
    valid_tickers = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "BRK", "V",
        "UNH", "XOM", "BAC", "MA", "WMT", "PFE", "ORCL", "INTC", "CSCO", "NFLX"
    ]
    return ticker.upper() in valid_tickers


def insert_cashtags(text: str) -> str:
    """
    Prefix recognized equity tickers in text with '$' symbol.

    Args:
        text (str): Input string containing stock-related information.
    Returns:
        str: Updated text with $CASHTAGS added.
    """
    try:
        # Static list can be replaced by `fetch_equity_tickers` for dynamic checking
        EQUITY_TICKERS = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "BRK", "V",
            "UNH", "XOM", "BAC", "MA", "WMT", "PFE", "ORCL", "INTC", "CSCO", "NFLX"
        ]
        
        for ticker in EQUITY_TICKERS:
            pattern = r"\b" + re.escape(ticker) + r"\b"  # Match full words only
            text = re.sub(pattern, f"${ticker}", text, flags=re.IGNORECASE)

        return text
    except Exception as e:
        logger.error(f"Error in insert_cashtags: {e}")
        return text


### --- 3. Insert Mentions --- ###

def insert_mentions(text: str) -> str:
    """
    Append relevant @mentions based on headline keywords.

    Args:
        text (str): Input string containing stock, macro, or political context.
    Returns:
        str: Text augmented with Twitter mentions.
    """
    try:
        mention_tags = {
            # Equity
            "Apple": "@Apple",
            "Microsoft": "@Microsoft",
            "Google": "@Google",
            "Amazon": "@Amazon",
            "Meta": "@Meta",
            "NVIDIA": "@nvidia",
            "Tesla": "@Tesla",
            "JPMorgan": "@jpmorgan",
            "Berkshire": "@BerkshireHath",
            "Visa": "@Visa",
            "Pfizer": "@pfizer",
            "Netflix": "@netflix",

            # Political
            "Trump": "@realDonaldTrump",
            "White House": "@WhiteHouse",

            # Macro tags
            "trade agreement": "@SecScottBessent @realDonaldTrump",
            "gdp": "@realDonaldTrump @SecScottBessent",
            "unemployment": "@realDonaldTrump @SecScottBessent",
            "inflation": "@federalreserve @realDonaldTrump",
            "rate hike": "@federalreserve @realDonaldTrump",
            "interest rate": "@federalreserve @realDonaldTrump",
            "fed": "@federalreserve @realDonaldTrump",
            "bonds": "@USTreasury @SecScottBessent",
            "treasury": "@USTreasury @SecScottBessent"
        }

        added = set()
        for keyword, handle in mention_tags.items():
            if keyword.lower() in text.lower() and handle not in text:
                for tag in handle.split():  # Handle multiple mentions for the same keyword
                    if tag not in added:
                        text += f" {tag}"
                        added.add(tag)
                        
        return text.strip()

    except Exception as e:
        logger.error(f"Error in insert_mentions: {e}")
        return text


### --- 4. Extract Cashtags --- ###

def extract_cashtags(commentary: str) -> list[str]:
    """
    Extracts valid cashtags like $AAPL or $0700.HK, excluding numeric values like $64.20,
    and removes trailing punctuation from tags like $AAPL, or $TSLA.
    """
    try:
        raw_tags = re.findall(r"\$[A-Za-z][A-Za-z0-9\.\-]{0,9}", commentary)
        return list(set(tag.rstrip('.,;:!?') for tag in raw_tags))
    except Exception as e:
        logger.error(f"Error in extract_cashtags: {e}")
        return []

### --- 5. Enhance Prompt with Prices --- ###

def enhance_prompt_with_prices(prompt: str, prices: dict) -> str:
    """
    Enhances the prompt by appending price + change data for referenced tickers.

    Args:
        prompt (str): The original GPT prompt.
        prices (dict): Dictionary like {"$AAPL": {"price": 189.24, "change_pct": -2.5}}

    Returns:
        str: The enhanced prompt including price information.
    """
    if not prices:
        return prompt

    price_lines = []
    for tag, data in prices.items():
        if data:
            price_str = f"{tag}: ${data['price']:.2f}"
            if "change_pct" in data and data["change_pct"] is not None:
                price_str += f" ({data['change_pct']:+.2f}%)"
            price_lines.append(price_str)
        else:
            price_lines.append(f"{tag}: price unavailable")

    price_info = "Price data:\n" + "\n".join(price_lines)
    return f"{prompt}\n\n{price_info}"

### --- 6. Enrich Cashtags with Price Data --- ###


def enrich_cashtags_with_price(text: str, prices: dict) -> str:
    """
    Replaces $TICKER in the text with $TICKER (price, %change) using provided price data.
    Strips pre-existing (+X.XX%) patterns to avoid duplication.
    """
    # Remove any loose percent-change-only tags that may have been echoed by GPT
    text = re.sub(r"\(\s*[-+]\d+(\.\d+)?%\)", "", text)

    def replacer(match):
        tag = match.group(0)
        data = prices.get(tag)
        if data and "price" in data:
            return f"{tag} (${data['price']:.2f}, {data.get('change_pct', 0):+0.2f}%)"
        return tag

    return re.sub(r"\$[A-Z]{1,5}", replacer, text)

def is_weekend():
    return datetime.utcnow().weekday() in [5, 6]

def percent_mentioned(part, value):
    # Match once, not as trailing duplicate
    return bool(re.search(rf"{re.escape(value)}(?:%|\\b)", part))

def get_headlines_for_tickers(tickers: list[str], headlines: list[tuple]) -> list[tuple]:
    """Return headlines where the ticker or company name appears."""
    matched = []
    for score, headline, url in headlines:
        if any(ticker in headline.upper() for ticker in tickers):
            matched.append((score, headline, url))
    return matched

def is_valid_ticker(tag: str) -> bool:
    return tag.isupper() and tag.isalpha() and 1 <= len(tag) <= 5

def fetch_scored_headlines(category: str) -> list[dict]:
    """
    Load scored headlines from the category-specific CSV.
    """
    path = os.path.join(DATA_DIR, f"scored_headlines_{category}.csv")
    if not os.path.exists(path):
        return []

    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def flatten_and_deduplicate_headlines(mover_news):
    seen_headlines = set()
    unique_headlines = []
    for ticker, articles in mover_news.items():
        for article in articles:
            headline = article.get("headline", "").strip().lower()
            url = article.get("url", "")
            if not headline or not url:
                continue
            if headline in seen_headlines:
                continue
            unique_headlines.append((0, f"{article['headline']} ({ticker})", url))
            seen_headlines.add(headline)
    return unique_headlines

def load_ticker_info():
    xls = pd.ExcelFile(EXCEL_PATH)
    sp100_df = pd.read_excel(xls, "SP100")
    nasdaq100_df = pd.read_excel(xls, "Nasdaq100")

    def df_to_dict(df):
        d = {}
        for _, row in df.iterrows():
            ticker = row['Ticker'].strip().upper()
            d[ticker] = {
                "name": row['Company_Name'].strip(),
                "sector": row.get('GICS_Sector', '').strip() if 'Sector' in row else None
            }
        return d

    sp100_dict = df_to_dict(sp100_df)
    nasdaq100_dict = df_to_dict(nasdaq100_df)

    combined = {**sp100_dict, **nasdaq100_dict}
    return combined

TICKER_INFO = load_ticker_info()

import re

def is_relevant_headline(ticker: str, headline: str, company_name: str) -> bool:
    if not headline:
        return False

    ticker = ticker.lower()
    headline_lower = headline.lower()
    company_name_lower = company_name.lower() if company_name else ""

    # Pattern to match ticker with word boundaries relaxed
    ticker_pattern = r'(?<!\w)' + re.escape(ticker) + r'(?!\w)'

    # Check for cashtag e.g. $tsla
    cashtag = f"${ticker}"

    # Basic company name cleanup to main part, remove suffixes
    def clean_company_name(name):
        suffixes = ["inc", "inc.", "ltd", "ltd.", "corp", "corporation", "co", "co."]
        for suf in suffixes:
            if name.endswith(suf):
                name = name[: -len(suf)].strip()
        return name

    company_name_clean = clean_company_name(company_name_lower)

    company_pattern = r'\b' + re.escape(company_name_clean) + r'\b' if company_name_clean else None

    # Check ticker presence
    ticker_in_headline = re.search(ticker_pattern, headline_lower) is not None or cashtag in headline_lower

    # Check company name presence (optional)
    company_in_headline = re.search(company_pattern, headline_lower) is not None if company_pattern else False

    return ticker_in_headline or company_in_headline

def get_briefing_caption(period: str, headline: str = None, summary: str = None) -> str:
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    if period == "morning":
        return (
            f"Morning Briefing: Overnight Up-Date 🌅\n"
            f"{headline or ''}\n"
            f"{date_str}\n"
            f"#morning #markets #macro"
        )
    elif period == "pre_market":
        return (
            f"Pre-Market Moves: What’s Hot Before the Bell 🚦\n"
            f"{headline or ''}\n"
            f"{date_str}\n"
            f"#premarket #stocks #trading"
        )
    elif period == "mid_day":
        return (
            f"Mid-Day Market Pulse 🕛\n"
            f"{summary or ''}\n"
            f"{date_str}\n"
            f"#midday #marketupdate"
        )
    elif period == "after_market":
        return (
            f"After-Market Wrap: Winners, Losers & Surprises 🌙\n"
            f"{headline or ''}\n"
            f"{date_str}\n"
            f"#afterhours #markets"
        )
    else:
        return (
            f"{period.capitalize()} Market Briefing 🧠\n"
            f"{date_str}\n"
            f"#markets"
        )

from datetime import datetime

from datetime import datetime

def format_market_sentiment(period, equity_block, macro_block, crypto_block, movers=None):
    """
    Builds the text-only market sentiment tweet for the specified period.
    period: 'morning', 'pre_market', 'mid_day', or 'after_market'
    """
    lines = []
    date_str = datetime.utcnow().strftime('%Y-%m-%d')

    if period == "morning":
        lines.append("Overnight movers & macro highlights:")
        # Asian and European index moves
        for idx in ["Nikkei 225", "Hang Seng", "Euro Stoxx 50", "DAX"]:
            val = equity_block.get(idx)
            if val:
                lines.append(f"🔸 {idx}: {val}")
        # FX and Crypto
        usdjpy = macro_block.get("USD/JPY")
        if usdjpy:
            lines.append(f"USD/JPY: {usdjpy}")
        btc = crypto_block.get("BTC")
        if btc:
            lines.append(f"$BTC: {btc}")
        lines.append(f"#morning #macro #markets {date_str}")

    elif period == "pre_market":
        lines.append("Pre-market movers before the bell:")
        if movers:
            gainers = list(movers.get("top_gainers", {}).items())
            losers = list(movers.get("top_losers", {}).items())
            for symbol, val in gainers:
                lines.append(f"🔺 ${symbol}: {val}")
            for symbol, val in losers:
                lines.append(f"🔻 ${symbol}: {val}")
            if not gainers and not losers:
                lines.append("No pre-market movers found.")
        else:
            lines.append("No pre-market movers found.")
        # Add key futures or FX
        spfut = equity_block.get("S&P Futures")
        if spfut:
            lines.append(f"S&P Futures: {spfut}")
        lines.append(f"#premarket #stocks #trading {date_str}")

    elif period == "mid_day":
        lines.append("European close snapshot:")
        for idx in ["Euro Stoxx 50", "DAX", "CAC 40", "FTSE 100"]:
            val = equity_block.get(idx)
            if val:
                lines.append(f"🔸 {idx}: {val}")
        eurusd = macro_block.get("EUR/USD")
        if eurusd:
            lines.append(f"EUR/USD: {eurusd}")
        lines.append(f"#midday #europe #marketupdate {date_str}")

    elif period == "after_market":
        lines.append("After-hours movers & wrap-up:")
        if movers:
            gainers = list(movers.get("top_gainers", {}).items())
            losers = list(movers.get("top_losers", {}).items())
            for symbol, val in gainers:
                lines.append(f"🔺 ${symbol}: {val}")
            for symbol, val in losers:
                lines.append(f"🔻 ${symbol}: {val}")
            if not gainers and not losers:
                lines.append("No after-hours movers found.")
        else:
            lines.append("No after-hours movers found.")
        # Highlight big S&P move only
        sp_fut = equity_block.get("S&P Futures")
        sp500 = equity_block.get("S&P 500")
        for sp_label, sp_val in [("S&P Futures", sp_fut), ("S&P 500", sp500)]:
            if sp_val:
                try:
                    pct = float(sp_val.split("(")[-1].replace("%)", "").replace("+", ""))
                    if abs(pct) >= 1.0:
                        direction = "surged" if pct > 0 else "dropped"
                        lines.append(f"⚡️ {sp_label} {direction} {pct:+.2f}% today.")
                except Exception:
                    pass
                break
        # FX/crypto as usual
        usdjpy = macro_block.get("USD/JPY")
        if usdjpy:
            lines.append(f"USD/JPY: {usdjpy}")
        btc = crypto_block.get("BTC")
        if btc:
            lines.append(f"$BTC: {btc}")
        lines.append(f"#afterhours #markets {date_str}")

    else:
        # Fallback for unexpected types
        lines.append("Market sentiment snapshot:")
        sp = equity_block.get("S&P 500") or equity_block.get("S&P Futures")
        btc = crypto_block.get("BTC")
        usdjpy = macro_block.get("USD/JPY")
        if sp:
            lines.append(f"🔸 S&P 500: {sp}")
        if btc:
            lines.append(f"🔸 $BTC: {btc}")
        if usdjpy:
            lines.append(f"🔸 USD/JPY: {usdjpy}")
        lines.append(f"#markets {date_str}")

    return "\n".join(lines)
