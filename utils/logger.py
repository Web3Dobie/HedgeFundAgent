# utils/logger.py - Simplified for HedgeFund database only

"""
Logger utility for recording tweet metrics to CSV and HedgeFund Notion database.
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


def log_tweet(tweet_id, date, tweet_category, url, likes, retweets, replies, engagement_score, tweet_text=None, theme=None):
    """
    Append tweet metrics to CSV and log to HedgeFund Notion database.
    
    Args:
        tweet_id: Twitter ID of the tweet
        date: Date string (YYYY-MM-DD format)
        tweet_category: Category/type of tweet
        url: URL to the tweet
        likes, retweets, replies: Engagement metrics
        engagement_score: Calculated engagement score
        tweet_text: Full text content of the tweet (optional)
        theme: Theme/topic extracted from the tweet content (optional)
    """
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    exists = os.path.exists(TWEET_LOG)
    
    with open(TWEET_LOG, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not exists:
            writer.writerow([
                "tweet_id", "date", "category", "url", "likes", "retweets", 
                "replies", "engagement_score", "text", "theme"
            ])
        writer.writerow([
            tweet_id, date, tweet_category, url, likes, retweets, 
            replies, engagement_score, tweet_text or "", theme or ""
        ])
    logging.info(f"Logged tweet {tweet_id} with category '{tweet_category}', theme '{theme}' to {TWEET_LOG}")

    # Log to HedgeFund Notion database
    try:
        from .notion_helper import log_hedgefund_tweet_to_notion
        success = log_hedgefund_tweet_to_notion(
            tweet_id=tweet_id,
            tweet_text=tweet_text or "",
            tweet_url=url,
            tweet_type=tweet_category,
            likes=likes,
            retweets=retweets,
            replies=replies
        )
        if success:
            logging.info(f"✅ Logged tweet {tweet_id} with category '{tweet_category}' to HedgeFund Notion database")
        else:
            logging.warning(f"⚠️ Failed to log tweet {tweet_id} to HedgeFund Notion database")
    except ImportError as e:
        logging.error(f"❌ Import error: {e}")
    except Exception as e:
        logging.error(f"❌ HedgeFund Notion log failed for tweet {tweet_id}: {e}")


# Backward compatibility functions
def log_tweet_legacy(tweet_id, date, tweet_type, url, likes, retweets, replies, engagement_score):
    """Legacy function for backward compatibility"""
    return log_tweet(tweet_id, date, tweet_type, url, likes, retweets, replies, engagement_score, None, None)