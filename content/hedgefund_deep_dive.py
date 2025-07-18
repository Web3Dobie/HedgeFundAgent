import logging
import re
from datetime import datetime
from utils.headline_pipeline import get_top_headline_today
from utils.gpt import generate_gpt_thread
from utils.theme_tracker import extract_theme
from utils.text_utils import (
    insert_mentions,
    extract_cashtags,
    is_valid_ticker
)
from utils.x_post import post_thread
from utils.fetch_stock_data import fetch_last_price
from utils.market_data import fetch_last_price

logger = logging.getLogger("hedgefund_deep_dive")

def build_deep_dive_prompt(headline: str, summary: str) -> str:
    context = f"Headline: {headline.strip()}\n\nSummary: {summary.strip() or '[No summary available]'}"

    return (
    f"Write a 3-part Twitter thread like a hedge fund investor explaining this story.\n\n"
    f"{context}\n\n"
    f"Whenever you mention a stock ticker (cashtag like $XYZ), always include latest price and percent change "
    f"in this format: $XYZ ($123.45, +1.23%).\n\n"
    f"Structure the thread:\n"
    f"1. Explain the news\n"
    f"2. What markets care about\n"
    f"3. Implications (macro or stock-specific), or your analytical view. Be analytical, not hypey."
)

def post_hedgefund_deep_dive():
    logger.info("\ud83d\udcca Generating hedge fund deep-dive thread")

    top_headline = get_top_headline_today()
    if not top_headline:
        logger.warning("No top headline available for today's deep dive.")
        return

    logger.info(f"Selected deep dive headline: {top_headline['headline']}")

    prompt = build_deep_dive_prompt(top_headline["headline"], top_headline.get("summary", ""))
    thread = generate_gpt_thread(prompt, max_parts=3)

   # === Begin Content Filter Handling Patch ===
    # If thread is a dict and Azure flagged it, or it's empty/None
    if isinstance(thread, dict) and thread.get("error", {}).get("code") == "contentfilter":
        logger.warning(f"[FILTERED] Deep dive blocked by Azure content filter: {top_headline['headline']}")
        mark_headline_used_in_hourly_commentary(top_headline["headline"], reason="filtered")
        return

    if not thread or not isinstance(thread, list) or not any(thread):
        logger.error(f"[EMPTY] Deep dive failed for: {top_headline['headline']}")
        mark_headline_used_in_hourly_commentary(top_headline["headline"], reason="empty")
        return

    # Extract unique cashtags from all parts
    all_cashtags = set()
    for part in thread:
        all_cashtags.update(extract_cashtags(part))

    all_cashtags = set(tag for tag in all_cashtags if is_valid_ticker(tag.strip("$")))

    logger.info(f"Valid cashtags for enrichment: {all_cashtags}")

    # Fetch prices using yfinance
    prices = {}
    for tag in all_cashtags:
        ticker = tag.strip("$")
        price_data = fetch_last_price(ticker)
        if price_data:
            prices[tag] = price_data

    logger.info(f"Fetched price data: {prices}")

    # Replace each cashtag with enriched format in each thread part
    enriched = []
    for part in thread:
        enriched_part = part
        for tag, data in prices.items():
            price = data.get("price")
            change = data.get("change_percent")
            if price is not None and change is not None:
                enriched_str = f"{tag} (${price:.2f}, {change:+.2f}%)"
                pattern = re.compile(rf"(?<!\w){re.escape(tag)}(?![\w])")
                enriched_part = pattern.sub(enriched_str, enriched_part)

        enriched_part = insert_mentions(enriched_part)
        enriched.append(enriched_part)

    # Clean and append disclaimer to final part
    enriched[-1] = re.sub(
        r"This is my opinion\\. Not financial advice\\.*",
        "",
        enriched[-1],
        flags=re.IGNORECASE
    ).strip()
    enriched[-1] += "\n\nThis is my opinion. Not financial advice."

    # Post the full thread
    post_thread(enriched, category="deep_dive", theme=extract_theme(top_headline["headline"]))
    logger.info("\u2705 Deep-dive thread posted successfully.")