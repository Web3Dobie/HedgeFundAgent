import logging
from datetime import datetime
from utils.headline_pipeline import get_top_headline_today
from utils.gpt import generate_gpt_thread
from utils.text_utils import insert_mentions, insert_cashtags
from utils.x_post import post_thread
from utils.fetch_stock_data import fetch_market_price

logger = logging.getLogger("hedgefund_deep_dive")


def build_deep_dive_prompt(headline: str) -> str:
    return (
        f"Write a 5-part Twitter thread like a hedge fund investor explaining this news: '{headline}'.\n"
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
    
    if thread and len(thread) >= 3:
        cashtags = set()
        for part in thread:
            cashtags.update(insert_cashtags(part))  # Assuming this extracts cashtags

        logger.info(f"Identified cashtags for thread enrichment: {cashtags}")

        prices = {tag: fetch_market_price(tag.strip("$")) for tag in cashtags}
        logger.info(f"Fetched price data: {prices}")

        enriched = []
        for part in thread:
            enriched_part = part
            for tag, price in prices.items():
                if price and "price" in price and f"${tag}" in part:

                    price_str = f"(Latest price: ${price['price']:.2f}"
                    if price.get("change_pct") is not None:
                        price_str += f", change: {price['change_pct']:+.2f}%)"
                    else:
                        price_str += ")"

                    enriched_part += f" {price_str}"
            enriched_part = insert_mentions(insert_cashtags(enriched_part))
            enriched.append(enriched_part)

        post_thread(enriched, category="deep_dive")
        logger.info("✅ Deep-dive thread posted successfully.")
    else:
        logger.error("GPT did not return a valid deep-dive thread.")
