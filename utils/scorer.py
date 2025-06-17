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

def score_headlines(items: list[dict], min_score: int = 8) -> list[dict]:
    results = []
    # Step 1: initial GPT relevance scoring
    for item in items:
        prompt = (
            f"As a hedge fund analyst focused on macro events, "
            f"rate on 1–10 how much this headline affects global markets: '{item['headline']}'"
        )
        raw = generate_gpt_text(prompt, max_tokens=10)
        try:
            score = min(10, max(1, int(round(float(raw.strip())))))
        except:
            score = 1
        item['score'] = score
    # Filter by base threshold
    scored = [i for i in items if i['score'] >= min_score]

    if not scored:
        return []

    # Step 2: GPT-powered trend detection within batch
    batch = "\n".join(f"- {i['headline']}" for i in scored)
    trend_prompt = (
        "Here are recent headlines:\n" + batch +
        "\n\nWhich top 2 reflect the most important macro themes right now? "
        "Reply using the full headlines, one per line."
    )
    hot_lines = generate_gpt_text(trend_prompt, max_tokens=60).splitlines()
    hot_set = set(h.strip() for h in hot_lines)

    # Step 3: boost trending headlines
    for item in scored:
        headline = item['headline']
        if headline in hot_set:
            item['score'] = min(10, item['score'] + 2)
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
