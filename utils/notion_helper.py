# utils/notion_helper.py - Fixed version
from notion_client import Client
import os
from datetime import datetime

notion = Client(auth=os.getenv("NOTION_API_KEY"))

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
        print(f"Error updating tweet URL: {e}")
        return False