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
    insert_mentions, 
    extract_cashtags, 
    is_valid_ticker,
    fetch_scored_headlines
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

def build_prompt(headline: str, summary: str, category: str) -> str:
    context = f"Headline: {headline.strip()}\n\nSummary: {summary.strip() or '[No summary available]'}"

    base = "Whenever you mention a stock ticker (cashtag like $XYZ), include the cashtag; my system will insert price and percent change."

    if category == CATEGORY_MACRO:
        return f"Comment on this macro headline like a global macro hedge fund PM:\n\n{context}\n\n{base}"
    elif category == CATEGORY_POLITICAL:
        return f"Comment on this political headline like a hedge fund strategist:\n\n{context}\n\n{base}"
    else:
        return f"Comment on this financial/corporate headline like an equity hedge fund PM:\n\n{context}\n\n{base}"

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

    # Step 1: Choose category and fetch scored headlines
    target_category = get_next_category()
    rows = fetch_scored_headlines(target_category)
    if not rows:
        logger.warning(f"No scored headlines found for category '{target_category}'")
        return

    # Step 2: Filter to today's unused headlines
    today = datetime.utcnow().date().isoformat()
    recent = [
        r for r in rows
        if r.get("timestamp", "").startswith(today) and
           r.get("used_in_hourly_commentary", "False").lower() != "true"
    ]
    if not recent:
        logger.warning("No unused headlines available for hourly commentary.")
        return

    # Step 3: Use headlines in this category (they already are) as candidates
    candidates = recent

    # Step 4: Select highest scoring non-duplicate theme
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

    category = classify_headline(headline["headline"])  # still used to format prompt
    prompt = build_prompt(headline["headline"], headline.get("summary", ""), category)

    tweet = generate_gpt_tweet(prompt)
    
    # === Begin Content Filter Handling Patch ===
    # Check if tweet is a dict and Azure flagged it (depends on your GPT wrapper return, adjust as needed)
    if isinstance(tweet, dict) and tweet.get("error", {}).get("code") == "contentfilter":
        logger.warning(f"[FILTERED] Commentary blocked by Azure content filter: {headline['headline']}")
        # Mark as used with 'filtered' status so this headline is never retried
        mark_headline_used_in_hourly_commentary(headline["headline"], reason="filtered")
        # Optionally: notify Telegram here
        return

    # Or if tweet is just None/empty (could happen after filtering)
    if not tweet:
        logger.error(f"[EMPTY] Commentary failed for: {headline['headline']}")
        mark_headline_used_in_hourly_commentary(headline["headline"], reason="empty")
        return

    cashtags = extract_cashtags(tweet)
    logger.info(f"Extracted cashtags: {cashtags}")

    prices = {}
    for tag in cashtags:
        ticker = tag.strip("$")
        if is_valid_ticker(ticker):
            data = fetch_last_price_yf(ticker)
            if data:
                prices[tag] = data

    for tag, data in prices.items():
        price = data.get("price")
        change = data.get("change_percent")
        if price is not None and change is not None:
            enriched = f"{tag} (${price:.2f}, {change:+.2f}%)"
            pattern = re.compile(rf"(?<!\\w){re.escape(tag)}(?![\\w])")
            tweet = pattern.sub(enriched, tweet)

    tweet = insert_mentions(tweet)
    tweet = re.sub(
        r"This is my opinion\\. Not financial advice\\.*",
        "",
        tweet,
        flags=re.IGNORECASE
    ).strip()
    tweet += f"\n\n{DISCLAIMER}"

    logger.info(f"Using theme: {theme}")
    logger.info(f"Using category: {category}")
    post_tweet(tweet, category=category, theme=theme)
    mark_headline_used_in_hourly_commentary(headline["headline"])
    track_theme(theme)
    logger.info(f"\\u2705 Posted hedge fund commentary tweet: {tweet}")

if __name__ == "__main__":
    load_recent_themes()
    post_hedgefund_comment()
