import logging
import re
from datetime import datetime
from utils.headline_pipeline import get_top_headline_today
from utils.gpt import generate_gpt_thread
from utils.text_utils import (
    insert_mentions, 
    insert_cashtags, 
    extract_cashtags,
    enrich_cashtags_with_price
)
from utils.x_post import post_thread
from utils.fetch_stock_data import fetch_latest_price_yf

logger = logging.getLogger("hedgefund_deep_dive")


def build_deep_dive_prompt(headline: str) -> str:
    return (
        f"Write a 5-part Twitter thread like a hedge fund investor explaining this news: '{headline}'.\n"
        f"Whenever you mention a stock ticker (cashtag like $XYZ), always include latest price and percent change "
        f"in this format: $XYZ ($123.45, +1.23%).\n"
        f"1. Explain the news\n2. What markets care about\n3. Implications (macro or stock-specific)\n"
        f"4. Similar historical precedent if any\n5. View or positioning insight. Be analytical, not hypey."
    )

def post_hedgefund_deep_dive():
    logger.info("📊 Generating hedge fund deep-dive thread")

    top_headline = get_top_headline_today()
    if not top_headline:
        logger.warning("No top headline available for today's deep dive.")
        return

    logger.info(f"Selected deep dive headline: {top_headline['headline']}")

    prompt = build_deep_dive_prompt(top_headline["headline"])
    thread = generate_gpt_thread(prompt, max_parts=5)

    if not thread or len(thread) < 3:
        logger.error("GPT did not return a valid deep-dive thread.")
        return

    # Collect cashtags from all parts
    all_cashtags = set()
    for part in thread:
        all_cashtags.update(extract_cashtags(part))

    if not all_cashtags:
        logger.info("No cashtags found — skipping price enrichment.")

    # Optionally cap to avoid excessive lookups
    all_cashtags = set(list(all_cashtags)[:5])

    logger.info(f"Identified cashtags for thread enrichment: {all_cashtags}")

    # Fetch prices using yfinance
    prices = {}
    for tag in all_cashtags:
        ticker = tag.strip("$")
        price_data = fetch_latest_price_yf(ticker)
        if price_data:
            prices[tag] = price_data

    logger.info(f"Fetched price data: {prices}")

   # Enrich each thread part
    enriched = []
    for i, part in enumerate(thread):
        enriched_part = enrich_cashtags_with_price(part, prices)
        enriched_part = insert_mentions(enriched_part)
        enriched_part = insert_cashtags(enriched_part)
        enriched.append(enriched_part)

    # Clean and append disclaimer to final part
    enriched[-1] = re.sub(
        r"This is my opinion\. Not financial advice\.*",
        "",
        enriched[-1],
        flags=re.IGNORECASE
    ).strip()
    enriched[-1] += "\n\nThis is my opinion. Not financial advice."

    # Post the full thread
    post_thread(enriched, category="deep_dive", theme=extract_theme(top_headline["headline"]))

    logger.info("✅ Deep-dive thread posted successfully.")
