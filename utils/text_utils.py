"""
Text utility functions for generating tweet content:
- classify_headline_topic: Categorize headlines as macro, political, or equity
- insert_cashtags: Transforms recognized tickers into $CASHTAG format
- insert_mentions: Appends relevant Twitter handles based on context
"""

import re
import requests
import spacy
from functools import lru_cache
import logging

# Load spaCy model
_NLP = spacy.load("en_core_web_sm")

# Define logger
logger = logging.getLogger(__name__)

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
import re

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

