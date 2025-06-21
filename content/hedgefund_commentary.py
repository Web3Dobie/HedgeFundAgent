import logging
from datetime import datetime
import random
import csv, os

from utils.config import DATA_DIR
from utils.headline_pipeline import fetch_and_score_headlines
from utils.scorer import score_headlines
from utils.gpt import generate_gpt_tweet
from utils.text_utils import insert_cashtags, insert_mentions
from utils.x_post import post_tweet
from utils.hourly_utils import (
    get_unused_headline_today_for_hourly,
    mark_headline_used_in_hourly_commentary,
)

logger = logging.getLogger("hedgefund_commentary")


CATEGORY_MACRO = "macro"
CATEGORY_EQUITY = "equity"
CATEGORY_POLITICAL = "political"

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
        return f"Comment on this political/macro headline like a global macro hedge fund PM: '{headline}'"
    elif category == CATEGORY_POLITICAL:
        return f"Comment on this political headline like a hedge fund strategist: '{headline}'"
    else:
        return f"Comment on this financial/corporate headline like an equity hedge fund PM: '{headline}'"

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

    # Step 1: Load today's headlines that haven't been used for hourly commentary
    
    scored_path = os.path.join(DATA_DIR, "scored_headlines.csv")
    if not os.path.exists(scored_path):
        logger.warning("No scored headlines found.")
        return

    today = datetime.utcnow().date().isoformat()
    with open(scored_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Filter: today only, and not yet used in hourly commentary
    recent = [
        r for r in rows
        if r.get("timestamp", "").startswith(today) and
           r.get("used_in_hourly_commentary", "False").lower() != "true"
    ]

    if not recent:
        logger.warning("No unused headlines available for hourly commentary.")
        return

    # Step 2: Get the next category in rotation
    target_category = get_next_category()

    # Step 3: Filter headlines based on the desired category
    categorized = [r for r in recent if classify_headline(r["headline"]) == target_category]

    # Step 4: Use highest scoring headline from selected category or fallback to random
    if categorized:
        headline = max(categorized, key=lambda r: int(r["score"]))
    else:
        logger.warning(f"No headlines available for category '{target_category}', falling back to random.")
        headline = random.choice(recent)

    category = classify_headline(headline["headline"])
    prompt = build_prompt(headline["headline"], category)

    # Step 5: Generate tweet
    core = generate_gpt_tweet(prompt)

    if core:
        tagged = insert_mentions(core)
        tagged = insert_cashtags(tagged)
        tweet = f"{core} {tagged[len(core):].strip()}"
        post_tweet(tweet, category=category)
        mark_headline_used_in_hourly_commentary(headline["headline"])
    else:
        logger.error("GPT did not return a tweet.")


