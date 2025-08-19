"""
X Post Utilities: posting tweets, quote tweets, and threads to X.
Includes retry-safe, non-blocking logic and HTTP timing for diagnostics.
UPDATED: Full category and theme support for all functions.
"""

import http.client as http_client
import threading
import time
from datetime import datetime, timezone
import tweepy
from pdf2image import convert_from_path
import tempfile
import logging
import os
import csv
import sys
import requests

from utils.text_utils import get_briefing_caption, format_market_sentiment
from utils.telegram_log_handler import TelegramHandler
from .config import (
    LOG_DIR,
    TWITTER_CONSUMER_KEY,
    TWITTER_CONSUMER_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET,
    BOT_USER_ID,
    DATA_DIR,
)
from .limit_guard import has_reached_daily_limit
from .logger import log_tweet

# ─── Constants ──────────────────────────────────────────────────────────
RATE_LIMIT_DELAY = 5  # seconds between thread parts
THREAD_RETRY_DELAY = 15 * 60  # 15 minutes
SINGLE_TWEET_RETRY_DELAY = 10 * 60  # 10 minutes  
MAX_TWEET_RETRIES = 3
TWEET_LOG_FILE = os.path.join(DATA_DIR, "tweet_log.csv")

# ─── HTTP & Library Debug Setup ─────────────────────────────────────────
def log_thread_diagnostics(thread_parts: list[str], category: str, theme: str = None):
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
os.makedirs(LOG_DIR, exist_ok=True)
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

# Main application logging
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
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
logging.getLogger().addHandler(tg_handler)

# ─── Twitter API Setup ──────────────────────────────────────────────────
# OAuth 1.0a
auth = tweepy.OAuth1UserHandler(
    TWITTER_CONSUMER_KEY,
    TWITTER_CONSUMER_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_SECRET
)

# API v2 client
client = tweepy.Client(
    consumer_key=TWITTER_CONSUMER_KEY,
    consumer_secret=TWITTER_CONSUMER_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET,
    wait_on_rate_limit=True
)

# API v1.1 for media upload
api = tweepy.API(auth, wait_on_rate_limit=True)

# ─── CSV Logging ────────────────────────────────────────────────────────
def log_tweet_to_csv(tweet_id: str, timestamp: str, tweet_type: str, category: str, theme: str, 
                     url: str, likes: int = 0, retweets: int = 0, replies: int = 0, 
                     impressions: int = 0, engagement_score: int = 0):
    """Log tweet data to CSV file with category and theme support"""
    header = ["tweet_id", "timestamp", "type", "category", "theme", "url", "likes", "retweets", "replies", "impressions", "engagement_score"]
    write_header = not os.path.exists(TWEET_LOG_FILE)

    row = {
        "tweet_id": tweet_id,
        "timestamp": timestamp,
        "type": tweet_type,
        "category": category,
        "theme": theme or "",  # Handle None theme
        "url": url,
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "impressions": impressions,
        "engagement_score": engagement_score
    }

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TWEET_LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logging.error(f"❌ Failed to write tweet log: {e}")

# ─── Utility Functions ──────────────────────────────────────────────────
def upload_media(image_path):
    """Upload an image to Twitter/X and return the media_id"""
    try:
        media = api.media_upload(filename=image_path)
        return media.media_id
    except Exception as e:
        logging.error(f"❌ Failed to upload media {image_path}: {e}")
        return None

def ping_twitter_api() -> bool:
    """Check if Twitter API is reachable"""
    try:
        client.get_me()
        return True
    except Exception:
        return False

def timed_create_tweet(text: str, in_reply_to_tweet_id: str = None, part_index: int = None, 
                      media_ids: list = None, retry_count: int = 0) -> tweepy.Response:
    """Create tweet with timing and retry logic"""
    start = time.monotonic()
    
    try:
        # Log the request details
        http_logger.debug(f"Making API request: POST https://api.twitter.com/2/tweets")
        http_logger.debug(f"Parameters: {{}}")
        http_logger.debug(f"Headers: {{'User-Agent': 'Python/{sys.version.split()[0]} Requests/{requests.__version__} Tweepy/{tweepy.__version__}'}}")
        http_logger.debug(f"Body: {{'text': '{text[:100]}...', 'in_reply_to_tweet_id': '{in_reply_to_tweet_id}', 'media': '{media_ids}'}}")
        
        # Make the actual request
        kwargs = {"text": text}
        if in_reply_to_tweet_id:
            kwargs["in_reply_to_tweet_id"] = in_reply_to_tweet_id
        if media_ids:
            kwargs["media_ids"] = media_ids
            
        resp = client.create_tweet(**kwargs)
        
        elapsed = time.monotonic() - start
        http_logger.debug(f"Received API response: 201 Created")
        http_logger.debug(f"Response time: {elapsed:.3f}s")
        
        return resp
        
    except Exception as e:
        elapsed = time.monotonic() - start
        error_str = str(e).lower()
        
        # Check for retryable errors
        if ('timeout' in error_str or 'connection' in error_str) and retry_count < 3:
            delay = 30 * (2 ** retry_count)  # Exponential backoff
            logging.warning(f"⏳ HTTP timeout/connection error after {elapsed:.2f}s (part {part_index}). "
                          f"Retrying in {delay}s")
            time.sleep(delay)
            return timed_create_tweet(text, in_reply_to_tweet_id, part_index, media_ids, retry_count + 1)
            
        # If max retries reached or other error, log and raise
        logging.error(f"HTTP POST /2/tweets failed after {elapsed:.2f}s (part {part_index}): {e}")
        raise

# ─── Main Posting Functions ────────────────────────────────────────────

def post_tweet(text: str, category: str = 'original', theme: str = None) -> str:
    """Post a standalone tweet with category and theme support"""
    if has_reached_daily_limit():
        logging.warning('🚫 Daily tweet limit reached — skipping standalone tweet.')
        return None
    try:
        resp = timed_create_tweet(text=text, part_index=1)
        tweet_id = resp.data['id']
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        
        # Enhanced logging to both CSV and Notion
        log_tweet_to_csv(
            tweet_id=tweet_id,
            timestamp=date_str,
            tweet_type='tweet',
            category=category,
            theme=theme or "",
            url=url,
            likes=0,
            retweets=0,
            replies=0,
            impressions=0,
            engagement_score=0
        )
        
        # Log to Notion via the enhanced logger
        log_tweet(tweet_id, date_str, category, url, 0, 0, 0, 0, text, theme)
        
        logging.info(f"✅ Posted tweet: {url}")
        return url
    except Exception as e:
        logging.error(f"❌ Error posting tweet: {e}")
        return None

def post_tweet_with_media(text: str, image_path: str, category: str = 'original', theme: str = None) -> str:
    """Post a tweet with media attachment"""
    if has_reached_daily_limit():
        logging.warning('🚫 Daily tweet limit reached — skipping tweet with media.')
        return None
    try:
        media_id = upload_media(image_path)
        if not media_id:
            logging.error(f"❌ Could not upload media for {image_path}. Tweet not sent.")
            return None
            
        resp = timed_create_tweet(text=text, part_index=1, media_ids=[media_id])
        tweet_id = resp.data['id']
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        
        # Enhanced logging
        log_tweet_to_csv(
            tweet_id=tweet_id,
            timestamp=date_str,
            tweet_type='tweet_with_media',
            category=category,
            theme=theme or "",
            url=url,
            likes=0,
            retweets=0,
            replies=0,
            impressions=0,
            engagement_score=0
        )
        
        log_tweet(tweet_id, date_str, category, url, 0, 0, 0, 0, text, theme)
        
        logging.info(f"✅ Posted tweet with image: {url}")
        return url
    except Exception as e:
        logging.error(f"❌ Error posting tweet with media: {e}")
        return None

def post_quote_tweet(text: str, tweet_url: str, category: str = 'quote', theme: str = None) -> str:
    """Post a quote tweet with category and theme support"""
    if has_reached_daily_limit():
        logging.warning('🚫 Daily tweet limit reached — skipping quote tweet.')
        return None
    try:
        quote_id = tweet_url.rstrip('/').split('/')[-1]
        resp = client.create_tweet(text=text, quote_tweet_id=quote_id)
        tweet_id = resp.data['id']
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        
        # Enhanced logging
        log_tweet_to_csv(
            tweet_id=tweet_id,
            timestamp=date_str,
            tweet_type='quote-tweet',
            category=category,
            theme=theme or "",
            url=url,
            likes=0,
            retweets=0,
            replies=0,
            impressions=0,
            engagement_score=0
        )
        
        log_tweet(tweet_id, date_str, category, url, 0, 0, 0, 0, text, theme)
        
        logging.info(f"✅ Posted quote tweet: {url}")
        return url
    except Exception as e:
        logging.error(f"❌ Error posting quote tweet: {e}")
        return None

def post_thread(thread_parts: list[str], category: str = 'thread', theme: str = None, 
               previous_id: str = None, retry: bool = False, media_id_first: str = None) -> dict:
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
                date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
                
                # Enhanced logging for first tweet
                log_tweet_to_csv(
                    tweet_id=tweet_id,
                    timestamp=date_str,
                    tweet_type='thread',
                    category=category,
                    theme=theme or "",
                    url=url,
                    likes=0,
                    retweets=0,
                    replies=0,
                    impressions=0,
                    engagement_score=0
                )
                
                log_tweet(tweet_id, date_str, category, url, 0, 0, 0, 0, first, theme)
                
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
                
                # Enhanced logging for reply
                log_tweet_to_csv(
                    tweet_id=in_reply_to,
                    timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    tweet_type='thread-reply',
                    category=category,
                    theme=theme or "",
                    url=reply_url,
                    likes=0,
                    retweets=0,
                    replies=0,
                    impressions=0,
                    engagement_score=0
                )
                
                log_tweet(in_reply_to, datetime.now(timezone.utc).strftime('%Y-%m-%d'), 
                         category, reply_url, 0, 0, 0, 0, part, theme)

                logging.info(f"↪️ Posted thread reply: {reply_url}")
                posted += 1
            except Exception as e:
                # If we've posted at least one tweet, schedule retry for remaining
                if posted > 0:
                    remaining = thread_parts[posted:]
                    schedule_retry_thread(remaining, in_reply_to, category, theme)
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

# ─── PDF/Briefing Functions ─────────────────────────────────────────────

def post_pdf_briefing(filepath: str, period: str = "morning", headline: str = None, 
                     summary: str = None, equity_block: str = None, macro_block: str = None, 
                     crypto_block: str = None, category: str = "briefing", theme: str = None):
    """Post PDF briefing as PNG with category and theme support"""
    return timed_post_pdf_briefing(
        filepath=filepath,
        period=period,
        headline=headline,
        summary=summary,
        equity_block=equity_block,
        macro_block=macro_block,
        crypto_block=crypto_block,
        category=category,
        theme=theme or period
    )

def timed_post_pdf_briefing(
    filepath: str,
    period: str = "morning",
    headline: str = None,
    summary: str = None,
    equity_block: dict = None,
    macro_block: dict = None,
    crypto_block: dict = None,
    pdf_url: str = None,
    retry_count: int = 0,
    category: str = "briefing",
    theme: str = None
):
    """
    Posts a multi-part briefing thread on X (Twitter) including:
    - Main briefing tweet with PDF first page image
    - Sentiment reply tweet
    - Third tweet with PDF link and call to action

    Handles retries on main tweet failures and logs tweet IDs and URLs.

    Args:
        filepath (str): Local PDF file path.
        period (str): Briefing period (e.g., 'morning', 'pre_market').
        headline (str, optional): Headline for main tweet.
        summary (str, optional): Summary text for main tweet.
        equity_block (dict, optional): Equity prices for sentiment.
        macro_block (dict, optional): Macro prices for sentiment.
        crypto_block (dict, optional): Crypto prices for sentiment.
        pdf_url (str, optional): Public URL to the full PDF briefing.
        retry_count (int): Retry attempt count for main tweet.
        category (str): Category for logging (default: "briefing")
        theme (str): Theme for logging (default: period)
    """
    img_path = None
    temp_dir = None
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAYS = [30, 60, 120]  # seconds

    if has_reached_daily_limit():
        logging.warning(f"🚫 Daily tweet limit reached — skipping {period} briefing.")
        return

    try:
        # Convert PDF to PNG
        images = convert_from_path(filepath, dpi=200, first_page=1, last_page=1)
        if not images:
            logging.error("❌ PDF conversion failed — no pages rendered.")
            return

        temp_dir = tempfile.mkdtemp()
        img_path = os.path.join(temp_dir, "page_1.png")
        images[0].save(img_path, "PNG")
        media_resp = api.media_upload(filename=img_path)
        media_id = getattr(media_resp, "media_id", None)
        if not media_id:
            logging.error("❌ Media upload failed: no media_id returned.")
            return

        # Generate sentiment and caption
        sentiment = format_market_sentiment(
            period,
            equity_block=equity_block,
            macro_block=macro_block,
            crypto_block=crypto_block,
            movers=None
        )

        caption = get_briefing_caption(period, headline=headline, summary=summary)

        try:
            # Main briefing tweet with image
            resp = client.create_tweet(text=caption, media_ids=[media_id])
            logging.debug(f"Tweet creation response: {resp}")

            if resp is None or not hasattr(resp, "data") or resp.data is None:
                logging.error("Failed to create tweet: response or data is None")
                return

            tweet_id = resp.data.get("id")
            if tweet_id is None:
                logging.error("Tweet creation response missing tweet ID")
                return

        except (tweepy.errors.TweepyException, requests.exceptions.RequestException, ConnectionError) as e:
            error_str = str(e).lower()
            if ("timeout" in error_str or "connection" in error_str or "remote end closed" in error_str) and retry_count < MAX_RETRY_ATTEMPTS:
                delay = RETRY_DELAYS[retry_count]
                logging.warning(f"⚠️ PDF post attempt {retry_count+1} failed: {e}. Retrying in {delay}s.")
                time.sleep(delay)
                return timed_post_pdf_briefing(
                    filepath=filepath,
                    period=period,
                    headline=headline,
                    summary=summary,
                    equity_block=equity_block,
                    macro_block=macro_block,
                    crypto_block=crypto_block,
                    pdf_url=pdf_url,
                    retry_count=retry_count + 1,
                    category=category,
                    theme=theme
                )
            raise

        # Log main tweet with enhanced logging
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        log_tweet_to_csv(tweet_id, date_str, "briefing", category, theme or period, url)
        log_tweet(tweet_id, date_str, category, url, 0, 0, 0, 0, caption, theme or period)
        
        logging.info(f"✅ Posted {period} briefing main tweet: {url}")

        # Post reply with sentiment
        try:
            resp2 = client.create_tweet(text=sentiment, in_reply_to_tweet_id=tweet_id)
            reply_id = getattr(resp2.data, "id", None) if resp2 and resp2.data else None
            if reply_id:
                reply_url = f"https://x.com/{BOT_USER_ID}/status/{reply_id}"
                log_tweet_to_csv(reply_id, date_str, "briefing_reply", category, theme or period, reply_url)
                log_tweet(reply_id, date_str, category, reply_url, 0, 0, 0, 0, sentiment, theme or period)
                logging.info(f"↪️ Posted sentiment reply for {period}: {reply_url}")
            else:
                logging.error("Failed to post sentiment reply or missing reply ID")
        except Exception as e:
            logging.error(f"Failed to post sentiment reply: {e}")
            reply_id = None

        # Post third tweet with PDF link and call to action
        if pdf_url:
            third_tweet_text = (
                f"📄 Dive deeper: The full briefing PDF is available here 👉 {pdf_url}\n\n"
                "Includes detailed economic calendars, upcoming IPOs & earnings, "
                "plus the latest news driving market moves. Stay informed and ahead of the curve!\n\n"
                "This is NFA, not financial advice."
            )
            
            try:
                # Determine which tweet to reply to
                reply_to_id = reply_id if reply_id else tweet_id
                
                resp3 = client.create_tweet(text=third_tweet_text, in_reply_to_tweet_id=reply_to_id)
                third_id = getattr(resp3.data, "id", None) if resp3 and resp3.data else None
                if third_id:
                    third_url = f"https://x.com/{BOT_USER_ID}/status/{third_id}"
                    log_tweet_to_csv(third_id, date_str, "briefing_pdf_link", category, theme or period, third_url)
                    log_tweet(third_id, date_str, category, third_url, 0, 0, 0, 0, third_tweet_text, theme or period)
                    logging.info(f"📄 Posted PDF link tweet for {period}: {third_url}")
                else:
                    logging.error("Failed to post PDF link tweet or missing tweet ID")
            except Exception as e:
                logging.error(f"Failed to post PDF link tweet: {e}")

        return url

    except Exception as e:
        logging.error(f"❌ Error in timed_post_pdf_briefing: {e}")
        return None

    finally:
        # Cleanup
        if img_path and os.path.exists(img_path):
            try:
                os.unlink(img_path)
            except Exception as e:
                logging.warning(f"Failed to cleanup image file: {e}")
        if temp_dir and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except Exception as e:
                logging.warning(f"Failed to cleanup temp directory: {e}")


def convert_pdf_to_png(filepath: str, output_dir: str = None) -> str:
    """
    Convert first page of PDF to PNG for Twitter posting
    
    Args:
        filepath: Path to PDF file
        output_dir: Optional output directory (uses temp if None)
        
    Returns:
        str: Path to generated PNG file
    """
    try:
        images = convert_from_path(filepath, dpi=200, first_page=1, last_page=1)
        if not images:
            raise Exception("PDF conversion failed — no pages rendered")

        if output_dir is None:
            output_dir = tempfile.mkdtemp()
            
        png_path = os.path.join(output_dir, "briefing_page_1.png")
        images[0].save(png_path, "PNG")
        
        logging.info(f"Converted PDF to PNG: {png_path}")
        return png_path
        
    except Exception as e:
        logging.error(f"Error converting PDF to PNG: {e}")
        raise

# ─── Retry Schedulers ───────────────────────────────────────────────────
def schedule_retry_thread(remaining_parts: list[str], reply_to_id: str, category: str, theme: str = None):
    """Schedule retry for remaining thread parts"""
    logging.info(f"⏳ Scheduling retry for {len(remaining_parts)} parts in 15 minutes.")
    def retry_call():
        post_thread(remaining_parts, category=category, theme=theme, previous_id=reply_to_id, retry=True)
    threading.Timer(THREAD_RETRY_DELAY, retry_call).start()

def schedule_retry_single_tweet(part: str, reply_to_id: str, category: str, theme: str = None, retries: int = 1):
    """Schedule retry for a single failed tweet"""
    if retries > MAX_TWEET_RETRIES:
        logging.error('❌ Max retries reached for single tweet — giving up.')
        return

    logging.info(f"⏳ Scheduling retry {retries}/{MAX_TWEET_RETRIES} for single tweet in 10 minutes.")
    def retry_call():
        try:
            resp = timed_create_tweet(text=part, in_reply_to_tweet_id=reply_to_id, part_index=None)
            in_reply = resp.data['id']
            reply_url = f"https://x.com/{BOT_USER_ID}/status/{in_reply}"
            
            # Enhanced logging for retry
            log_tweet_to_csv(
                tweet_id=in_reply,
                timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                tweet_type='thread-reply',
                category=category,
                theme=theme or "",
                url=reply_url,
                likes=0,
                retweets=0,
                replies=0,
                impressions=0,
                engagement_score=0
            )
            
            log_tweet(in_reply, datetime.now(timezone.utc).strftime('%Y-%m-%d'), 
                     category, reply_url, 0, 0, 0, 0, part, theme)

            logging.info(f"✅ Retry success: Posted single tweet: {reply_url}")
        except Exception as e:
            error_str = str(e).lower()
            if 'timeout' in error_str or 'connection' in error_str:
                schedule_retry_single_tweet(part, reply_to_id, category, theme, retries=retries+1)
            else:
                logging.error(f"❌ Retry failed with non-retryable error: {e}")
    threading.Timer(SINGLE_TWEET_RETRY_DELAY, retry_call).start()