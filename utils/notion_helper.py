# utils/notion_helper.py - Enhanced with main tweet logging and category/theme support
from notion_client import Client
import os
from datetime import datetime
import logging

notion = Client(auth=os.getenv("NOTION_API_KEY"))
logger = logging.getLogger(__name__)

# Environment variables
HEDGEFUND_TWEET_DB_ID = os.getenv("HEDGEFUND_TWEET_DB_ID")
NOTION_TWEET_LOG_DB = os.getenv("NOTION_TWEET_LOG_DB")  # Main tweet database

def log_pdf_briefing_to_notion(pdf_path: str, period: str, pdf_url: str, tweet_url: str = None):
    """
    Log PDF briefing to Notion database
    
    Args:
        pdf_path: Local PDF file path (for extracting filename)
        period: Briefing period (morning, pre_market, etc.)
        pdf_url: Azure blob URL for the PDF
        tweet_url: Twitter URL (optional, can be None initially)
    """
    database_id = os.getenv("NOTION_PDF_DATABASE_ID")

    if not database_id:
        raise ValueError("NOTION_PDF_DATABASE_ID environment variable not set")

    # Extract filename from path for better title
    filename = os.path.basename(pdf_path) if pdf_path else f"{period}_briefing"
    title = f"{period.capitalize()} Market Briefing"

    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        },
        "Date": {
            "date": {"start": datetime.utcnow().isoformat()}
        },
        "Period": {
            "select": {"name": period}
        },
        "PDF Link": {  # This should be the Azure blob URL
            "url": pdf_url
        }
    }
    
    # Only add Tweet URL if provided
    if tweet_url:
        properties["Tweet URL"] = {
            "url": tweet_url
        }

    page = notion.pages.create(
        parent={"database_id": database_id},
        properties=properties
    )
    
    return page

def update_briefing_tweet_url(page_id: str, tweet_url: str):
    """
    Update an existing briefing page with the tweet URL
    """
    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "Tweet URL": {
                    "url": tweet_url
                }
            }
        )
        return True
    except Exception as e:
        logger.error(f"Error updating tweet URL: {e}")
        return False

def log_main_tweet_to_notion(
    tweet_id: str, 
    tweet_text: str, 
    tweet_url: str, 
    tweet_category: str = "original",
    tweet_theme: str = None,
    likes: int = 0,
    retweets: int = 0, 
    replies: int = 0
) -> bool:
    """
    Log a tweet to the main tweet log database with category and theme support
    
    Args:
        tweet_id: Twitter ID of the posted tweet
        tweet_text: Full text content of the tweet
        tweet_url: URL to the tweet
        tweet_category: Category of tweet ("original", "briefing", "thread", etc.)
        tweet_theme: Theme/topic extracted from the tweet content
        likes, retweets, replies: Engagement metrics (initially 0, can be updated later)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not NOTION_TWEET_LOG_DB:
            logger.error("NOTION_TWEET_LOG_DB environment variable not set")
            return False
            
        # Calculate basic engagement score
        engagement_score = likes + (retweets * 2) + (replies * 1.5)
        
        properties = {
            "Tweet ID": {
                "title": [{"text": {"content": str(tweet_id)}}]
            },
            "Date": {
                "date": {"start": datetime.utcnow().isoformat()}
            },
            "Category": {  # Updated from "Type" to "Category"
                "select": {"name": tweet_category}
            },
            "URL": {
                "url": tweet_url
            },
            "Text": {
                "rich_text": [{"text": {"content": tweet_text[:2000]}}]  # Notion limit
            },
            "Likes": {
                "number": likes
            },
            "Retweets": {
                "number": retweets
            },
            "Replies": {
                "number": replies
            },
            "Engagement Score": {
                "number": engagement_score
            }
        }
        
        # Add theme if provided
        if tweet_theme:
            properties["Theme"] = {
                "rich_text": [{"text": {"content": str(tweet_theme)[:100]}}]  # Limit to 100 chars
            }
        
        response = notion.pages.create(
            parent={"database_id": NOTION_TWEET_LOG_DB},
            properties=properties
        )
        
        logger.info(f"[OK] Logged main tweet {tweet_id} with category '{tweet_category}', theme '{tweet_theme}' to Notion DB {NOTION_TWEET_LOG_DB}")
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to log main tweet {tweet_id} to Notion: {e}")
        logger.error(f"[ERROR] Main tweet data: id={tweet_id}, category={tweet_category}, theme={tweet_theme}, text_length={len(tweet_text) if tweet_text else 0}")
        return False

def log_hedgefund_tweet_to_notion(
    tweet_id: str, 
    tweet_text: str, 
    tweet_url: str, 
    tweet_type: str = "hedge_fund_commentary",
    likes: int = 0,
    retweets: int = 0, 
    replies: int = 0
) -> bool:
    """
    Log a hedge fund tweet to the dedicated HedgeFund tweet database
    
    Args:
        tweet_id: Twitter ID of the posted tweet
        tweet_text: Full text content of the tweet
        tweet_url: URL to the tweet
        tweet_type: Type of tweet ("hedge_fund_commentary", "deep_dive_thread")
        likes, retweets, replies: Engagement metrics (initially 0, can be updated later)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not HEDGEFUND_TWEET_DB_ID:
            logger.error("HEDGEFUND_TWEET_DB_ID environment variable not set")
            return False
            
        # Calculate basic engagement score (can be enhanced later)
        engagement_score = likes + (retweets * 2) + (replies * 1.5)
        
        properties = {
            "Tweet ID": {
                "title": [{"text": {"content": str(tweet_id)}}]
            },
            "Date": {
                "date": {"start": datetime.utcnow().isoformat()}
            },
            "Category": {  # Updated from "Type" to "Category"
                "select": {"name": tweet_type}
            },
            "URL": {
                "url": tweet_url
            },
            "Text": {
                "rich_text": [{"text": {"content": tweet_text[:2000]}}]  # Notion limit
            },
            "Likes": {
                "number": likes
            },
            "Retweets": {
                "number": retweets
            },
            "Replies": {
                "number": replies
            },
            "Engagement Score": {
                "number": engagement_score
            }
        }
        
        response = notion.pages.create(
            parent={"database_id": HEDGEFUND_TWEET_DB_ID},
            properties=properties
        )
        
        logger.info(f"[OK] Logged HedgeFund tweet {tweet_id} to Notion DB {HEDGEFUND_TWEET_DB_ID}")
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to log HedgeFund tweet {tweet_id} to Notion: {e}")
        return False

def update_hedgefund_tweet_metrics(tweet_id: str, likes: int, retweets: int, replies: int) -> bool:
    """
    Update engagement metrics for an existing tweet in the HedgeFund Notion database
    """
    try:
        if not HEDGEFUND_TWEET_DB_ID:
            logger.error("HEDGEFUND_TWEET_DB_ID environment variable not set")
            return False

        # Search for the tweet by ID
        response = notion.databases.query(
            database_id=HEDGEFUND_TWEET_DB_ID,
            filter={
                "property": "Tweet ID",
                "title": {
                    "equals": str(tweet_id)
                }
            }
        )
        
        if not response.results:
            logger.warning(f"Tweet {tweet_id} not found in database")
            return False
            
        page_id = response.results[0]["id"]
        engagement_score = likes + (retweets * 2) + (replies * 1.5)
        
        notion.pages.update(
            page_id=page_id,
            properties={
                "Likes": {"number": likes},
                "Retweets": {"number": retweets},
                "Replies": {"number": replies},
                "Engagement Score": {"number": engagement_score}
            }
        )
        
        logger.info(f"[OK] Updated metrics for tweet {tweet_id}")
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to update tweet {tweet_id} metrics: {e}")
        return False