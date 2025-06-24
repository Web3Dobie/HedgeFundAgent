import logging
from datetime import datetime
from utils.headline_pipeline import get_top_headline_last_7_days
from utils.gpt import generate_gpt_thread
from utils.text_utils import insert_mentions, insert_cashtags
from utils.x_post import post_thread

logger = logging.getLogger("hedgefund_deep_dive")

def build_deep_dive_prompt(headline: str) -> str:
    return (
        f"Write a 5-part Twitter thread like a hedge fund investor explaining this news: '{headline}'.\n"
        f"1. Explain the news\n2. What markets care about\n3. Implications (macro or stock-specific)\n"
        f"4. Similar historical precedent if any\n5. View or positioning insight. Be analytical, not hypey."
    )

def post_hedgefund_deep_dive():
    logger.info("📊 Generating hedge fund deep-dive thread")

    # Step 1: Fetch today's top headline
    today = datetime.utcnow().date().isoformat()
    headline = fetch_and_score_headlines(date=today)

    if not headline or len(headline) == 0:
        logger.warning("No top headline available for today's deep-dive.")
        return

    # Select the highest scoring headline for today
    top_headline = max(headline, key=lambda h: h.get("score", 0))
    logger.info(f"Today's top headline selected: {top_headline['headline']}")

    # Step 2: Build initial prompt
    prompt = build_deep_dive_prompt(top_headline["headline"])

    # Step 3: Generate initial thread
    thread = generate_gpt_thread(prompt, max_parts=5)

    if thread and len(thread) >= 3:
        # Step 4: Extract all cashtags across all parts of the thread
        cashtags = set()
        for part in thread:
            cashtags.update(insert_cashtags(part))  # `insert_cashtags` extracts and adds cashtags

        logger.info(f"Identified cashtags for thread enrichment: {cashtags}")

        # Step 5: Fetch real-time market prices for identified tickers
        prices = {tag: fetch_market_price(tag.strip("$")) for tag in cashtags}

        # Step 6: Enhance each part with price data and enrich content
        enriched = []
        for i, part in enumerate(thread):
            enriched_part = part
            for tag, price in prices.items():
                if f"${tag}" in part and price:
                    enriched_part += f" (Latest price: ${price:.2f})"
            enriched_part = insert_mentions(insert_cashtags(enriched_part))
            enriched.append(enriched_part)

        # Step 7: Post the enriched deep-dive thread
        post_thread(enriched, category="deep_dive")
    else:
        logger.error("GPT did not return a valid deep-dive thread.")

