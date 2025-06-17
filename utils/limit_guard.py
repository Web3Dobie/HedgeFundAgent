"""
Guard to enforce a maximum number of tweets per day.
"""

import csv
import logging
import os
from datetime import date

from .config import DATA_DIR, LOG_DIR

# Configure logging
log_file = os.path.join(LOG_DIR, "limit_guard.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# CSV file for recording tweets
LOG_FILE = os.path.join(DATA_DIR, "tweet_log.csv")

# Maximum daily tweets (override via env var if needed)
MAX_DAILY_TWEETS = int(os.getenv("MAX_DAILY_TWEETS", 17))


def has_reached_daily_limit() -> bool:
    """
    Returns True if the number of tweets logged for today
    has reached or exceeded MAX_DAILY_TWEETS.
    """
    if not os.path.exists(LOG_FILE):
        logging.info("No tweet log file found; daily limit not reached.")
        return False

    today = date.today().isoformat()
    count = 0

    with open(LOG_FILE, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            timestamp = row.get("timestamp") or row.get("date")
            if timestamp and timestamp.startswith(today):
                count += 1

    logging.info(f"Tweets today: {count}; Limit: {MAX_DAILY_TWEETS}")
    return count >= MAX_DAILY_TWEETS
