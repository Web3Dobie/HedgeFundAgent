"""
Utility for finding relevant stock tickers based on keywords/themes
"""

import logging
import re
from typing import List, Optional

from openai import OpenAI

client = OpenAI()

def validate_ticker(ticker: str) -> bool:
    """Validate ticker format ($SYMBOL with 1-5 chars after $)"""
    return bool(re.match(r'^\$[A-Z]{1,5}$', ticker))

def get_relevant_tickers(theme: str, max_tickers: int = 3) -> list[str]:
    """
    Use GPT to identify relevant stock tickers for a given theme.
    Returns a list of cashtags (e.g., ['$XHB', '$LEN', '$DHI'])
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a stock market expert. Given a theme, return ONLY the most relevant "
                        "US stock tickers. Always include 1 sector ETF first if available, then the top companies. "
                        "For example, for homebuilders return: $XHB $LEN $DHI\n"
                        "Return only tickers with $ prefix, separated by spaces. No explanation."
                    )
                },
                {
                    "role": "user", 
                    "content": f"Return {max_tickers} most relevant tickers for: {theme}"
                }
            ],
            max_tokens=50,
            temperature=0.2,  # Lower temperature for more consistent results
        )
        
        tickers = response.choices[0].message.content.strip().split()
        # Validate tickers (must start with $ and be 1-5 chars after $)
        valid_tickers = [t for t in tickers if t.startswith('$') and 1 <= len(t[1:]) <= 5]
        
        if not valid_tickers:
            logging.warning(f"No valid tickers found for theme: {theme}")
            return []
            
        return valid_tickers[:max_tickers]
        
    except Exception as e:
        logging.error(f"Error finding tickers: {e}")
        return []