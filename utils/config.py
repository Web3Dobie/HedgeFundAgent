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
    "reuters-politics": "http://feeds.reuters.com/Reuters/PoliticsNews",
    "reuters-business": "http://feeds.reuters.com/reuters/businessNews",
    "reuters-markets":  "http://feeds.reuters.com/reuters/marketsNews",
    "cnbc-top":         "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "marketwatch":      "https://feeds.marketwatch.com/marketwatch/topstories/",
    "ft":               "https://www.ft.com/?format=rss",
    "bloomberg-markets":"https://feeds.bloomberg.com/markets/news.rss",
    "bloomberg-poli":   "https://feeds.bloomberg.com/politics/news.rss",
    "bloomberg-tech":   "https://feeds.bloomberg.com/technology/news.rss",
    "bloomberg-wealth": "https://feeds.bloomberg.com/wealth/news.rss",
    "bloomberg-eco":    "https://feeds.bloomberg.com/economics/news.rss",
    "prnnews":          "https://www.prnewswire.com/rss/",
    "zerohedge-gen":    "https://rss.feedspot.com/zerohedge_rss_feeds.xml",
    "zerohedge-econ":   "https://rss.feedspot.com/zerohedge-economics.xml",
    "zerohedge-markets":"https://rss.feedspot.com/zerohedge-markets.xml",
    "zerohedge-geopol": "https://rss.feedspot.com/zerohedge-geopolitical.xml"
}
