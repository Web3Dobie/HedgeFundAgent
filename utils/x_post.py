"""
X Post Utilities: posting tweets, quote tweets, and threads to X.
Includes retry-safe, non-blocking logic and HTTP timing for diagnostics.
"""

import http.client as http_client
import threading
import time
from datetime import datetime, timezone
import tweepy

from utils.telegram_log_handler import TelegramHandler
from .config import (
    LOG_DIR,
    TWITTER_CONSUMER_KEY,
    TWITTER_CONSUMER_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET,
    BOT_USER_ID,
)
from .limit_guard import has_reached_daily_limit
from .logger import log_tweet
import requests
import csv
import sys


# ─── HTTP & Library Debug Setup ─────────────────────────────────────────
import logging
import os

def log_thread_diagnostics(thread_parts: list[str], category: str, theme: str):
    """Log detailed diagnostics about the thread being posted"""
    logging.info("-" * 80)
    logging.info(f"🔍 Thread Diagnostics:")
    logging.info(f"Category: {category}")
    logging.info(f"Theme: {theme}")
    logging.info(f"Parts: {len(thread_parts)}")
    logging.info(f"Total characters: {sum(len(p) for p in thread_parts)}")
    for i, part in enumerate(thread_parts):
        logging.info(f"Part {i+1} length: {len(part)} chars")
    logging.info("-" * 80)

# Create a dedicated HTTP debug log file
http_log_file = os.path.join(LOG_DIR, 'x_post_http.log')
http_handler = logging.FileHandler(http_log_file)
http_handler.setLevel(logging.DEBUG)
http_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Create HTTP debug logger
http_logger = logging.getLogger('http_debug')
http_logger.setLevel(logging.DEBUG)
http_logger.addHandler(http_handler)
http_logger.propagate = False

# Set up other HTTP loggers to only write to file
for logger_name in ['urllib3', 'tweepy']:
    logger = logging.getLogger(logger_name)
    logger.handlers = [http_handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

# Main application logging - WARNING level for terminal
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, 'x_post.log')
logging.basicConfig(
    filename=log_file,
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Add Telegram handler for errors
tg_handler = TelegramHandler()
tg_handler.setLevel(logging.ERROR)
tg_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logging.getLogger().addHandler(tg_handler)

# ─── Tweepy Client Initialization ────────────────────────────────────────
client = tweepy.Client(
    consumer_key=TWITTER_CONSUMER_KEY,
    consumer_secret=TWITTER_CONSUMER_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET,
    wait_on_rate_limit=True,
)

MAX_TWEET_RETRIES = 3
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAYS = [300, 600, 900]  # 5min, 10min, 15min progressive delays
THREAD_RETRY_DELAY = 900  # 15 minutes for thread retries
SINGLE_TWEET_RETRY_DELAY = 600  # 10 minutes for single tweet retries
RATE_LIMIT_DELAY = 5  # 5 seconds between tweets to avoid hitting rate limits

# Initialize v1.1 API client for media uploads
auth = tweepy.OAuth1UserHandler(
    TWITTER_CONSUMER_KEY,
    TWITTER_CONSUMER_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET
)
api = tweepy.API(auth)

# --- Ping Twitter API to ensure connection is alive ---
def ping_twitter_api():
    """Optional: Ping Twitter API to check if reachable before posting."""
    try:
        resp = requests.get("https://api.twitter.com/2/tweets", timeout=5)
        logging.debug(f"Ping Twitter API status: {resp.status_code}")
        return resp.status_code == 200 or resp.status_code == 401  # 401 if no auth, but endpoint is up
    except Exception as e:
        logging.error(f"Ping to Twitter API failed: {e}")
        return False

# ─── Timing Wrapper ─────────────────────────────────────────────────────
def timed_create_tweet(text: str, in_reply_to_tweet_id=None, part_index: int = None, media_ids=None, retry_count=0):
    """Wrapped tweet creation with timing, retries and error handling"""
    start = time.monotonic()
    try:
        logging.debug(f"Making API request: POST https://api.twitter.com/2/tweets")
        logging.debug(f"Parameters: text={text[:50]}..., in_reply_to_tweet_id={in_reply_to_tweet_id}, part_index={part_index}")
        
        # Try to create tweet
        resp = client.create_tweet(
            text=text,
            in_reply_to_tweet_id=in_reply_to_tweet_id,
            media_ids=media_ids
        )
        elapsed = time.monotonic() - start
        logging.debug(f"HTTP POST /2/tweets succeeded in {elapsed:.2f}s (part {part_index})")
        return resp

    except (tweepy.errors.TweepyException, requests.exceptions.RequestException, ConnectionError) as e:
        elapsed = time.monotonic() - start
        error_str = str(e).lower()
        
        # Handle connection timeouts and errors
        if ('timeout' in error_str or 'connection' in error_str) and retry_count < MAX_RETRY_ATTEMPTS:
            delay = RETRY_DELAYS[retry_count]
            logging.warning(f"Connection issue on attempt {retry_count + 1}/{MAX_RETRY_ATTEMPTS}. Retrying in {delay}s")
            time.sleep(delay)
            return timed_create_tweet(text, in_reply_to_tweet_id, part_index, media_ids, retry_count + 1)
            
        # If max retries reached or other error, log and raise
        logging.error(f"HTTP POST /2/tweets failed after {elapsed:.2f}s (part {part_index}): {e}")
        raise

    except Exception as e:
        elapsed = time.monotonic() - start
        logging.error(f"HTTP POST /2/tweets failed after {elapsed:.2f}s (part {part_index}): {e}")
        raise

# --- Log tweet to CSV file
TWEET_LOG_FILE = os.path.join(LOG_DIR, "tweet_log.csv")

def log_tweet_to_csv(tweet_id: str, timestamp: str, tweet_type: str, category: str, theme: str, url: str,
                     likes: int = 0, retweets: int = 0, replies: int = 0, impressions: int = 0, engagement_score: int = 0):
    header = ["tweet_id", "timestamp", "type", "category", "theme", "url", "likes", "retweets", "replies", "impressions", "engagement_score"]
    write_header = not os.path.exists(TWEET_LOG_FILE)

    row = {
        "tweet_id": tweet_id,
        "timestamp": timestamp,
        "type": tweet_type,
        "category": category,
        "theme": theme,
        "url": url,
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "impressions": impressions,
        "engagement_score": engagement_score
    }

    try:
        with open(TWEET_LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logging.error(f"❌ Failed to write tweet log: {e}")

# --- Upload Media
def upload_media(image_path):
    """
    Uploads an image to Twitter/X and returns the media_id.
    Uses v1.1 API for media upload.
    """
    try:
        media = api.media_upload(filename=image_path)
        return media.media_id
    except Exception as e:
        logging.error(f"❌ Failed to upload media {image_path}: {e}")
        return None

# ─── Standalone Tweet ────────────────────────────────────────────────────
def post_tweet(text: str, category: str, theme: str):
    if has_reached_daily_limit():
        logging.warning('🚫 Daily tweet limit reached — skipping standalone tweet.')
        return
    try:
        resp = timed_create_tweet(text=text, part_index=1)
        tweet_id = resp.data['id']
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        log_tweet_to_csv(
            tweet_id=tweet_id,
            timestamp=date_str,
            tweet_type='tweet',
            category=category,
            theme=theme, 
            url=url,
            likes=0,  # Initial values, can be updated later
            retweets=0,
            replies=0,
            impressions=0,
            engagement_score=0
        )
        logging.info(f"✅ Posted tweet: {url}")
    except Exception as e:
        logging.error(f"❌ Error posting tweet: {e}")

# ─── Quote Tweet ────────────────────────────────────────────────────────
def post_quote_tweet(text: str, tweet_url: str, category: str, theme: str):
    if has_reached_daily_limit():
        logging.warning('🚫 Daily tweet limit reached — skipping quote tweet.')
        return
    try:
        quote_id = tweet_url.rstrip('/').split('/')[-1]
        resp = client.create_tweet(text=text, quote_tweet_id=quote_id)
        tweet_id = resp.data['id']
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        log_tweet_to_csv(
            tweet_id=tweet_id,
            timestamp=date_str,
            tweet_type='quote-tweet',
            category=category,
            theme=theme, 
            url=url,
            likes=0,  # Initial values, can be updated later
            retweets=0,
            replies=0,
            impressions=0,
            engagement_score=0
        )
        logging.info(f"✅ Posted quote tweet: {url}")
    except Exception as e:
        logging.error(f"❌ Error posting quote tweet: {e}")

# ─── Thread Posting ─────────────────────────────────────────────────────
def post_thread(
    thread_parts: list[str],
    category: str,
    theme: str,
    previous_id=None,
    retry=False,
    media_id_first=None  # <-- Add this argument
):

    """Post a thread with enhanced diagnostics and retry handling"""
    # Add detailed diagnostics
    log_thread_diagnostics(thread_parts, category, theme)
    
    # Add connection quality check
    start_ping = time.monotonic()
    api_status = ping_twitter_api()
    ping_time = time.monotonic() - start_ping
    logging.info(f"🌐 API Connection Check: {'✅' if api_status else '❌'} ({ping_time:.2f}s)")


    if has_reached_daily_limit():
        logging.warning('🚫 Daily tweet limit reached — skipping thread.')
        return {
            "posted": 0,
            "total": len(thread_parts) if thread_parts else 0,
            "error": "Daily limit reached"
        }

    if not thread_parts:
        logging.warning('⚠️ No thread parts provided; skipping thread.')
        return {
            "posted": 0,
            "total": 0,
            "error": "No thread parts provided"
        }

    # Optional: Pre-flight check
    if not ping_twitter_api():
        logging.error("❌ Twitter API is unreachable before posting thread.")
        return {
            "posted": 0,
            "total": len(thread_parts),
            "error": "Twitter API unreachable"
        }

    logging.info(f"{'🔁 Retrying' if retry else '📢 Posting'} thread of {len(thread_parts)} parts under category '{category}'.")
    posted = 0
    try:
        # First tweet
        if previous_id:
            in_reply_to = previous_id
            parts_to_post = thread_parts
        else:
            first = thread_parts[0]
            logging.debug(f"Posting first thread tweet: {first[:60]}...")
            try:
                resp = timed_create_tweet(
                    text=first,
                    part_index=1,
                    media_ids=[media_id_first] if media_id_first else None
                )
                tweet_id = resp.data['id']
                date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
                log_tweet_to_csv(
                    tweet_id=tweet_id,
                    timestamp=date_str,
                    tweet_type='thread',
                    category=category,
                    theme=theme, 
                    url=url,
                    likes=0,  # Initial values, can be updated later
                    retweets=0,
                    replies=0,
                    impressions=0,
                    engagement_score=0
                )
                logging.info(f"✅ Posted thread first tweet: {url}")
                in_reply_to = tweet_id
                posted = 1
                parts_to_post = thread_parts[1:]
            except Exception as e:
                logging.error(f"❌ Failed to post first tweet: {e}")
                raise
    
        # Replies
        for part in parts_to_post:
            if not part:
                logging.warning(f"⚠️ Skipping empty part {posted+1}")
                continue
            
            time.sleep(RATE_LIMIT_DELAY)  # Basic rate limiting
            try:
                logging.debug(f"Posting thread reply {posted+1}: {part[:60]}...")
                resp = timed_create_tweet(
                    text=part,
                    in_reply_to_tweet_id=in_reply_to,
                    part_index=posted+1
                )
                in_reply_to = resp.data['id']
                reply_url = f"https://x.com/{BOT_USER_ID}/status/{in_reply_to}"
                log_tweet_to_csv(
                    tweet_id=in_reply_to,
                    timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                    tweet_type='thread-reply',
                    category=category,
                    theme=theme,
                    url=reply_url,
                    likes=0,
                    retweets=0,
                    replies=0,
                    impressions=0,
                    engagement_score=0
            )

                logging.info(f"↪️ Posted thread reply: {reply_url}")
                posted += 1
            except Exception as e:
                # If we've posted at least one tweet, schedule retry for remaining
                if posted > 0:
                    remaining = thread_parts[posted:]
                    schedule_retry_thread(remaining, in_reply_to, category)
                logging.error(f"❌ Error posting part {posted+1}: {e}")
                raise

        return {
            "posted": posted,
            "total": len(thread_parts)
        }

    except Exception as e:
        logging.error(f"❌ General error posting thread: {e}")
        return {
            "posted": posted,
            "total": len(thread_parts),
            "error": str(e)
        }


# ─── Retry Schedulers ───────────────────────────────────────────────────
def schedule_retry_thread(remaining_parts: list[str], reply_to_id: str, category: str, theme: str):
    logging.info(f"⏳ Scheduling retry for {len(remaining_parts)} parts in 15 minutes.")
    def retry_call():
        post_thread(remaining_parts, category=category, theme = theme, previous_id=reply_to_id, retry=True)
    threading.Timer(THREAD_RETRY_DELAY, retry_call).start()


def schedule_retry_single_tweet(part: str, reply_to_id: str, category: str, theme: str, retries: int = 1):
    if retries > MAX_TWEET_RETRIES:
        logging.error('❌ Max retries reached for single tweet — giving up.')
        return

    logging.info(f"⏳ Scheduling retry {retries}/{MAX_TWEET_RETRIES} for single tweet in 10 minutes.")
    def retry_call():
        try:
            resp = timed_create_tweet(text=part, in_reply_to_tweet_id=reply_to_id, part_index=None)
            in_reply = resp.data['id']
            reply_url = f"https://x.com/{BOT_USER_ID}/status/{in_reply}"
            log_tweet_to_csv(
                tweet_id=in_reply,
                timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                tweet_type='thread-reply',
                category=category,
                theme=theme,
                url=reply_url,
                likes=0,
                retweets=0,
                replies=0,
                impressions=0,
                engagement_score=0
            )

            logging.info(f"✅ Retry success: Posted single tweet: {reply_url}")
        except Exception as e:
            error_str = str(e).lower()
            if 'timeout' in error_str or 'connection' in error_str:
                schedule_retry_single_tweet(part, reply_to_id, category, retries=retries+1)
            else:
                logging.error(f"❌ Retry failed with non-retryable error: {e}")
    threading.Timer(SINGLE_TWEET_RETRY_DELAY, retry_call).start()
