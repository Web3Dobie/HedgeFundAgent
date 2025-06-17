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

def score_headlines(items: list[dict], min_score: int = 6) -> list[dict]:
    """
    Score hedge fund-relevant headlines based on potential market impact and virality.
    Classify each as macro, political, or equity.
    """
    results = []
    for item in items:
        headline = item.get("headline", "")
        url = item.get("url", "")

        # Classify into macro, political, equity
        category = classify_headline_topic(headline)

        # Prompt for scoring relevance to hedge fund investors
        prompt = (
            f"As a hedge fund analyst, rate the market relevance of this headline on a scale from 1 to 10: '{headline}'\n"
            f"Score based on how much it would affect macro positioning or equity trades."
        )
        response = generate_gpt_text(prompt)

        try:
            raw = float(response.strip())
            score = int(round(raw))
        except Exception:
            score = 1

        score = max(1, min(score, 10))

        if score >= min_score:
            timestamp = datetime.utcnow().isoformat()
            record = {
                "headline": headline,
                "url": url,
                "ticker": category,  # repurposing ticker as macro/political/equity
                "score": score,
                "timestamp": timestamp,
            }
            _append_to_csv(record)
            logging.info(f"Scored: {headline} → {score} ({category})")
            results.append(record)
        else:
            logging.info(f"Skipped low-scoring headline: '{headline}' → {score}")

    return results

def _append_to_csv(record: dict):
    try:
        header = ["score", "headline", "url", "ticker", "timestamp"]
        os.makedirs(DATA_DIR, exist_ok=True)
        write_header = not os.path.exists(SCORED_CSV)

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
