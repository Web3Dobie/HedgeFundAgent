import os
import csv
import finnhub
import logging
import inspect
import pandas as pd

from datetime import datetime, timedelta
from utils.text_utils import (
    TICKER_INFO, 
    is_weekend, 
    get_headlines_for_tickers, 
    flatten_and_deduplicate_headlines, 
    is_relevant_headline
)
from utils.yield_utils import (
    treasury_futures_to_yield_change,
    convert_us_treasury_yields
)
from utils.config import DATA_DIR
from utils.fetch_stock_data import (
    fetch_prior_close_yield,
    get_top_movers_from_constituents,
    fetch_stock_news
)
# Import your actual market data client (IG API + yfinance)
from utils.market_data import get_market_data_client
from utils.pdf_renderer import render_pdf
from data.ticker_blocks import (
    ASIA_EQUITY, 
    EUROPE_EQUITY, 
    US_EQUITY, 
    FX_PAIRS, 
    COMMODITIES, 
    RATES,
    CRYPTO,
    YIELD_SYMBOLS 
)
from utils.fetch_token_data import get_top_tokens_data
from utils.gpt import generate_gpt_text
from utils.x_post import timed_post_pdf_briefing

# ═══════════════════════════════════════════════════════════════
# CALENDAR IMPORTS: Keep IPO/Earnings (Finnhub), Disable Economic Cal
# ═══════════════════════════════════════════════════════════════
from utils.fetch_calendars import (
    # scrape_investing_econ_calendar,  # DISABLED - API not working
    get_ipo_calendar,                   # KEEP - Finnhub working
    get_earnings_calendar,              # KEEP - Finnhub working
)

from utils.azure_blob_storage_handler import upload_pdf_to_blob
from utils.notion_helper import log_pdf_briefing_to_notion

BRIEFING_DIR = os.path.join(DATA_DIR, "briefings")
os.makedirs(BRIEFING_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Finnhub client setup
api_key = os.getenv("FINNHUB_API_KEY")
if api_key:
    finnhub_client = finnhub.Client(api_key=api_key)
else:
    finnhub_client = None
    logger.warning("⚠️ Finnhub API key not configured")

# content/briefings.py - Enhanced run_briefing function with comprehensive logging

# content/briefings.py - Enhanced run_briefing function with comprehensive logging

def run_briefing(period: str, test_mode: bool = False):
    """
    Main briefing function with comprehensive logging for X posting troubleshooting
    """
    logging.info(f"🚀 [BRIEFING START] Generating {period} market briefing PDF")

    try:
        # Step 1: Generate the PDF briefing
        logging.info(f"📄 [PDF GEN] Starting PDF generation for {period}")
        pdf_path = generate_briefing_pdf(period)
        logging.info(f"✅ [PDF GEN] PDF generated successfully: {pdf_path}")
        
        if test_mode:
            logging.info(f"🧪 [TEST MODE] Skipping upload/posting - PDF created at {pdf_path}")
            print(f"✅ Test mode: PDF created at {pdf_path}")
            return pdf_path
        
        # Step 2: Upload to Azure Blob Storage
        logging.info(f"☁️ [BLOB UPLOAD] Starting Azure blob upload")
        blob_name = os.path.basename(pdf_path)
        logging.info(f"☁️ [BLOB UPLOAD] Blob name: {blob_name}")
        
        pdf_url = upload_pdf_to_blob(pdf_path, blob_name)
        logging.info(f"✅ [BLOB UPLOAD] Uploaded PDF to Azure Blob Storage: {pdf_url}")

        # Step 3: Log PDF metadata + URL to Notion
        logging.info(f"📝 [NOTION] Starting Notion logging")
        notion_page = log_pdf_briefing_to_notion(pdf_path, period, pdf_url)
        notion_id = notion_page.get('id') if notion_page else 'UNKNOWN'
        logging.info(f"✅ [NOTION] Logged PDF briefing to Notion: {notion_id}")

        # Step 4: Fetch market data blocks for sentiment tweet
        logging.info(f"📊 [MARKET DATA] Fetching market data blocks for {period}")
        try:
            equity_block, macro_block, crypto_block = get_market_blocks(period)
            logging.info(f"✅ [MARKET DATA] Fetched blocks - Equity: {len(equity_block)} items, "
                        f"Macro: {len(macro_block)} items, Crypto: {len(crypto_block)} items")
        except Exception as e:
            logging.error(f"❌ [MARKET DATA] Failed to fetch market blocks: {e}")
            # Set empty blocks as fallback
            equity_block, macro_block, crypto_block = {}, {}, {}

        # Step 5: VERIFY X POSTING SETUP
        logging.info(f"🔍 [X VERIFY] Verifying X posting configuration...")
        
        # Import the verification function
        from utils.x_post import verify_x_posting_before_briefing
        
        x_verify_ok = verify_x_posting_before_briefing(period)
        if not x_verify_ok:
            logging.error(f"❌ [X VERIFY] X posting verification failed - skipping X posting")
            logging.info(f"🎯 [BRIEFING COMPLETE] Briefing completed WITHOUT X posting due to config issues")
            return pdf_path

        # Step 6: POST TO X (TWITTER) - This is where the issue likely occurs
        logging.info(f"🐦 [X POST] ==================== STARTING X POSTING ====================")
        logging.info(f"🐦 [X POST] Period: {period}")
        logging.info(f"🐦 [X POST] PDF Path: {pdf_path}")
        logging.info(f"🐦 [X POST] PDF URL: {pdf_url}")
        logging.info(f"🐦 [X POST] Equity block size: {len(equity_block)}")
        logging.info(f"🐦 [X POST] Macro block size: {len(macro_block)}")
        logging.info(f"🐦 [X POST] Crypto block size: {len(crypto_block)}")
        
        # Check if PDF file exists before posting
        if not os.path.exists(pdf_path):
            logging.error(f"❌ [X POST] PDF file does not exist: {pdf_path}")
            return pdf_path
        
        logging.info(f"✅ [X POST] PDF file exists, size: {os.path.getsize(pdf_path)} bytes")
        
        try:
            # Call the X posting function with detailed logging
            logging.info(f"🐦 [X POST] Calling timed_post_pdf_briefing...")
            
            result = timed_post_pdf_briefing(
                filepath=pdf_path,
                period=period,
                headline=None,  # Let function generate
                summary=None,   # Let function generate
                equity_block=equity_block,
                macro_block=macro_block,
                crypto_block=crypto_block,
                pdf_url=pdf_url
            )
            
            logging.info(f"✅ [X POST] timed_post_pdf_briefing completed. Result: {result}")
            
            # Check the result and log accordingly
            if result == "SUCCESS":
                logging.info(f"🎉 [X POST] X posting completed successfully!")
            else:
                logging.warning(f"⚠️ [X POST] X posting returned: {result}")
            
            logging.info(f"🐦 [X POST] ==================== X POSTING COMPLETE ====================")
            
        except Exception as e:
            logging.error(f"❌ [X POST] Exception in timed_post_pdf_briefing: {e}")
            logging.error(f"❌ [X POST] Traceback: {traceback.format_exc()}")
            logging.info(f"🐦 [X POST] ==================== X POSTING FAILED ====================")
            # Don't re-raise - let briefing complete even if X posting fails
        
        logging.info(f"🎯 [BRIEFING COMPLETE] All steps completed for {period} briefing")
        return pdf_path
        
    except Exception as e:
        logging.error(f"❌ [BRIEFING ERROR] Critical error in run_briefing: {e}")
        logging.error(f"❌ [BRIEFING ERROR] Traceback: {traceback.format_exc()}")
        raise

def fetch_crypto_block() -> dict:
    """Fetch crypto prices using your market data client"""
    try:
        client = get_market_data_client()
        
        # Get crypto data using the market data client's crypto method
        crypto_data = client.get_crypto_prices()
        
        # Format for briefing display
        formatted_crypto = {}
        for name, data in crypto_data.items():
            if isinstance(data, dict) and 'price' in data and 'change_percent' in data:
                price = data['price']
                change = data['change_percent']
                formatted_crypto[name] = f"${price:,.2f} ({change:+.2f}%)"
            else:
                formatted_crypto[name] = "N/A"
        
        return formatted_crypto
        
    except Exception as e:
        logger.error(f"❌ Crypto block fetch failed: {e}")
        return {
            "Bitcoin": "N/A",
            "Ethereum": "N/A", 
            "Solana": "N/A",
            "Cardano": "N/A"
        }

def fetch_price_block(tickers: dict) -> dict:
    """
    Fetch prices using IG API + yfinance fallback (your market data client)
    
    Args:
        tickers: Dictionary of {label: symbol}
        
    Returns:
        Dictionary of {label: "price (change%)"}
    """
    if not tickers:
        return {}
    
    try:
        client = get_market_data_client()
        
        # Use the multiple prices method which handles IG API + yfinance fallback
        formatted_prices = client.get_multiple_prices(tickers)
        
        # The client returns already formatted strings, so return directly
        return formatted_prices
        
    except Exception as e:
        logger.error(f"❌ Price block fetch failed: {e}")
        # Return N/A for all tickers
        return {label: "N/A" for label in tickers.keys()}

def generate_gpt_comment(prices: dict, region: str) -> str:
    """Generate GPT commentary on market prices with fallback"""
    try:
        # Filter out N/A values for cleaner prompt
        valid_prices = {k: v for k, v in prices.items() if v != "N/A"}
        
        if not valid_prices:
            return f"Market data unavailable for {region} briefing analysis."
        
        summary = ", ".join(f"{k}: {v}" for k, v in valid_prices.items())
        prompt = f"In 2-3 sentences, provide a hedge fund style summary of {region} market sentiment based on: {summary}"
        
        response = generate_gpt_text(prompt, max_tokens=250)
        clean_response = response.replace("**", "").strip()
        
        return clean_response if clean_response else f"Market analysis for {region} unavailable."
        
    except Exception as e:
        logger.error(f"❌ GPT comment generation failed: {e}")
        return f"Market commentary unavailable for {region} due to processing error."

def generate_briefing_pdf_robust(briefing_type: str = "morning") -> str:
    """
    Generate briefing PDF with IG API + yfinance architecture
    """
    logger.info(f"📄 Generating {briefing_type} briefing PDF using IG API + yfinance")
    limit = 5  # Number of top movers to show
    
    # ═══════════════════════════════════════════════════════════════
    # CALENDAR DATA: Handle with graceful fallbacks
    # ═══════════════════════════════════════════════════════════════
    
    # IPO Calendar
    try:
        ipo_list = get_ipo_calendar()
        logger.info(f"✅ IPO calendar: {len(ipo_list)} items")
    except Exception as e:
        logger.warning(f"⚠️ IPO calendar failed: {e}")
        ipo_list = []

    # Earnings Calendar  
    try:
        earnings_list = get_earnings_calendar()
        logger.info(f"✅ Earnings calendar: {len(earnings_list)} items")
    except Exception as e:
        logger.warning(f"⚠️ Earnings calendar failed: {e}")
        earnings_list = []
    
    # Economic Calendar (disabled)
    econ_df = pd.DataFrame()
    logger.info("📅 Economic calendar disabled - using empty fallback")
    
    # ═══════════════════════════════════════════════════════════════
    # MARKET DATA BLOCKS: Using IG API + yfinance fallback
    # ═══════════════════════════════════════════════════════════════
    
    try:
        logger.info("📊 Fetching market data blocks using IG API + yfinance...")
        equity_block, macro_block, crypto_block = get_market_blocks(briefing_type)
        logger.info(f"✅ Market data: Equity={len(equity_block)}, Macro={len(macro_block)}, Crypto={len(crypto_block)}")
    except Exception as e:
        logger.error(f"❌ Market data blocks failed: {e}")
        # Create minimal fallback blocks
        equity_block = {"Market Data": "Unavailable"}
        macro_block = {"Macro Data": "Unavailable"}
        crypto_block = {"Crypto Data": "Unavailable"}

    # Convert US Treasury futures to yields
    try:
        equity_block = convert_us_treasury_yields(equity_block)
        macro_block = convert_us_treasury_yields(macro_block)
        logger.info("✅ Treasury yields converted")
    except Exception as e:
        logger.warning(f"⚠️ Treasury yield conversion failed: {e}")

    # ═══════════════════════════════════════════════════════════════
    # GPT COMMENT: Generate with fallback
    # ═══════════════════════════════════════════════════════════════
    
    try:
        combined_prices = {**equity_block, **macro_block, **crypto_block}
        comment = generate_gpt_comment(combined_prices, briefing_type)
        logger.info("✅ GPT comment generated")
    except Exception as e:
        logger.warning(f"⚠️ GPT comment failed: {e}")
        comment = f"Market briefing for {briefing_type} - automated analysis unavailable"

    # ═══════════════════════════════════════════════════════════════
    # HEADLINES: Fetch with error handling
    # ═══════════════════════════════════════════════════════════════
    
    try:
        headlines = get_briefing_headlines(briefing_type)
        logger.info(f"✅ Headlines: {len(headlines)} items")
    except Exception as e:
        logger.warning(f"⚠️ Headlines failed: {e}")
        headlines = []

    # ═══════════════════════════════════════════════════════════════
    # MOVERS DATA: Using pure yfinance for top gainers/losers
    # ═══════════════════════════════════════════════════════════════
    
    mover_block = None
    mover_title = None
    mover_news = {}

    if briefing_type not in ["morning", "mid_day"]:
        try:
            logger.info("📈 Fetching top movers using pure yfinance...")
            movers = get_top_movers_from_constituents(limit=limit, include_extended=True)

            if briefing_type == "pre_market":
                # For pre-market: use regular day movers (extended hours not implemented)
                gainers = movers.get("top_gainers", [])
                losers = movers.get("top_losers", [])
                mover_title = "Top Pre-Market Movers"
                
                mover_block = {
                    "top_gainers": {
                        item['symbol']: f"{item['price']:.2f} ({item['change_percent']:+.2f}%)" 
                        for item in gainers[:limit]
                    },
                    "top_losers": {
                        item['symbol']: f"{item['price']:.2f} ({item['change_percent']:+.2f}%)" 
                        for item in losers[:limit]
                    }
                }

            elif briefing_type == "after_market":
                # For after-market: use regular day movers (extended hours not implemented)
                gainers = movers.get("top_gainers", [])
                losers = movers.get("top_losers", [])
                mover_title = "Top After-Market Movers"
                
                mover_block = {
                    "top_gainers": {
                        item['symbol']: f"{item['price']:.2f} ({item['change_percent']:+.2f}%)" 
                        for item in gainers[:limit]
                    },
                    "top_losers": {
                        item['symbol']: f"{item['price']:.2f} ({item['change_percent']:+.2f}%)" 
                        for item in losers[:limit]
                    }
                }
                
            logger.info("✅ Movers data processed using yfinance")
            
        except Exception as e:
            logger.warning(f"⚠️ Movers data failed: {e}")
            # Create empty mover block
            mover_title = f"Top {briefing_type.replace('_', '-').title()} Movers"
            mover_block = {
                "top_gainers": {"Data": "Unavailable"},
                "top_losers": {"Data": "Unavailable"}
            }

        # Get news for movers if available
        if mover_block and any(mover_block.values()):
            try:
                mover_news = get_news_for_movers(mover_block)
                logger.info(f"✅ Mover news: {len(mover_news)} tickers")
            except Exception as e:
                logger.warning(f"⚠️ Mover news failed: {e}")
                mover_news = {}

    # ═══════════════════════════════════════════════════════════════
    # PDF RENDERING: Final step with comprehensive error handling
    # ═══════════════════════════════════════════════════════════════
    
    try:
        logger.info("📄 Rendering PDF...")
        pdf_path = render_pdf(
            headlines=headlines,
            equity_block=equity_block,
            macro_block=macro_block,
            crypto_block=crypto_block,
            comment=comment,
            period=briefing_type,
            mover_block=mover_block,
            mover_title=mover_title,
            mover_news=mover_news,
            econ_df=econ_df,
            ipo_list=ipo_list,
            earnings_list=earnings_list
        )
        logger.info(f"✅ PDF rendered successfully: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        logger.error(f"❌ PDF rendering failed: {e}")
        import traceback
        traceback.print_exc()
        raise

def get_briefing_headlines(briefing_type: str) -> list:
    """
    Get headlines with error handling
    """
    try:
        now = datetime.utcnow()

        if briefing_type not in {"morning", "mid_day"}:
            return []

        if briefing_type == "morning":
            start = (now - timedelta(days=1)).replace(hour=16, minute=0, second=0)
        elif briefing_type == "mid_day":
            start = now.replace(hour=6, minute=30, second=0)
        else:
            start = now - timedelta(hours=24)

        files = [
            os.path.join(DATA_DIR, "scored_headlines_macro.csv"),
            os.path.join(DATA_DIR, "scored_headlines_political.csv"),
        ]

        result = []

        for file in files:
            if not os.path.exists(file):
                logger.warning(f"⚠️ Headlines file not found: {file}")
                continue

            try:
                with open(file, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        timestamp = row.get("timestamp")
                        if not timestamp:
                            continue
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            if dt >= start:
                                score = int(row.get("score", 0))
                                headline = row.get("headline", "")
                                url = row.get("url", "")
                                result.append((score, headline, url))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"⚠️ Invalid headline row: {e}")
                            continue
            except Exception as e:
                logger.warning(f"⚠️ Failed to read {file}: {e}")
                continue

        return sorted(result, key=lambda x: -x[0])[:15]
        
    except Exception as e:
        logger.error(f"❌ Headlines fetch failed: {e}")
        return []

def get_market_blocks(briefing_type: str) -> tuple:
    """
    Get market data blocks using IG API + yfinance fallback
    """
    try:
        if briefing_type == "morning":
            equity = {**ASIA_EQUITY, **EUROPE_EQUITY, "S&P Futures": US_EQUITY["S&P 500"]}
            macro = {**FX_PAIRS, **RATES, **COMMODITIES}

        elif briefing_type == "pre_market":
            equity = {**US_EQUITY, **RATES, "Gold": COMMODITIES["Gold"], "Crude Oil": COMMODITIES["Crude Oil"]}
            macro = {}  # Empty for pre-market, movers in block 2
            
        elif briefing_type == "mid_day":
            equity = {**EUROPE_EQUITY, **US_EQUITY}
            macro = {**FX_PAIRS, **RATES}

        elif briefing_type == "after_market":
            equity = {
                **US_EQUITY, **RATES, 
                "Gold": COMMODITIES["Gold"], 
                "Crude Oil": COMMODITIES["Crude Oil"], 
                "USD/JPY": FX_PAIRS["USD/JPY"], 
                "EUR/USD": FX_PAIRS["EUR/USD"]
            }
            macro = {}  # Empty for after-market, movers in block 2

        else:
            equity = {}
            macro = {}   

        # Fetch data using IG API + yfinance fallback
        equity_data = fetch_price_block(equity) if equity else {}
        macro_data = fetch_price_block(macro) if macro else {}
        crypto_data = fetch_crypto_block()

        return equity_data, macro_data, crypto_data
        
    except Exception as e:
        logger.error(f"❌ Market blocks fetch failed: {e}")
        # Return minimal fallback data
        return (
            {"Market": "Data Unavailable"}, 
            {"Macro": "Data Unavailable"}, 
            {"Crypto": "Data Unavailable"}
        )

def get_news_for_movers(mover_block: dict, window_hours=18) -> dict:
    """Get news for top movers with error handling"""
    try:
        now = datetime.utcnow()
        start = (now - timedelta(hours=window_hours)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        news_by_ticker = {}
        
        for section in ["top_gainers", "top_losers"]:
            tickers = mover_block.get(section, {})
            for ticker in tickers.keys():
                if ticker in ["Data", "Market", "Unavailable"]:  # Skip error placeholders
                    continue
                    
                try:
                    logger.info(f"📰 Fetching news for {ticker}")
                    news = fetch_stock_news(ticker, start, end)
                    if news:
                        news_by_ticker[ticker] = news[:2]  # Limit to 2 articles
                except Exception as e:
                    logger.warning(f"⚠️ News fetch failed for {ticker}: {e}")

        return news_by_ticker
        
    except Exception as e:
        logger.error(f"❌ Mover news fetch failed: {e}")
        return {}

def test_ig_yfinance_system():
    """
    Test the complete IG API + yfinance system
    """
    print("🧪 Testing Complete IG API + yfinance System")
    print("=" * 60)
    
    # Test 1: Market data client
    print("1️⃣ Testing market data client...")
    try:
        client = get_market_data_client()
        print(f"   ✅ Client initialized: {type(client).__name__}")
        
        # Test health
        health = client.health_check()
        print(f"   IG Index: {'✅' if health.get('ig_index') else '❌'}")
        print(f"   yfinance: {'✅' if health.get('yfinance') else '❌'}")
        print(f"   Overall: {'✅' if health.get('overall') else '❌'}")
    except Exception as e:
        print(f"   ❌ Client test failed: {e}")
    
    # Test 2: Ticker blocks (IG API + yfinance fallback)
    print("\n2️⃣ Testing ticker blocks (IG API + yfinance fallback)...")
    try:
        test_tickers = {
            "S&P 500": "^GSPC",
            "EUR/USD": "EURUSD=X",
            "Gold": "GC=F",
            "Apple": "AAPL"  # Should use yfinance fallback
        }
        
        ticker_results = fetch_price_block(test_tickers)
        for label, result in ticker_results.items():
            if result != "N/A":
                print(f"   ✅ {label}: {result}")
            else:
                print(f"   ❌ {label}: N/A")
    except Exception as e:
        print(f"   ❌ Ticker blocks test failed: {e}")
    
    # Test 3: Top movers (pure yfinance)
    print("\n3️⃣ Testing top movers (pure yfinance)...")
    try:
        start_time = datetime.now()
        movers = get_top_movers_from_constituents(limit=3)
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if 'error' not in movers:
            print(f"   ✅ Movers scan: {elapsed:.1f}s")
            print(f"   Scanned: {movers['total_scanned']} symbols")
            print(f"   Valid: {movers['valid_results']} results")
            print(f"   Gainers: {len(movers['top_gainers'])}")
            print(f"   Losers: {len(movers['top_losers'])}")
        else:
            print(f"   ❌ Movers failed: {movers['error']}")
    except Exception as e:
        print(f"   ❌ Top movers test failed: {e}")
    
    # Test 4: Crypto
    print("\n4️⃣ Testing crypto...")
    try:
        crypto_data = fetch_crypto_block()
        valid_crypto = sum(1 for v in crypto_data.values() if v != "N/A")
        print(f"   ✅ Crypto: {valid_crypto}/{len(crypto_data)} valid")
    except Exception as e:
        print(f"   ❌ Crypto test failed: {e}")
    
    # Test 5: Full briefing generation
    print("\n5️⃣ Testing full briefing generation...")
    try:
        start_time = datetime.now()
        pdf_path = generate_briefing_pdf_robust("morning")
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path) / 1024  # KB
            print(f"   ✅ PDF generated: {elapsed:.1f}s")
            print(f"   File: {os.path.basename(pdf_path)}")
            print(f"   Size: {file_size:.1f} KB")
        else:
            print(f"   ❌ PDF not created")
    except Exception as e:
        print(f"   ❌ Briefing test failed: {e}")
    
    print(f"\n{'='*60}")
    print("✅ IG API + yfinance system test completed")

def test_morning_briefing():
    """Simple test of morning briefing generation"""
    print("🧪 Testing Morning Briefing with IG API + yfinance...")
    
    try:   
        pdf_path = generate_briefing_pdf_robust("morning")
        print(f"✅ PDF generated successfully: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

# Legacy function for compatibility
def generate_briefing_pdf(briefing_type: str = "morning") -> str:
    """Legacy function - redirects to robust version"""
    return generate_briefing_pdf_robust(briefing_type)

# Legacy function for compatibility  
def generate_briefing_pdf_test(briefing_type: str = "morning") -> str:
    """Legacy test function - redirects to robust version"""
    return generate_briefing_pdf_robust(briefing_type)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--full":
            # Run full briefing: python -m content.briefings --full
            path = generate_briefing_pdf_robust("morning")
            print(f"PDF created: {path}")
            
        elif command == "--test":
            # Test mode: python -m content.briefings --test
            test_morning_briefing()
            
        elif command == "--system-test":
            # System test: python -m content.briefings --system-test
            test_ig_yfinance_system()
            
        elif command == "--pre-market":
            # Pre-market briefing: python -m content.briefings --pre-market
            path = generate_briefing_pdf_robust("pre_market")
            print(f"Pre-market PDF created: {path}")
            
        else:
            print("Available commands:")
            print("  --full        : Generate full morning briefing")
            print("  --test        : Test morning briefing generation")
            print("  --system-test : Test complete IG API + yfinance system")
            print("  --pre-market  : Generate pre-market briefing")
    else:
        # Default: Test mode (safe - no blob/notion/twitter)
        test_morning_briefing()