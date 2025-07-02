import os
import csv
from datetime import datetime, timedelta
from utils.text_utils import (
    TICKER_INFO, 
    is_weekend, 
    get_headlines_for_tickers, 
    flatten_and_deduplicate_headlines, 
    is_relevant_headline, 
    treasury_futures_to_yield_change
)
from utils.config import DATA_DIR
from utils.fetch_stock_data import fetch_last_price_yf
from utils.pdf_renderer import render_pdf
from data.ticker_blocks import (
    ASIA_EQUITY, 
    EUROPE_EQUITY, 
    US_EQUITY, 
    FX_PAIRS, 
    COMMODITIES, 
    RATES 
)
from utils.fetch_token_data import get_top_tokens_data
from utils.gpt import generate_gpt_text
from utils.x_post import timed_post_pdf_briefing
from utils.fetch_stock_data import get_top_movers_from_constituents, fetch_stock_news
from utils.fetch_calendars import (
    scrape_investing_econ_calendar,
    get_ipo_calendar,
    get_earnings_calendar,
)


import logging
import inspect

BRIEFING_DIR = os.path.join(DATA_DIR, "briefings")
os.makedirs(BRIEFING_DIR, exist_ok=True)

def run_briefing(period: str):
    logging.info(f"Generating {period} market briefing PDF")
    pdf_path = generate_briefing_pdf(period)
    timed_post_pdf_briefing(pdf_path, period=period)

def fetch_crypto_block() -> dict:
    """
    Returns crypto price block as {symbol: "price (%change)"}
    """
    tokens = get_top_tokens_data()
    return {
        token["ticker"]: f"{token['price']:.2f} ({token['change']:+.2f}%)"
        for token in tokens[:6]  # or whatever number you want
    }

def fetch_price_block(tickers: dict) -> dict:
    if is_weekend():
        return {label: "Weekend" for label in tickers}

    data = {}
    today = datetime.utcnow().date().isoformat()
    for label, symbol in tickers.items():
        try:
            result = fetch_last_price_yf(symbol)
            if result:
                price = result.get("price")
                pct_change = result.get("change_percent")
                timestamp = result.get("timestamp")

                if timestamp and timestamp < today:
                    data[label] = "Public Holiday"
                else:
                    price_fmt = f"{price:.4f}" if symbol.endswith("=X") else f"{price:.2f}"
                    data[label] = f"{price_fmt} ({pct_change:+.2f}%)"
            else:
                data[label] = "N/A"
        except Exception:
            data[label] = "N/A"
    return data

def generate_gpt_comment(prices: dict, region: str) -> str:
    summary = ", ".join(f"{k}: {v}" for k, v in prices.items() if v != "N/A")
    prompt = f"In 2-3 sentences, provide a hedge fund style summary of {region} market sentiment based on: {summary}"
    response = generate_gpt_text(prompt, max_tokens=250)
    clean_response = response.replace("**", "").strip()
    return clean_response

def generate_briefing_pdf(briefing_type: str = "morning") -> str:
    """
    Generate a multi-block PDF briefing for the specified period.
    Briefing types: 'morning', 'pre_market', 'mid_day', 'after_market'.
    Returns the full file path to the generated PDF.
    """

    limit = 5  # Number of top movers to show
    
    # Fetch calendar data
    econ_df = scrape_investing_econ_calendar()
    ipo_list = get_ipo_calendar()
    earnings_list = get_earnings_calendar()

    # ─── Build Market Data Blocks (implement as you already do) ───────────────
    equity_block, macro_block, crypto_block = get_market_blocks(briefing_type)

    print("Morning briefing macro block keys:", macro_block.keys())
    print("Morning briefing macro block sample data:", list(macro_block.items())[:5])

    # --- BEGIN YIELD CONVERSION BLOCK ---
    macro_yield_lines = []
    for label, value in macro_block.items():
        if "US Treasury" in label:
            yield_delta = treasury_futures_to_yield_change(label, value)
            if yield_delta:
                macro_yield_lines.append(f"{label.replace('US Treasury','yield')}: {yield_delta}")

    # ─── GPT Comment Block ────────────────────────────────────────────────────
    macro_summary = ", ".join(
        f"{k}: {v}" for k, v in macro_block.items() if v != "N/A" and "US Treasury" not in k
    )
    if macro_yield_lines:
        macro_summary = macro_summary + ", " + ", ".join(macro_yield_lines)
    comment_prompt = (
        f"In 2-3 sentences, provide a hedge fund style summary of the {briefing_type} market sentiment "
        f"based on: {macro_summary}"
    )
    comment = generate_gpt_text(comment_prompt, max_tokens=150).strip()

    # ─── Headlines for Page 2 ────────────────────────────────────────────────
    headlines = get_briefing_headlines(briefing_type) 

    # ─── Movers Block (not shown in morning briefing) ────────────────────────
    mover_block = None
    mover_title = None

    if briefing_type != "morning":
        print("USING get_top_movers_from_constituents FROM:", inspect.getfile(get_top_movers_from_constituents))
        movers = get_top_movers_from_constituents(limit=5, include_extended=True)

        if briefing_type == "pre_market":
            pre_market = movers.get("pre_market", [])
            # Separate gainers and losers
            pre_gainers = [x for x in pre_market if x[2] > 0]
            pre_losers = [x for x in pre_market if x[2] < 0]
            mover_title = "Top Pre-Market Movers"
            mover_block = {
                "top_gainers": {symbol: f"{price:.2f} ({change:+.2f}%)" for symbol, price, change in pre_gainers[:limit]},
                "top_losers": {symbol: f"{price:.2f} ({change:+.2f}%)" for symbol, price, change in pre_losers[:limit]}
            }

            # print("DEBUG pre_market:", pre_market[:5])
            # print("DEBUG pre_losers:", pre_losers)

        elif briefing_type == "after_market":
            post_market = movers.get("post_market", [])
            post_gainers = [x for x in post_market if x[2] > 0]
            post_losers = [x for x in post_market if x[2] < 0]
            mover_title = "Top After-Market Movers"
            mover_block = {
                "top_gainers": {symbol: f"{price:.2f} ({change:+.2f}%)" for symbol, price, change in post_gainers[:limit]},
                "top_losers": {symbol: f"{price:.2f} ({change:+.2f}%)" for symbol, price, change in post_losers[:limit]}
            }
        else:
            mover_data = None
            mover_title = None
            mover_block = None

    mover_news = {}

    if briefing_type in {"pre_market", "after_market"} and mover_block:
        mover_news = get_news_for_movers(mover_block)


    # Prepare headlines for PDF page 2
    if briefing_type in {"morning", "mid_day"}:
        headlines = get_briefing_headlines(briefing_type)
    else:
        # For pre/after market, use mover_news flattened into headline tuples
        headlines = flatten_and_deduplicate_headlines(mover_news)

    # ─── Render the PDF with all data blocks ─────────────────────────────────
    pdf_path = render_pdf(
        headlines=headlines,
        equity_block=equity_block,
        macro_block=macro_block,
        crypto_block=crypto_block,
        comment=comment,
        period=briefing_type,
        mover_block=mover_block if briefing_type != "morning" else None,
        mover_title=mover_title if briefing_type != "morning" else None,
        mover_news=mover_news if briefing_type in {"pre_market", "after_market"} else None,
        econ_df=econ_df,
        ipo_list=ipo_list,
        earnings_list=earnings_list
    )

    return pdf_path

def get_briefing_headlines(briefing_type: str) -> list:
    """
    Returns a list of (score, headline, url) from macro + political headline CSVs
    for 'morning' and 'mid_day' briefings only.
    """
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
            continue

        with open(file, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = row.get("timestamp")
                if not timestamp:
                    continue
                dt = datetime.fromisoformat(timestamp)
                if dt >= start:
                    result.append((int(row["score"]), row["headline"], row.get("url", "")))

    return sorted(result, key=lambda x: -x[0])[:15]

def get_market_blocks(briefing_type: str) -> tuple:
    """
    Return (equity_block, macro_block, crypto_block) based on briefing_type.
    Each block is a dict { label: "price (%change)" }
    """
    if briefing_type == "morning":
        # Block 1: Equity (Asia + Europe + S&P Futures)
        equity = {
            **ASIA_EQUITY,
            **EUROPE_EQUITY,
            "S&P Futures": US_EQUITY["S&P 500"],
        }
        # Block 2: Macro (FX + Rates + Commodities)
        macro = {
            **FX_PAIRS,
            **RATES,
            **COMMODITIES,
        }

    elif briefing_type == "pre_market":
        # Block 1: Equity (US) + Rates + Gold & Crude Oil
        equity = {
            **US_EQUITY, 
            **RATES, 
            "Gold": COMMODITIES["Gold"], 
            "Crude Oil": COMMODITIES["Crude Oil"]
        }
        macro = {} # Empty for pre-market, movers in block 2
        
    elif briefing_type == "mid_day":
        # Block 1: Equity (Europe + US)
        equity = {
            **EUROPE_EQUITY, 
            **US_EQUITY
        }
        # Block 2: Macro (FX + Rates)
        macro = {
            **FX_PAIRS, 
            **RATES
        }

    elif briefing_type == "after_market":
        # Block 1: Equity (US) + Rates + Gold & Crude Oil + Yes & Euro FX
        equity = {
            **US_EQUITY, 
            **RATES, 
            "Gold": COMMODITIES["Gold"], 
            "Crude Oil": COMMODITIES["Crude Oil"], 
            "USD/JPY": FX_PAIRS["USD/JPY"], 
            "EUR/USD": FX_PAIRS["EUR/USD"]
        }
        macro = {} # Empty for after-market, movers in block 2

    else:
        equity = {}
        macro = {}   

    crypto = fetch_crypto_block()

    return (
        fetch_price_block(equity),
        fetch_price_block(macro),
        crypto
    )

def get_news_for_movers(mover_block: dict, window_hours=18) -> dict:
    now = datetime.utcnow()
    start = (now - timedelta(hours=window_hours)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    news_by_ticker = {}
    for section in ["top_gainers", "top_losers"]:
        tickers = mover_block.get(section, {})
        for ticker in tickers.keys():
            # Your logic to fetch news for 'ticker' here
            print(f"Fetching news for ticker: {ticker}")
            try:
                news = fetch_stock_news(ticker, start, end)
                if news:
                    news_by_ticker[ticker] = news[:2]  # or whatever filtering you want
            except Exception as e:
                print(f"News error for {ticker}: {e}")

    return news_by_ticker

if __name__ == "__main__":
    path = generate_briefing_pdf("morning")
    print(f"PDF created: {path}")

