import logging
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
    headline = get_top_headline_last_7_days()

    if not headline:
        logger.warning("No top headline available for deep-dive.")
        return

    prompt = build_deep_dive_prompt(headline["headline"])
    thread = generate_gpt_thread(prompt, max_parts=5)

    if thread and len(thread) >= 3:
        enriched = [insert_mentions(insert_cashtags(p)) for p in thread]
        post_thread(enriched, category="deep_dive")
    else:
        logger.error("GPT did not return a valid deep-dive thread.")
