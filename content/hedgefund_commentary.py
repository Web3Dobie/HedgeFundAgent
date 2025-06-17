import logging
from datetime import datetime
import random

from utils.headline_pipeline import fetch_and_score_headlines
from utils.scorer import score_headlines
from utils.gpt import generate_gpt_tweet
from utils.text_utils import insert_cashtags, insert_mentions
from utils.x_post import post_tweet

logger = logging.getLogger("hedgefund_commentary")


CATEGORY_MACRO = "macro"
CATEGORY_EQUITY = "equity"

def classify_headline(headline: str) -> str:
    keywords_macro = ["trump", "europe", "china", "inflation", "fed", "ecb", "election", "tariffs", "geopolitical", "interest rate"]
    keywords_equity = ["earnings", "stock", "IPO", "revenue", "guidance", "CEO", "acquisition", "buyback"]
    
    hl = headline.lower()
    if any(word in hl for word in keywords_macro):
        return CATEGORY_MACRO
    elif any(word in hl for word in keywords_equity):
        return CATEGORY_EQUITY
    else:
        return random.choice([CATEGORY_MACRO, CATEGORY_EQUITY])  # fallback

def build_prompt(headline: str, category: str) -> str:
    if category == CATEGORY_MACRO:
        return f"Comment on this political/macro headline like a global macro hedge fund PM: '{headline}'"
    else:
        return f"Comment on this financial/corporate headline like an equity hedge fund PM: '{headline}'"

def post_hedgefund_comment():
    logger.info("🧠 Generating hedge fund investor comment")
    fetch_and_score_headlines()

    from utils.config import DATA_DIR
    import csv, os

    scored_path = os.path.join(DATA_DIR, "scored_headlines.csv")
    if not os.path.exists(scored_path):
        logger.warning("No scored headlines found.")
        return

    with open(scored_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    today = datetime.utcnow().date().isoformat()
    recent = [r for r in rows if r.get("timestamp", "").startswith(today)]

    if not recent:
        logger.warning("No recent headlines to comment on.")
        return

    headline = random.choice(recent)
    category = classify_headline(headline["headline"])
    prompt = build_prompt(headline["headline"], category)

    # Step 1: Generate the core insight (≤100 chars)
    core = generate_gpt_tweet(prompt)

    if core:
        # Step 2: Append cashtags and mentions AFTER core content
        tags = insert_cashtags(insert_mentions(""))
        tweet = f"{core} {tags}".strip()
        post_tweet(tweet, category=category)
    else:
        logger.error("GPT did not return a tweet.")

