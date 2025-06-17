"""
Logger utility for recording tweet metrics to CSV and Notion.
"""

import csv
import logging
import os
from datetime import datetime

from .config import DATA_DIR, LOG_DIR

# Setup Python logging
log_file = os.path.join(LOG_DIR, "logger.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# CSV file for recording tweet metrics
TWEET_LOG = os.path.join(DATA_DIR, "tweet_log.csv")


def log_tweet(
    tweet_id, date, tweet_type, url, likes, retweets, replies, engagement_score
):
    """
    Append tweet metrics to a CSV and log to Notion.
    """
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    exists = os.path.exists(TWEET_LOG)
    with open(TWEET_LOG, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not exists:
            writer.writerow(
                [
                    "tweet_id",
                    "date",
                    "type",
                    "url",
                    "likes",
                    "retweets",
                    "replies",
                    "engagement_score",
                ]
            )
        writer.writerow(
            [
                tweet_id,
                date,
                tweet_type,
                url,
                likes,
                retweets,
                replies,
                engagement_score,
            ]
        )
    logging.info(f"Logged tweet {tweet_id} to {TWEET_LOG}")
