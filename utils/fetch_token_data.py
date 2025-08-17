from threading import Lock
import requests
import logging
from data.ticker_blocks import CRYPTO as CRYPTO_TOKENS # Importing CRYPTO tokens from ticker blocks

logger = logging.getLogger(__name__)

# COINGECKO-SPECIFIC MAPPING 
CRYPTO_TOKENS = {
    # CoinGecko API names (lowercase) -> Display tickers
    "bitcoin": "BTC",
    "ethereum": "ETH", 
    "solana": "SOL",
    "ripple": "XRP",        # XRP on CoinGecko is "ripple" 
    "cardano": "ADA",
}


def get_top_tokens_data():
    """
    Fetch price and 24h change for each token from CoinGecko.
    Returns a list of dicts with 'ticker', 'price', and 'change'.
    """
    try:
        ids = ",".join(CRYPTO_TOKENS.keys())  # Now uses lowercase names
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        )
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        results = []
        for name, ticker in CRYPTO_TOKENS.items():  # Now matches API response
            info = data.get(name, {})
            price = info.get("usd")
            change = info.get("usd_24h_change")
            if price is None or change is None:
                logger.warning(f"⚠️ Incomplete data for {name}")
                continue
            results.append({"ticker": ticker, "price": price, "change": change})

        if len(results) < 3:
            logger.warning("⚠️ Fewer than 3 valid tokens—skipping.")
            return []

        # Sort by change percentage (descending for gains, ascending for losses)
        all_negative = all(t['change'] < 0 for t in results)
        results.sort(key=lambda x: x['change'], reverse=not all_negative)

        return results
    except Exception as e:
        logger.error(f"❌ Error fetching prices: {e}")
        return []

# Thread safety lock
_market_summary_lock = Lock()
_last_attempt_time = None