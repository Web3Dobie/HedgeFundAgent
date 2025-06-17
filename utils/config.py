import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Twitter API
TWITTER_CONSUMER_KEY    = os.getenv("X_API_KEY")
TWITTER_CONSUMER_SECRET = os.getenv("X_API_SECRET")
TWITTER_ACCESS_TOKEN    = os.getenv("X_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET   = os.getenv("X_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN    = os.getenv("X_BEARER_TOKEN")
BOT_USER_ID             = os.getenv("X_BOT_USER_ID")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Telegram Logging
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID   = os.getenv("TG_CHAT_ID")

# Local directories
BASE_DIR  = os.path.dirname(os.path.dirname(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
LOG_DIR   = os.path.join(BASE_DIR, "logs")
BACKUP_DIR = os.path.join(BASE_DIR, "backup")

# RSS feeds: Political, Macro, and Financial News
RSS_FEED_URLS = {
    # Reuters feeds (updated to new format)
    # "reuters-business": "https://www.reuters.com/business/rss",
    # "reuters-markets": "https://www.reuters.com/finance/markets",

    # CNBC feeds (alternate URLs)
    # "cnbc-latest": "https://feeds.feedspot.com/cnbc_latest.rss",  # example
    
    # Working feeds (unchanged)
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "ft": "https://www.ft.com/?format=rss",
    "bloomberg-markets": "https://feeds.bloomberg.com/markets/news.rss",
    "bloomberg-poli": "https://feeds.bloomberg.com/politics/news.rss",
    "bloomberg-tech": "https://feeds.bloomberg.com/technology/news.rss",
    "bloomberg-wealth": "https://feeds.bloomberg.com/wealth/news.rss",
    "bloomberg-eco": "https://feeds.bloomberg.com/economics/news.rss",
    
    # PRNewswire (corrected path)
    "prnnews": "https://www.prnewswire.com/rss/news-releases/news-releases-list.rss",
    
    # Alternative for ZeroHedge
    # "zerohedge": "https://rss.feedspot.com/zerohedge-markets.xml",

    # Additional Financial News Sources
    "seeking-alpha": "https://seekingalpha.com/feed.xml",
    "wsj-markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "investing-com": "https://www.investing.com/rss/news.rss",
    "benzinga-general": "https://www.benzinga.com/feed",
    "business-insider": "https://markets.businessinsider.com/rss/news",
    "tradingview-news": "https://www.tradingview.com/feed/",
}
