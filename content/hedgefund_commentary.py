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
    enrich_cashtags_with_price,
    percent_mentioned,
)
from utils.theme_tracker import load_recent_themes, extract_theme, is_duplicate_theme, track_theme

from utils.fetch_stock_data import fetch_last_price_yf
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
        return random.choice([CATEGORY_MACRO, CATEGORY_POLITICAL, CATEGORY_EQUITY])

def build_prompt(headline: str, category: str) -> str:
    return (
        f"Comment on this political/macro headline like a global macro hedge fund PM: '{headline}'. "
        f"Whenever you mention a stock ticker (cashtag like $XYZ), include the cashtag; my system will insert price and percent change."
    )

def get_next_category():
    global last_used_category
    categories = [CATEGORY_MACRO, CATEGORY_POLITICAL, CATEGORY_EQUITY]
    if last_used_category:
        current_index = categories.index(last_used_category)
        next_index = (current_index + 1) % len(categories)
        next_category = categories[next_index]
    else:
        next_category = CATEGORY_MACRO
    last_used_category = next_category
    return next_category

def post_hedgefund_comment():
    logger.info("\U0001f9e0 Generating hedge fund investor comment")
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

    cashtags = set(extract_cashtags(core))
    trailing = set(insert_cashtags(core).split())
    cashtags.update(trailing)

    logger.info(f"Total cashtags to enrich: {cashtags}")

    prices = {}
    for tag in cashtags:
        ticker = tag.strip("$")
        price_data = fetch_last_price_yf(ticker)
        if price_data:
            prices[tag] = price_data

    if prices:
        enhanced_prompt = enhance_prompt_with_prices(prompt, prices)
        final_core = generate_gpt_tweet(enhanced_prompt) or core
    else:
        final_core = core

    seen_tickers = set()
    for tag, data in prices.items():
        if tag in seen_tickers:
            continue

        price = data.get("price")
        change = data.get("change_percent")
        price_str = f"${price:.2f}" if price is not None else ""
        change_str = f"{change:+.2f}%" if change is not None else ""

        already_has_price = price_str in final_core
        already_has_change = percent_mentioned(final_core, change_str)

        if tag in final_core and not (already_has_price and already_has_change):
            addition = []
            if price_str and not already_has_price:
                addition.append(price_str)
            if change_str and not already_has_change:
                addition.append(change_str)
            if addition:
                final_core += f" ({', '.join(addition)})"
                seen_tickers.add(tag)

    if "$" not in final_core:
        final_core = insert_cashtags(final_core)
    final_core = insert_mentions(final_core)
    final_core = re.sub(
        r"This is my opinion\\. Not financial advice\\.*",
        "",
        final_core,
        flags=re.IGNORECASE
    ).strip()
    tweet = f"{final_core}\n\n{DISCLAIMER}"

    logger.info(f"Using theme: {theme}")
    logger.info(f"Using category: {category}")
    post_tweet(tweet, category=category, theme=theme)
    mark_headline_used_in_hourly_commentary(headline["headline"])
    track_theme(theme)
    logger.info(f"\u2705 Posted hedge fund commentary tweet: {tweet}")

if __name__ == "__main__":
    load_recent_themes()
    post_hedgefund_comment()
