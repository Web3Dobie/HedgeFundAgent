import os
from datetime import datetime

from utils.headline_pipeline import fetch_and_score_headlines
from utils.text_utils import classify_headline_topic, is_weekend, get_headlines_for_tickers
from utils.config import DATA_DIR
from utils.fetch_stock_data import fetch_last_price_yf
from utils.pdf_renderer import render_pdf
from utils.fetch_token_data import get_top_tokens_data
from data.ticker_blocks import ASIA_EQUITY, EUROPE_EQUITY, US_EQUITY, FX_PAIRS, COMMODITIES, RATES, CRYPTO 
from utils.fetch_token_data import get_top_tokens_data
from utils.gpt import generate_gpt_text

BRIEFING_DIR = os.path.join(DATA_DIR, "briefings")
os.makedirs(BRIEFING_DIR, exist_ok=True)

def format_price(label, val, ticker=None):
    try:
        price_part, change_part = val.split(" ")
        price = float(price_part)
        if ticker and ticker.endswith("=X"):  # FX
            return f"{price:.4f} {change_part}"
        else:
            return f"{price:.2f} {change_part}"
    except Exception:
        return val

def format_crypto_block() -> dict:
    tokens = get_top_tokens_data()
    block = {}
    for token in tokens[:6]:
        price = token["price"]
        change = token["change"]
        block[token["ticker"]] = f"{price:.2f} ({change:+.2f}%)"
    return block

def get_top_headlines(period: str = "morning", limit: int = 5):
    path = os.path.join(DATA_DIR, "scored_headlines.csv")
    if not os.path.exists(path):
        return []

    today = datetime.utcnow().date().isoformat()
    headlines = []
    with open(path, encoding="utf-8") as f:
        for line in f.readlines()[1:]:
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            score, headline, url, ticker, timestamp = parts[:5]
            if timestamp.startswith(today):
                headlines.append((float(score), headline.strip(), url.strip()))

    headlines.sort(reverse=True, key=lambda x: x[0])
    return headlines[:limit]

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

def generate_briefing_pdf(period: str = "morning") -> str:
    if period == "morning":
        # Price blocks
        equity_block = fetch_price_block({**ASIA_EQUITY, **EUROPE_EQUITY, "S&P 500 Futures": "ES=F"})
        macro_block = fetch_price_block({**FX_PAIRS, **RATES, **COMMODITIES})
        crypto_block = format_crypto_block()
        comment = generate_gpt_comment({**equity_block, **macro_block, **crypto_block}, region="Global")
        headlines = get_top_headlines(period=period)
        return render_pdf(headlines, equity_block, macro_block, crypto_block, comment, period)

    raise ValueError(f"Unsupported briefing period: {period}")

if __name__ == "__main__":
    path = generate_briefing_pdf("morning")
    print(f"PDF created: {path}")

