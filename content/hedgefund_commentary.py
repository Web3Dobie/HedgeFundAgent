import logging
from datetime import datetime
import random
import csv, os
import re

from utils.config import DATA_DIR
from utils.headline_pipeline import fetch_and_score_headlines
from utils.scorer import score_headlines
from utils.gpt import generate_gpt_tweet
from utils.text_utils import (
    insert_cashtags, 
    insert_mentions, 
    extract_cashtags, 
    enhance_prompt_with_prices,
    enrich_cashtags_with_price
)
from utils.theme_tracker import load_recent_themes, extract_theme, is_duplicate_theme, track_theme

from utils.fetch_stock_data import intraday_ticker_data_equities, get_last_brent_price, fetch_market_price
from utils.config import ALPHA_VANTAGE_API_KEY 
from utils.x_post import post_tweet
from utils.hourly_utils import (
    get_unused_headline_today_for_hourly,
    mark_headline_used_in_hourly_commentary,
)

logger = logging.getLogger("hedgefund_commentary")


CATEGORY_MACRO = "macro"
CATEGORY_EQUITY = "equity"
CATEGORY_POLITICAL = "political"
DISCLAIMER = "This is my opinion. Not financial advice."

# Keep a global variable or store this persistently (e.g., file/db) if needed
last_used_category = None

def classify_headline(headline: str) -> str:
    keywords_macro = ["trump", "europe", "china", "inflation", "fed", "ecb", "election", "tariffs", "geopolitical", "interest rate"]
    keywords_political = ["government", "policy", "senate", "congress", "war", "diplomacy", "trade", "trade agreement", "sanctions"]
    keywords_equity = ["earnings", "stock", "IPO", "revenue", "guidance", "CEO", "acquisition", "buyback"]
    
    hl = headline.lower()
    if any(word in hl for word in keywords_macro):
        return CATEGORY_MACRO
    elif any(word in hl for word in keywords_political):
        return CATEGORY_POLITICAL
    elif any(word in hl for word in keywords_equity):
        return CATEGORY_EQUITY
    else:
        # If no match, return random category
        return random.choice([CATEGORY_MACRO, CATEGORY_POLITICAL, CATEGORY_EQUITY])

def build_prompt(headline: str, category: str) -> str:
    if category == CATEGORY_MACRO:
        return (
            f"Comment on this political/macro headline like a global macro hedge fund PM: '{headline}'. "
            f"Whenever you mention a stock ticker (cashtag like $XYZ), include the cashtag; my system will insert price and percent change."
        )
    elif category == CATEGORY_POLITICAL:
        return (
            f"Comment on this political/macro headline like a global macro hedge fund PM: '{headline}'. "
            f"Whenever you mention a stock ticker (cashtag like $XYZ), include the cashtag; my system will insert price and percent change."
        )
    else:
        return (
            f"Comment on this political/macro headline like a global macro hedge fund PM: '{headline}'. "
            f"Whenever you mention a stock ticker (cashtag like $XYZ), include the cashtag; my system will insert price and percent change."  
        )

def get_next_category():
    global last_used_category
    categories = [CATEGORY_MACRO, CATEGORY_POLITICAL, CATEGORY_EQUITY]

    # Rotate to the next category
    if last_used_category:
        current_index = categories.index(last_used_category)
        next_index = (current_index + 1) % len(categories)
        next_category = categories[next_index]
    else:
        # Default category if none is set initially
        next_category = CATEGORY_MACRO

    last_used_category = next_category
    return next_category


def post_hedgefund_comment():
    logger.info("🧠 Generating hedge fund investor comment")

    scored_path = os.path.join(DATA_DIR, "scored_headlines.csv")
    if not os.path.exists(scored_path):
        logger.warning("No scored headlines found.")
        return

    today = datetime.utcnow().date().isoformat()
    with open(scored_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    recent = [
        r for r in rows
        if r.get("timestamp", "").startswith(today) and
           r.get("used_in_hourly_commentary", "False").lower() != "true"
    ]

    if not recent:
        logger.warning("No unused headlines available for hourly commentary.")
        return

    target_category = get_next_category()
    candidates = [r for r in recent if classify_headline(r["headline"]) == target_category]

    if not candidates:
        logger.warning(f"No headlines available for category '{target_category}', falling back to all recent.")
        candidates = recent

    # Try to find a headline with unused theme
    selected = None
    for r in sorted(candidates, key=lambda r: int(r["score"]), reverse=True):
        t = extract_theme(r["headline"])
        if not is_duplicate_theme(t):
            selected = (r, t)
            break

    if selected:
        headline, theme = selected
    else:
        logger.warning("All headlines have duplicate themes. Using highest scoring anyway.")
        headline = candidates[0]
        theme = extract_theme(headline["headline"])

    category = classify_headline(headline["headline"])
    prompt = build_prompt(headline["headline"], category)

    core = generate_gpt_tweet(prompt)
    if not core:
        logger.error("GPT did not return a tweet.")
        return

    # Extract all potential cashtags (inline and trailing)
    cashtags = set(extract_cashtags(core))
    trailing = set(insert_cashtags(core).split())
    cashtags.update(trailing)

    logger.info(f"Total cashtags to enrich: {cashtags}")

    # Fetch live price data
    prices = {}
    for tag in cashtags:
        ticker = tag.strip("$")
        price_data = fetch_market_price(ticker)
        if price_data:
            prices[tag] = price_data

    # Enrich GPT output with price info
    if prices:
        enhanced_prompt = enhance_prompt_with_prices(prompt, prices)
        final_core = generate_gpt_tweet(enhanced_prompt) or core
        final_core = enrich_cashtags_with_price(final_core, prices)
    else:
        final_core = core

    # Ensure price enrichment is applied even if GPT ignored prompt instruction
    final_core = enrich_cashtags_with_price(final_core, prices)

    # Add mentions and cashtags into the tweet body first
    final_core = insert_mentions(final_core)
    final_core = insert_cashtags(final_core)

    # Clean any pre-existing disclaimer
    final_core = re.sub(
        r"This is my opinion\. Not financial advice\.*",
        "",
        final_core,
        flags=re.IGNORECASE
    ).strip()

    # Append clean disclaimer LAST
    DISCLAIMER = "This is my opinion. Not financial advice."
    tweet = f"{final_core}\n\n{DISCLAIMER}"

    logger.info(f"Using theme: {theme}")
    logger.info(f"Using category: {category}")
    post_tweet(tweet, category=category, theme=theme)
    mark_headline_used_in_hourly_commentary(headline["headline"])
    track_theme(theme)
    logger.info(f"✅ Posted hedge fund commentary tweet: {tweet}")

if __name__ == "__main__":
    load_recent_themes()
    post_hedgefund_comment()
