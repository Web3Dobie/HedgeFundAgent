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
import traceback

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

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

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

# utils/x_post.py - Enhanced timed_post_pdf_briefing function with comprehensive logging

def timed_post_pdf_briefing(
    filepath: str,
    period: str = "morning",
    headline=None,
    summary=None,
    equity_block=None,
    macro_block=None,
    crypto_block=None,
    pdf_url=None,
    retry_count=0
):
    """
    Posts a multi-part briefing thread on X (Twitter) with comprehensive logging
    and PyMuPDF fallback for PDF conversion
    """
    logging.info(f"🐦 [X POST ENTRY] Function called with parameters:")
    logging.info(f"🐦 [X POST ENTRY] - filepath: {filepath}")
    logging.info(f"🐦 [X POST ENTRY] - period: {period}")
    logging.info(f"🐦 [X POST ENTRY] - headline: {headline}")
    logging.info(f"🐦 [X POST ENTRY] - summary: {summary}")
    logging.info(f"🐦 [X POST ENTRY] - pdf_url: {pdf_url}")
    logging.info(f"🐦 [X POST ENTRY] - retry_count: {retry_count}")
    
    img_path = None
    temp_dir = None

    # Check daily limit first
    logging.info(f"🐦 [LIMIT CHECK] Checking daily tweet limit...")
    if has_reached_daily_limit():
        logging.warning(f"🚫 [LIMIT CHECK] Daily tweet limit reached — skipping {period} briefing.")
        return "DAILY_LIMIT_REACHED"
    
    logging.info(f"✅ [LIMIT CHECK] Daily limit OK, proceeding with posting")

    try:
        # Step 1: Convert PDF to image with fallback methods
        logging.info(f"🖼️ [PDF CONVERT] Converting PDF first page to image...")
        logging.info(f"🖼️ [PDF CONVERT] PDF path: {filepath}")
        logging.info(f"🖼️ [PDF CONVERT] PDF exists: {os.path.exists(filepath)}")
        logging.info(f"🖼️ [PDF CONVERT] Working directory: {os.getcwd()}")
        
        if not os.path.exists(filepath):
            logging.error(f"❌ [PDF CONVERT] PDF file not found: {filepath}")
            return "PDF_NOT_FOUND"

        # Make filepath absolute
        abs_filepath = os.path.abspath(filepath)
        logging.info(f"🖼️ [PDF CONVERT] Absolute path: {abs_filepath}")
        
        images = None
        conversion_method = "unknown"

        # Try pdf2image first (requires poppler)
        try:
            logging.info(f"🖼️ [PDF CONVERT] Trying pdf2image method...")
            images = convert_from_path(abs_filepath, dpi=200, first_page=1, last_page=1)
            conversion_method = "pdf2image"
            logging.info(f"✅ [PDF CONVERT] pdf2image successful")
        except Exception as e:
            logging.warning(f"⚠️ [PDF CONVERT] pdf2image failed: {e}")
            
            # Try PyMuPDF fallback
            if PYMUPDF_AVAILABLE:
                logging.info(f"🖼️ [PDF CONVERT] Trying PyMuPDF fallback...")
                images = convert_pdf_to_image_fallback(abs_filepath, dpi=200)
                if images:
                    conversion_method = "pymupdf"
                    logging.info(f"✅ [PDF CONVERT] PyMuPDF fallback successful")
                else:
                    logging.error(f"❌ [PDF CONVERT] PyMuPDF returned no images")
            else:
                logging.error(f"❌ [PDF CONVERT] PyMuPDF not available for fallback")

        if not images:
            logging.error(f"❌ [PDF CONVERT] All PDF conversion methods failed")
            return "PDF_CONVERSION_FAILED"
        
        logging.info(f"✅ [PDF CONVERT] Successfully converted PDF using {conversion_method}, got {len(images)} image(s)")

        # Step 2: Save image and upload to Twitter
        logging.info(f"💾 [IMAGE SAVE] Creating temporary image file...")
        temp_dir = tempfile.mkdtemp()
        img_path = os.path.join(temp_dir, "page_1.png")
        images[0].save(img_path, "PNG")
        
        img_size = os.path.getsize(img_path)
        logging.info(f"✅ [IMAGE SAVE] Image saved: {img_path}, size: {img_size} bytes")
        
        # Step 3: Upload media to Twitter
        logging.info(f"📤 [MEDIA UPLOAD] Uploading image to Twitter...")
        
        try:
            media_resp = api.media_upload(filename=img_path)
            media_id = getattr(media_resp, "media_id", None)
            
            if not media_id:
                logging.error(f"❌ [MEDIA UPLOAD] Media upload failed: no media_id returned.")
                return "MEDIA_UPLOAD_FAILED"
            
            logging.info(f"✅ [MEDIA UPLOAD] Media uploaded successfully, ID: {media_id}")
            
        except Exception as e:
            logging.error(f"❌ [MEDIA UPLOAD] Exception during media upload: {e}")
            return "MEDIA_UPLOAD_EXCEPTION"

        # Step 4: Generate sentiment text
        logging.info(f"📝 [SENTIMENT] Generating market sentiment text...")
        
        try:
            sentiment = format_market_sentiment(
                period,
                equity_block=equity_block,
                macro_block=macro_block,
                crypto_block=crypto_block,
                movers=None
            )
            logging.info(f"✅ [SENTIMENT] Sentiment generated, length: {len(sentiment)} chars")
            logging.info(f"📝 [SENTIMENT] Content: {sentiment[:100]}...")  # First 100 chars
            
        except Exception as e:
            logging.error(f"❌ [SENTIMENT] Exception generating sentiment: {e}")
            sentiment = f"Market update for {period} - check the PDF for details! 📊"
            logging.info(f"📝 [SENTIMENT] Using fallback sentiment")

        # Step 5: Generate caption
        logging.info(f"📝 [CAPTION] Generating briefing caption...")
        
        try:
            caption = get_briefing_caption(period, headline=headline, summary=summary)
            logging.info(f"✅ [CAPTION] Caption generated, length: {len(caption)} chars")
            logging.info(f"📝 [CAPTION] Content: {caption[:100]}...")  # First 100 chars
            
        except Exception as e:
            logging.error(f"❌ [CAPTION] Exception generating caption: {e}")
            caption = f"📊 {period.title()} Market Briefing is ready!"
            logging.info(f"📝 [CAPTION] Using fallback caption")

        # Step 6: POST MAIN TWEET
        logging.info(f"🐦 [MAIN TWEET] ==================== POSTING MAIN TWEET ====================")
        logging.info(f"🐦 [MAIN TWEET] Caption length: {len(caption)}")
        logging.info(f"🐦 [MAIN TWEET] Media ID: {media_id}")
        
        try:
            logging.info(f"🐦 [MAIN TWEET] Calling client.create_tweet...")
            
            resp = client.create_tweet(text=caption, media_ids=[media_id])
            
            logging.info(f"🐦 [MAIN TWEET] Tweet creation response received")
            logging.debug(f"🐦 [MAIN TWEET] Raw response: {resp}")

            if resp is None:
                logging.error(f"❌ [MAIN TWEET] Failed to create tweet: response is None")
                return "TWEET_RESPONSE_NONE"
                
            if not hasattr(resp, "data") or resp.data is None:
                logging.error(f"❌ [MAIN TWEET] Failed to create tweet: response.data is None")
                return "TWEET_DATA_NONE"

            tweet_id = resp.data.get("id")
            if tweet_id is None:
                logging.error(f"❌ [MAIN TWEET] Tweet creation response missing tweet ID")
                return "TWEET_ID_MISSING"
            
            logging.info(f"✅ [MAIN TWEET] Main tweet posted successfully, ID: {tweet_id}")

        except (tweepy.errors.TweepyException, requests.exceptions.RequestException, ConnectionError) as e:
            error_str = str(e).lower()
            logging.error(f"❌ [MAIN TWEET] Network/API error: {e}")
            
            # Define retry delays and max attempts for this function
            RETRY_DELAYS = [30, 60, 120]  # 30s, 1m, 2m
            MAX_RETRY_ATTEMPTS = 3
            
            if ("timeout" in error_str or "connection" in error_str or "remote end closed" in error_str) and retry_count < MAX_RETRY_ATTEMPTS:
                delay = RETRY_DELAYS[retry_count] if retry_count < len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                logging.warning(f"⚠️ [MAIN TWEET] Retry attempt {retry_count+1} in {delay}s due to: {e}")
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
                    retry_count=retry_count + 1
                )
            
            logging.error(f"❌ [MAIN TWEET] Max retries reached or non-recoverable error")
            return "MAIN_TWEET_FAILED"

        # Step 7: Log main tweet
        url = f"https://x.com/{BOT_USER_ID}/status/{tweet_id}"
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        logging.info(f"📊 [TWEET LOG] Logging main tweet to CSV...")
        try:
            log_tweet_to_csv(tweet_id, date_str, "briefing", "briefing", period, url)
            logging.info(f"✅ [TWEET LOG] Main tweet logged successfully")
        except Exception as e:
            logging.error(f"❌ [TWEET LOG] Failed to log main tweet: {e}")
        
        logging.info(f"✅ [MAIN TWEET] Posted {period} briefing main tweet: {url}")

        # Step 8: POST SENTIMENT REPLY
        logging.info(f"💬 [REPLY TWEET] ==================== POSTING SENTIMENT REPLY ====================")
        
        try:
            logging.info(f"💬 [REPLY TWEET] Posting sentiment reply to tweet {tweet_id}")
            resp2 = client.create_tweet(text=sentiment, in_reply_to_tweet_id=tweet_id)
            
            reply_id = getattr(resp2.data, "id", None) if resp2 and resp2.data else None
            
            if reply_id:
                reply_url = f"https://x.com/{BOT_USER_ID}/status/{reply_id}"
                logging.info(f"✅ [REPLY TWEET] Sentiment reply posted: {reply_url}")
                
                try:
                    log_tweet_to_csv(reply_id, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                                   "briefing_reply", "briefing", period, reply_url)
                    logging.info(f"✅ [REPLY LOG] Sentiment reply logged successfully")
                except Exception as e:
                    logging.error(f"❌ [REPLY LOG] Failed to log sentiment reply: {e}")
            else:
                logging.error(f"❌ [REPLY TWEET] Failed to post sentiment reply or missing reply ID")
                
        except Exception as e:
            logging.error(f"❌ [REPLY TWEET] Exception posting sentiment reply: {e}")
            reply_id = None

        # Step 9: POST PDF LINK TWEET
        if pdf_url:
            logging.info(f"🔗 [PDF TWEET] ==================== POSTING PDF LINK TWEET ====================")
            
            third_tweet_text = (
                f"📄 Dive deeper: The full briefing PDF is available here 👉 {pdf_url}\n\n"
                "Includes detailed economic calendars, upcoming IPOs & earnings, "
                "plus the latest news driving market moves. Stay informed and ahead of the curve!\n\n"
                "This is NFA, not financial advice."
            )
            
            try:
                logging.info(f"🔗 [PDF TWEET] Posting PDF link tweet, reply to {reply_id or tweet_id}")
                resp3 = client.create_tweet(text=third_tweet_text, in_reply_to_tweet_id=reply_id or tweet_id)
                
                third_id = getattr(resp3.data, "id", None) if resp3 and resp3.data else None
                
                if third_id:
                    third_url = f"https://x.com/{BOT_USER_ID}/status/{third_id}"
                    logging.info(f"✅ [PDF TWEET] PDF link tweet posted: {third_url}")
                    
                    try:
                        log_tweet_to_csv(third_id, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                                       "briefing_pdf_link", "briefing", period, third_url)
                        logging.info(f"✅ [PDF LOG] PDF link tweet logged successfully")
                    except Exception as e:
                        logging.error(f"❌ [PDF LOG] Failed to log PDF link tweet: {e}")
                else:
                    logging.error(f"❌ [PDF TWEET] Failed to post PDF link tweet or missing tweet ID")
                    
            except Exception as e:
                logging.error(f"❌ [PDF TWEET] Exception posting PDF link tweet: {e}")
        else:
            logging.warning(f"⚠️ [PDF TWEET] No PDF URL provided, skipping PDF link tweet")

        logging.info(f"🎯 [X POST COMPLETE] All Twitter posting completed successfully!")
        return "SUCCESS"

    except Exception as e:
        logging.error(f"❌ [X POST ERROR] Unexpected error in timed_post_pdf_briefing: {e}")
        logging.error(f"❌ [X POST ERROR] Traceback: {traceback.format_exc()}")
        return "UNEXPECTED_ERROR"
        
    finally:
        # Cleanup temporary files
        if img_path and os.path.exists(img_path):
            try:
                os.remove(img_path)
                logging.info(f"🧹 [CLEANUP] Removed temporary image: {img_path}")
            except Exception as e:
                logging.error(f"❌ [CLEANUP] Failed to remove temp image: {e}")
                
        if temp_dir and os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
                logging.info(f"🧹 [CLEANUP] Removed temporary directory: {temp_dir}")
            except Exception as e:
                logging.error(f"❌ [CLEANUP] Failed to remove temp directory: {e}")

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

# utils/x_post.py - Add this test function to verify X posting configuration

def test_x_post_config():
    """
    Test function to verify X posting configuration and API connectivity
    Call this before the actual briefing to verify everything is working
    """
    logging.info(f"🧪 [X TEST] ==================== TESTING X POST CONFIG ====================")
    
    # Test 1: Check if API clients are initialized
    logging.info(f"🧪 [X TEST] Checking API client initialization...")
    
    try:
        logging.info(f"🧪 [X TEST] client object: {client}")
        logging.info(f"🧪 [X TEST] api object: {api}")
        logging.info(f"🧪 [X TEST] BOT_USER_ID: {BOT_USER_ID}")
    except NameError as e:
        logging.error(f"❌ [X TEST] API client not initialized: {e}")
        return False
    
    # Test 2: Check daily limit function
    logging.info(f"🧪 [X TEST] Checking daily limit function...")
    try:
        limit_status = has_reached_daily_limit()
        logging.info(f"✅ [X TEST] Daily limit check: {limit_status}")
    except Exception as e:
        logging.error(f"❌ [X TEST] Daily limit check failed: {e}")
        return False
    
    # Test 3: Check Twitter API connectivity (simple API call)
    logging.info(f"🧪 [X TEST] Testing Twitter API connectivity...")
    try:
        # Try to get user info (simple API call that doesn't post anything)
        user_info = client.get_me()
        if user_info and user_info.data:
            logging.info(f"✅ [X TEST] API connectivity OK - User: {user_info.data.username}")
        else:
            logging.error(f"❌ [X TEST] API connectivity failed - No user data returned")
            return False
    except Exception as e:
        logging.error(f"❌ [X TEST] API connectivity test failed: {e}")
        return False
    
    # Test 4: Check text utility functions
    logging.info(f"🧪 [X TEST] Testing text utility functions...")
    try:
        test_sentiment = format_market_sentiment("morning", 
                                                equity_block={"SPY": "100.00 (+1.5%)"}, 
                                                macro_block={"USD/EUR": "1.08 (-0.2%)"}, 
                                                crypto_block={"BTC": "50000 (+2.1%)"})
        test_caption = get_briefing_caption("morning", headline="Test", summary="Test summary")
        
        logging.info(f"✅ [X TEST] Text utilities OK - Sentiment: {len(test_sentiment)} chars, Caption: {len(test_caption)} chars")
    except Exception as e:
        logging.error(f"❌ [X TEST] Text utility functions failed: {e}")
        return False
    
    # Test 5: Check PDF conversion capability (using a dummy file path)
    logging.info(f"🧪 [X TEST] Testing PDF conversion capability...")
    try:
        # Just check if the import works and function exists
        from pdf2image import convert_from_path
        logging.info(f"✅ [X TEST] PDF conversion library imported successfully")
    except ImportError as e:
        logging.error(f"❌ [X TEST] PDF conversion library not available: {e}")
        return False
    
    logging.info(f"🎯 [X TEST] ==================== ALL X POST TESTS PASSED ====================")
    return True

def verify_x_posting_before_briefing(period: str):
    """
    Run this before each briefing to ensure X posting will work
    """
    logging.info(f"🔍 [X VERIFY] Verifying X posting setup before {period} briefing...")
    
    config_ok = test_x_post_config()
    
    if not config_ok:
        logging.error(f"❌ [X VERIFY] X posting configuration check failed!")
        return False
    
    logging.info(f"✅ [X VERIFY] X posting verification passed for {period} briefing")
    return True

def convert_pdf_to_image_fallback(pdf_path, dpi=200):
    """
    Convert PDF to image using PyMuPDF as fallback
    Returns list of PIL Images to match pdf2image interface
    """
    from PIL import Image
    import io
    
    try:
        logging.info(f"🖼️ [PDF CONVERT FB] Using PyMuPDF fallback for {pdf_path}")
        
        # Open the PDF
        doc = fitz.open(pdf_path)
        
        if len(doc) == 0:
            logging.error(f"❌ [PDF CONVERT FB] PDF has no pages")
            doc.close()
            return None
        
        # Get the first page
        page = doc[0]
        
        # Create a transformation matrix for the desired DPI
        mat = fitz.Matrix(dpi/72, dpi/72)  # 72 is the default DPI
        
        # Render page to an image
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("ppm")
        img = Image.open(io.BytesIO(img_data))
        
        doc.close()
        
        logging.info(f"✅ [PDF CONVERT FB] PyMuPDF conversion successful: {img.size}")
        return [img]  # Return as list to match pdf2image interface
        
    except Exception as e:
        logging.error(f"❌ [PDF CONVERT FB] PyMuPDF conversion failed: {e}")
        return None
