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
from utils.fetch_stock_data import fetch_last_price_yf

logger = logging.getLogger("hedgefund_deep_dive")

def build_deep_dive_prompt(headline: str, summary: str) -> str:
    context = f"Headline: {headline.strip()}\n\nSummary: {summary.strip() or '[No summary available]'}"

    return (
        f"Write a 5-part Twitter thread like a hedge fund investor explaining this story.\n\n"
        f"{context}\n\n"
        f"Whenever you mention a stock ticker (cashtag like $XYZ), always include latest price and percent change "
        f"in this format: $XYZ ($123.45, +1.23%).\n\n"
        f"Structure the thread:\n"
        f"1. Explain the news\n"
        f"2. What markets care about\n"
        f"3. Implications (macro or stock-specific)\n"
        f"4. Similar historical precedent if any\n"
        f"5. View or positioning insight. Be analytical, not hypey."
    )

def post_hedgefund_deep_dive():
    logger.info("\ud83d\udcca Generating hedge fund deep-dive thread")

    top_headline = get_top_headline_today()
    if not top_headline:
        logger.warning("No top headline available for today's deep dive.")
        return

    logger.info(f"Selected deep dive headline: {top_headline['headline']}")

    prompt = build_deep_dive_prompt(top_headline["headline"], top_headline.get("summary", ""))
    thread = generate_gpt_thread(prompt, max_parts=5)

    if not thread or len(thread) < 3:
        logger.error("GPT did not return a valid deep-dive thread.")
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
        price_data = fetch_last_price_yf(ticker)
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