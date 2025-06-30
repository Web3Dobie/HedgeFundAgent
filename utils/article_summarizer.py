import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

def summarize_url(url: str, char_limit: int = 500) -> str:
    """
    Fetches and extracts a summary from the given article URL.
    Prioritizes meta description or first meaningful paragraph.

    Args:
        url (str): Article URL.
        char_limit (int): Max length of summary to return.

    Returns:
        str: Extracted summary text.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ArticleSummaryBot/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=7)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Try <meta name="description"> or <meta property="og:description">
        meta = soup.find("meta", attrs={"name": "description"}) or \
               soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            return meta["content"][:char_limit].strip()

        # Fallback: first clean paragraph
        for p in soup.find_all("p"):
            text = p.get_text().strip()
            if len(text) > 50:
                return text[:char_limit]

        return ""

    except Exception as e:
        logger.warning(f"[SUMMARY ERROR] Failed to summarize {url}: {e}")
        return ""
