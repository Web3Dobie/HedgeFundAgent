from notion_client import Client
import os
from datetime import datetime

notion = Client(auth=os.getenv("NOTION_API_KEY"))

def log_pdf_briefing_to_notion(pdf_url: str, period: str, tweet_url: str):
    database_id = os.getenv("NOTION_PDF_DATABASE_ID")

    page = notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "Name": {
                "title": [{"text": {"content": f"{period.capitalize()} Market Briefing"}}]
            },
            "Date": {
                "date": {"start": datetime.utcnow().isoformat()}
            },
            "Period": {
                "select": {"name": period}
            },
            "Tweet URL": {
                "url": tweet_url
            },
            "PDF Link": {   # rename property to PDF Link for clarity
                "url": pdf_url
            },
        }
    )
    return page
