"""
GPT-based scoring for hedge fund investor headlines.
Logs scores to CSV (and optionally to Notion).
"""
import csv
import logging
import os
from datetime import datetime

from .config import DATA_DIR, LOG_DIR
from .gpt import generate_gpt_text
from .text_utils import classify_headline_topic  # new utility we'll add for tagging

# Configure logging
log_file = os.path.join(LOG_DIR, "scorer.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

SCORED_CSV = os.path.join(DATA_DIR, "scored_headlines.csv")
model_name = "gpt-4o"  # Use the latest model for scoring

def score_headlines(items: list[dict], min_score: int = 8) -> list[dict]:
    """
    Score headlines using GPT with enhanced scoring system.
    Returns list of headlines scored >= min_score.
    """
    # Step 1: Score all headlines first with more detailed criteria
    scored_items = []
    
    failed_count=0
    for item in items:
        item.setdefault("score", 1)  # Default score if not set
        item.setdefault("ticker", classify_headline_topic(item.get("headline", "")))
        item.setdefault("url", "")
        item.setdefault("timestamp", datetime.utcnow().isoformat())
        scored_items.append(item)
        # Generate prompt for GPT
        prompt = (
            f"As a hedge fund analyst, rate this headline's market impact from 1-10:\n"
            f"'{item['headline']}'\n\n"
            f"Consider these factors:\n"
            f"- Immediate market moving potential (price action)\n"
            f"- Broader economic implications\n"
            f"- Policy/regulatory impact\n"
            f"- Sector-wide effects\n"
            f"- Geopolitical significance\n"
            f"- Trading volume implications\n\n"
            f"Score 8-10 for headlines that combine multiple major factors.\n"
            f"Return only the number."
        )
        # Generate GPT response
        raw = generate_gpt_text(prompt, model_name=model_name, max_tokens=10)

        if not raw or raw.strip() == "":
            logging.error(f"GPT returned an empty response for headline: '{item['headline']}'")
            failed_count += 1
            item['score'] = 1  # Assign default score for empty GPT response
        else:
            try:
                # Parse and constrain score between 1 and 10
                item['score'] = parse_score(raw)  # Assume parse_score is implemented correctly
            except Exception as e:
                logging.error(f"Failed to parse GPT response for headline: '{item['headline']}', Error: {e}")
                item['score'] = 1  # Default score for parsing failure
                failed_count += 1

        # Append item with updated score to the result list (only if >= min_score)
        if item['score'] >= min_score:
            scored_items.append(item)

    logging.info(f"Total headlines processed: {len(items)}")
    logging.info(f"Total GPT failures: {failed_count}")

    return scored_items

    # Step 2: Enhanced trend detection
    batch = "\n".join(f"- {i['headline']}" for i in scored_items)
    trend_prompt = (
        "From these headlines, identify the 3 most significant market-moving stories.\n"
        "Consider combinations of:\n"
        "- Major policy changes\n"
        "- Geopolitical tensions\n"
        "- Significant market shifts\n"
        "- Economic data surprises\n"
        "- Cross-asset implications\n\n"
        f"{batch}\n\n"
        "Reply with exact headlines, one per line."
    )
    hot_lines = generate_gpt_text(trend_prompt, model_name = model_name, max_tokens=200).splitlines()
    hot_set = set(h.strip() for h in hot_lines)

    # Step 3: Apply enhanced boost for trending themes
    results = []
    for item in scored_items:
        headline = item['headline']
        # Boost score for trending themes (+3 instead of +2)
        if headline in hot_set:
            item['score'] = min(10, item['score'] + 3)
            
        # Only include items meeting minimum score
        if item['score'] >= min_score:
            _append_to_csv({
                "headline": headline,
                "url": item.get("url", ""),
                "ticker": item.get("ticker", ""),
                "score": item['score'],
                "timestamp": item.get("timestamp", datetime.utcnow().isoformat()),
            })
            results.append(item)

    return results

def parse_score(raw_response: str) -> int:
    """
    Parse the score returned by GPT, ensuring it's between 1 and 10.
    Args:
        raw_response (str): Raw GPT response.
    Returns:
        int: Parsed score (default to 1 for failures).
    """
    try:
        # Attempt to parse numeric value
        score = float(raw_response.strip())
        return min(10, max(1, int(round(score))))
    except ValueError:
        logging.error(f"Failed to parse score from response: '{raw_response}'")
        return 1  # Default score on failure


def _append_to_csv(record: dict):
    try:
        header = ["score", "headline", "url", "ticker", "timestamp", "used_in_hourly_commentary"]
        os.makedirs(DATA_DIR, exist_ok=True)
        write_header = not os.path.exists(SCORED_CSV)

        # Ensure default for the new column
        record.setdefault("used_in_hourly_commentary", "False")

        with open(SCORED_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if write_header:
                writer.writeheader()
            writer.writerow(record)
    except Exception as e:
        logging.error(f"Failed to write to CSV: {e}")
        raise

def write_headlines(records: list[dict]):
    for rec in records:
        rec.setdefault("url", "")
        rec.setdefault("ticker", classify_headline_topic(rec.get("headline", "")))
        rec.setdefault("timestamp", datetime.utcnow().isoformat())
        _append_to_csv(rec)
