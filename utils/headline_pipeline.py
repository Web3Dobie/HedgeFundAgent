"""
Fetches, dedupes, and scores headlines.
Reads & writes only to scored_headlines.csv via scorer.
"""

import csv
import logging
import os
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR, LOG_DIR
from .rss_fetch import fetch_headlines
from .scorer import score_headlines
from .text_utils import classify_headline_topic

# Logging setup
log_file = os.path.join(LOG_DIR, "headline_pipeline.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file, level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

SCORED_FILE = os.path.join(DATA_DIR, "scored_headlines.csv")


def fetch_and_score_headlines(limit=1000):
    """
    Fetch via RSS, skip already seen, then score new headlines.
    """
    logging.info("Starting headline ingestion and scoring...")
    headlines = fetch_headlines(limit=limit)
    logging.info(f"Fetched {len(headlines)} headlines.")

    seen = set()
    if os.path.exists(SCORED_FILE):
        with open(SCORED_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # dedupe on headline text
            seen = {row["headline"] for row in reader}

    new = [h for h in headlines if h["headline"] not in seen]
    if not new:
        logging.info("No new headlines to score.")
        return

    # Use extract_ticker(...) on each new headline before scoring
    enriched = []
    for h in new:
            ticker = classify_headline_topic(h["headline"])
            enriched.append({
                "headline": h["headline"],
                "url":      h.get("url", ""),
                "ticker":   ticker,
            })

    records = score_headlines(enriched)

    logging.info(f"[OK] Scored and recorded {len(records)} new headlines.")


def get_top_headline_last_7_days():
    """
    Returns the highest-scoring headline from the past week.
    """
    try:
        with open(SCORED_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        logging.warning("[ALERT] No scored headlines file found.")
        return None
    # Compute an AWARE datetime (UTC) for one week ago
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Build a list of rows whose timestamp (ISO format) is within the last 7 days.
    # We parse each r["timestamp"], then force it to UTC if it was naive:
    recent = []
    for r in rows:
        try:
            parsed = datetime.fromisoformat(r["timestamp"])
        except ValueError:
            # If the timestamp string isn't valid ISO, skip this row.
            continue

        # If parsed has no tzinfo (naive), assume UTC:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        # Now both sides (parsed and one_week_ago) are UTC‐aware, so this comparison is safe:
        if parsed >= one_week_ago:
             recent.append(r)
    
    if not recent:
        logging.info("[ERROR] No headlines in the past 7 days.")
        return None

    # Choose the row with max float(score)
    top = max(recent, key=lambda r: float(r["score"]))
    return {"headline": top["headline"], "url": top["url"]}

def get_top_headline_today():
    """
    Returns the highest-scoring headline from today.
    """
    try:
        with open(SCORED_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        logging.warning("[ALERT] No scored headlines file found.")
        return None

    today = datetime.utcnow().date().isoformat()
    today_rows = [r for r in rows if r.get("timestamp", "").startswith(today)]

    if not today_rows:
        logging.info("[INFO] No scored headlines for today.")
        return None

    top = max(today_rows, key=lambda r: float(r["score"]))
    return {
        "headline": top["headline"],
        "url": top["url"],
        "score": top["score"]
    }

    