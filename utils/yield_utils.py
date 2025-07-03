import os
import re

from utils.fetch_stock_data import fetch_prior_close_yield
from data.ticker_blocks import YIELD_SYMBOLS

def treasury_futures_to_yield_change(label, value):
    """
    Estimate the change in yield (%) from the change in the futures price.
    Returns a string like: "-0.01%" for a small move lower in yield.
    """
    match = re.search(r"\(([-+]\d+\.\d+)%\)", value)
    if not match:
        return None  # No change info

    pct_change = float(match.group(1))
    # Rule of thumb: +1% in price ≈ X% drop in yield (negative correlation)
    if "2Y" in label:
        multiplier = -0.40  # +1% in price = -0.40% in yield (40bps)
    elif "10Y" in label:
        multiplier = -0.17  # +1% in price = -0.17% in yield (17bps)
    else:
        multiplier = -0.20  # Default fallback

    yield_change = pct_change * multiplier
    return f"{yield_change:+.2f}%"

def convert_us_treasury_yields(price_block: dict) -> dict:
    # Make a copy if you want to avoid mutating original
    block = dict(price_block)
    for label in list(block):
        if "US Treasury" in label:
            yield_delta = treasury_futures_to_yield_change(label, block[label])
            if yield_delta:
                tenor = label.split()[0]
                yield_symbol = YIELD_SYMBOLS.get(tenor)
                if yield_symbol:
                    prior_yield = fetch_prior_close_yield(yield_symbol)
                    if prior_yield is not None:
                        delta_float = float(yield_delta.replace("%", ""))
                        implied_yield = prior_yield + delta_float
                        new_label = f"{tenor} Yield"
                        block[new_label] = f"{implied_yield:.2f}% ({yield_delta})"
            del block[label]
    return block
