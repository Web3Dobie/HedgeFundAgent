from notion_client import Client
import os
from datetime import datetime

notion = Client(auth=os.getenv("NOTION_API_KEY"))

def log_pdf_briefing_to_notion(pdf_path: str, period: str, pdf_url: str, market_sentiment: str = None, tweet_url: str = None):
    """
    Log PDF briefing to Notion with optional market sentiment and tweet URL
    
    Args:
        pdf_path (str): Local path to the PDF file
        period (str): Briefing period (morning, pre_market, etc.)
        pdf_url (str): Azure Blob URL to the PDF
        market_sentiment (str, optional): GPT-generated market sentiment comment
        tweet_url (str, optional): URL to the tweet about this briefing
    """
    database_id = os.getenv("NOTION_PDF_DATABASE_ID")

    # Create the base properties
    properties = {
        "Name": {
            "title": [{"text": {"content": f"{period.capitalize()} Market Briefing"}}]
        },
        "Date": {
            "date": {"start": datetime.utcnow().isoformat()}
        },
        "Period": {
            "select": {"name": period}
        },
        "PDF Link": {
            "url": pdf_url
        }
    }
    
    # Add market sentiment if provided
    if market_sentiment:
        properties["Market Sentiment"] = {
            "rich_text": [{"text": {"content": market_sentiment}}]
        }
    
    # Add tweet URL if provided
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
    Update an existing briefing with a tweet URL
    
    Args:
        page_id (str): Notion page ID
        tweet_url (str): URL to the tweet
    """
    notion.pages.update(
        page_id=page_id,
        properties={
            "Tweet URL": {
                "url": tweet_url
            }
        }
    )
    
    return True