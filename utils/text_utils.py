"""
Text utility functions for tweet content:
- classify_headline_topic: tag as macro, political, or equity
- insert_cashtags: transforms known tickers into $CASHTAG format.
- insert_mentions: appends relevant Twitter handles based on keywords.
"""

import re

def classify_headline_topic(headline: str) -> str:
    """
    Classify headline as 'macro', 'political', or 'equity'.
    """
    h = headline.lower()
    political_keywords = ["trump", "election", "senate", "vote", "white house", "parliament"]
    macro_keywords = ["inflation", "rate hike", "interest rate", "fed", "ecb", "central bank", "gdp", "unemployment", "trade agreement", "bonds", "treasury"]
    equity_keywords = ["earnings", "ipo", "stock", "dividend", "guidance", "merger", "acquisition", "ceo", "layoffs"]

    if any(kw in h for kw in political_keywords):
        return "political"
    elif any(kw in h for kw in macro_keywords):
        return "macro"
    elif any(kw in h for kw in equity_keywords):
        return "equity"
    else:
        return "macro"  # safe fallback

def insert_cashtags(text: str) -> str:
    """
    Prefix known equity tickers with $ symbol.
    """
    EQUITY_TICKERS = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "BRK", "V", "UNH",
        "XOM", "BAC", "MA", "WMT", "PFE", "ORCL", "INTC", "CSCO", "NFLX"
    ]
    for ticker in EQUITY_TICKERS:
        pattern = r"(?<!\\$)\\b" + re.escape(ticker) + r"\\b"
        text = re.sub(pattern, f"${ticker}", text, flags=re.IGNORECASE)
    return text

def insert_mentions(text: str) -> str:
    """
    Appends relevant @mentions for equity, political, and macro topics.
    """
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

        # Macro (grouped by signal type)
        "trade agreement": "@realDonaldTrump" "@SecScottBessent",
        "gdp": "@realDonaldTrump" "@SecScottBessent" "@JeromePowell",
        "unemployment": "@realDonaldTrump" "@SecScottBessent",
        "inflation": "@federalreserve @JeromePowell",
        "rate hike": "@federalreserve @JeromePowell",
        "interest rate": "@federalreserve @JeromePowell",
        "fed": "@federalreserve @JeromePowell",
        "bonds": "@USTreasury @SecScottBessent",
        "treasury": "@USTreasury @SecScottBessent"
    }

    added = set()
    for keyword, handle in mention_tags.items():
        if keyword.lower() in text.lower() and handle not in text:
            for tag in handle.split():
                if tag not in added:
                    text += f" {tag}"
                    added.add(tag)
    return text
