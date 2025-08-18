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

# Azure OpenAI credentials
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_DEPLOYMENT_ID = os.getenv("AZURE_DEPLOYMENT_ID")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION")
AZURE_RESOURCE_NAME = os.getenv("AZURE_RESOURCE_NAME")

# Telegram Logging
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID   = os.getenv("TG_CHAT_ID")

# Finnhub API
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# Alpha Vantage API
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

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
    "reuters": "https://feeds.reuters.com/reuters/businessNews",

    # CNBC feeds (alternate URLs)
    "cnbc": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    
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
    "yahoo_finance": "https://finance.yahoo.com/news/rssindex",
    "marketwatch": "https://www.marketwatch.com/rss/topstories",
}

#Notion API
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_PDF_DATABASE_ID = os.getenv("NOTION_PDF_DATABASE_ID")

#Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_BRIEFINGS_CONTAINER_NAME")

# IB Gateway Settings
IB_GATEWAY_HOST = os.getenv("IB_GATEWAY_HOST", "10.0.0.6")
IB_GATEWAY_PORT = int(os.getenv("IB_GATEWAY_PORT", "4001"))
IB_MAX_CLIENTS = int(os.getenv("IB_MAX_CLIENTS", "5"))

# NEW: C# REST API Configuration  
# Both Python and C# API are on 10.0.0.5, use localhost for best performance
CSHARP_API_URL = os.getenv("CSHARP_API_URL", "")
CSHARP_API_TIMEOUT = int(os.getenv("CSHARP_API_TIMEOUT", "30"))

# Optional: API Authentication (if you add it later)
CSHARP_API_KEY = os.getenv("CSHARP_API_KEY", "")
CSHARP_API_USERNAME = os.getenv("CSHARP_API_USERNAME", "")
CSHARP_API_PASSWORD = os.getenv("CSHARP_API_PASSWORD", "")

# Export the new config values
__all__ = [
    'IB_GATEWAY_HOST', 'IB_GATEWAY_PORT', 'IB_MAX_CLIENTS',
    'CSHARP_API_URL', 'CSHARP_API_TIMEOUT',
    'CSHARP_API_KEY', 'CSHARP_API_USERNAME', 'CSHARP_API_PASSWORD'
]

# IG Index API Configuration
IG_USERNAME = os.getenv('IG_USERNAME')
IG_PASSWORD = os.getenv('IG_PASSWORD') 
IG_API_KEY = os.getenv('IG_API_KEY')
IG_ACC_TYPE = os.getenv('IG_ACC_TYPE', 'LIVE')  # DEMO or LIVE
IG_ACC_NUMBER = os.getenv('IG_ACC_NUMBER')  # Optional

# IG Index Configuration Validation
def validate_ig_config():
    """Validate IG Index configuration"""
    missing = []
    
    if not IG_USERNAME:
        missing.append('IG_USERNAME')
    if not IG_PASSWORD:
        missing.append('IG_PASSWORD')
    if not IG_API_KEY:
        missing.append('IG_API_KEY')
    
    if missing:
        print(f"⚠️  Missing IG Index configuration: {', '.join(missing)}")
        print("Add these to your .env file:")
        for var in missing:
            print(f"  {var}=your_value_here")
        return False
    
    print("✅ IG Index configuration validated")
    return True

# Market Data Source Priority
MARKET_DATA_SOURCES = {
    'primary': 'ig_index',
    'fallback': 'yfinance',
    'crypto': 'coingecko'
}

# Rate Limiting Configuration
RATE_LIMITS = {
    'ig_index': {
        'requests_per_minute': 35,  # Conservative limit (IG allows 40)
        'min_interval_seconds': 1.5
    },
    'yfinance': {
        'requests_per_minute': 60,
        'min_interval_seconds': 1.0
    }
}