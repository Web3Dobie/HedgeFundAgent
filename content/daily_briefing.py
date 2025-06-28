import os
from datetime import datetime
from fpdf import FPDF

from utils.headline_pipeline import fetch_and_score_headlines
from utils.text_utils import classify_headline_topic, is_weekend
from utils.config import DATA_DIR
from utils.fetch_stock_data import fetch_last_price_yf
from utils.gpt import generate_gpt_text

BRIEFING_DIR = os.path.join(DATA_DIR, "briefings")
os.makedirs(BRIEFING_DIR, exist_ok=True)

# Morning Briefing Tickers
MORNING_EQUITY = {
    "Nikkei 225": "^N225",
    "KOSPI": "^KS11",
    "Hang Seng": "^HSI",
    "CSI 300": "000300.SS",
    "Euro Stoxx 50": "^STOXX50E",
    "FTSE 100": "^FTSE",
    "DAX": "^GDAXI",
    "CAC 40": "^FCHI",
    "S&P 500": "ES=F",
}

MORNING_MACRO = {
    "USD/JPY": "JPY=X",
    "USD/CNH": "CNY=X",
    "USD/AUD": "AUDUSD=X",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "EUR/CHF": "EURCHF=X",
    "US 10YR": "ZN=F",
    "Brent": "BZ=F",
    "Gold": "GC=F",
}

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
    from utils.fetch_token_data import get_top_tokens_data  # adjust path if needed
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
    data = {}
    today = datetime.utcnow().date().isoformat()
    for label, symbol in tickers.items():
        try:
            result = fetch_last_price_yf(symbol)
            if result:
                price = result.get("price")
                pct_change = result.get("change_percent")
                timestamp = result.get("timestamp")

                if not price or not pct_change:
                    data[label] = "N/A"
                elif timestamp and timestamp < today:
                    data[label] = "Weekend" if is_weekend() else "Public Holiday"
                else:
                    # Format FX with 4 decimals, others with 2
                    price_fmt = f"{price:.4f}" if symbol.endswith("=X") else f"{price:.2f}"
                    data[label] = f"{price_fmt} ({pct_change:+.2f}%)"
            else:
                data[label] = "N/A"
        except Exception as e:
            data[label] = "N/A"
    return data

def generate_gpt_comment(prices: dict, region: str) -> str:
    summary = ", ".join(f"{k}: {v}" for k, v in prices.items() if v != "N/A")
    prompt = f"In 2-3 sentences, provide a hedge fund style summary of {region} market sentiment based on: {summary}"
    response = generate_gpt_text(prompt, max_tokens=250)
    clean_response = response.replace("**", "").strip()
    return clean_response

def render_pdf(headlines: list[tuple], period: str) -> str:
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    filename = f"briefing_{period}_{date_str}.pdf"
    filepath = os.path.join(BRIEFING_DIR, filename)

    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", uni=True)
    pdf.set_font("DejaVu", size=11)
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"{period.capitalize()} Market Briefing - {date_str}", ln=True, align="C")

    def render_block(equity_block, macro_block, crypto_block, comment, pdf):
        pdf.set_font("DejaVu", size=11)
        margin_x = 15
        box_width_total = 180
        row_height = 8
        col_width = box_width_total / 2

        max_rows_top = max(len(equity_block), len(macro_block))
        max_rows_crypto = len(crypto_block)

        temp_pdf = FPDF()
        temp_pdf.add_page()
        temp_pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", uni=True)
        temp_pdf.set_font("DejaVu", size=11)
        temp_pdf.set_xy(0, 0)
        comment_lines = temp_pdf.multi_cell(box_width_total - 4, 8, f"--- Market Sentiment Summary --- \n{comment}", split_only=True)
        comment_height = 10 * row_height + 8  # fixed space for 10 lines of comment

        block_height = (
            max_rows_top * row_height +
            max_rows_crypto * row_height +
            comment_height + 30
        )

        y_start = pdf.get_y()
        pdf.set_draw_color(0)
        pdf.set_line_width(0.4)
        pdf.rect(margin_x - 1, y_start - 1, box_width_total + 2, block_height + 2)
        pdf.set_draw_color(160)
        pdf.set_line_width(0.2)
        pdf.rect(margin_x, y_start, box_width_total, block_height)

        keys_eq = list(equity_block.keys())
        keys_mc = list(macro_block.keys())
        keys_crypto = list(crypto_block.keys())

        def color_text(val):
            if "+" in val:
                pdf.set_text_color(0, 102, 204)
            elif "-" in val:
                pdf.set_text_color(204, 0, 0)
            else:
                pdf.set_text_color(0)

        for i in range(max_rows_top):
            y = y_start + i * row_height
            if i < len(keys_eq):
                label, val = keys_eq[i], equity_block[keys_eq[i]]
                pdf.set_xy(margin_x + 2, y + 1)
                color_text(val)
                pdf.set_font("DejaVu", "B", size=11)
                pdf.cell(35, 6, f"{label}:")
                pdf.set_font("DejaVu", size=11)
                pdf.cell(col_width - 37, 6, val)

            if i < len(keys_mc):
                label, val = keys_mc[i], macro_block[keys_mc[i]]
                pdf.set_xy(margin_x + col_width + 2, y + 1)
                color_text(val)
                pdf.set_font("DejaVu", "B", size=11)
                pdf.cell(35, 6, f"{label}:")
                pdf.set_font("DejaVu", size=11)
                pdf.cell(col_width - 37, 6, val)

        y_crypto_start = y_start + max_rows_top * row_height + 6
        pdf.set_draw_color(180)
        pdf.line(margin_x, y_crypto_start, margin_x + box_width_total, y_crypto_start)

        pdf.image("content/assets/AI Hedge Fund Analyst - resized for pdf.png", x=margin_x + 2, y=y_crypto_start + 4, w=45)

        for j, label in enumerate(keys_crypto):
            val = crypto_block[label]
            y = y_crypto_start + 4 + j * row_height
            pdf.set_xy(margin_x + col_width + 2, y)
            color_text(val)
            pdf.set_font("DejaVu", "B", size=11)
            pdf.cell(35, 6, f"{label}:")
            pdf.set_font("DejaVu", size=11)
            pdf.cell(col_width - 37, 6, val)

        y_comment = y_crypto_start + 4 + max_rows_crypto * row_height + 4
        pdf.set_draw_color(180)
        pdf.line(margin_x, y_comment, margin_x + box_width_total, y_comment)
        pdf.set_text_color(0)
        pdf.set_font("DejaVu", size=11)
        pdf.set_xy(margin_x + 2, y_comment + 3)
        pdf.multi_cell(box_width_total - 4, 8, f"--- Market Sentiment Summary --- \n{comment}")

    # OUTSIDE the render_block
    morning_eq_data = fetch_price_block(MORNING_EQUITY)
    morning_mc_data = fetch_price_block(MORNING_MACRO)
    crypto_data = format_crypto_block()
    morning_comment = generate_gpt_comment({**morning_eq_data, **morning_mc_data, **crypto_data}, region="Global")
    render_block(morning_eq_data, morning_mc_data, crypto_data, morning_comment, pdf)

    # Page 2 - Top Headlines (auto-paginated)
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Top Headlines –  {date_str}", ln=True, align="C")
    pdf.ln(5)

    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)
    pdf.set_font("DejaVu", size=11)

    if not headlines:
        pdf.cell(0, 10, "No headlines available.", ln=True)
    else:
        for score, headline, url in headlines:
            # Page space check
            block_height_estimate = 60  # adjust as needed
            page_height = 297  # A4 in mm
            available_space = page_height - pdf.get_y() - 15

            if available_space < block_height_estimate:
                pdf.add_page()
                pdf.set_left_margin(20)
                pdf.set_right_margin(20)
                pdf.set_font("DejaVu", "B", 14)
                pdf.cell(0, 10, f"Top Headlines –  {date_str} (cont’d)", ln=True, align="C")
                pdf.ln(5)

            # Headline (bold)
            pdf.set_text_color(0)
            pdf.set_font("DejaVu", "B", 11)
            pdf.multi_cell(0, 8, headline)

            # Move back up slightly to avoid extra line gap
            pdf.set_y(pdf.get_y() - 2)

            # URL (blue hyperlink)
            pdf.set_text_color(0, 0, 255)
            pdf.set_font("DejaVu", "", 11)
            pdf.write(8, url, url)

            # Manually move to next line
            pdf.set_y(pdf.get_y() + 8)
            
            # Add horizontal line divider between URL and Comment
            pdf.set_draw_color(200)  # light gray
            x_start = pdf.get_x()
            y_pos = pdf.get_y()
            page_width = 210  # A4 width
            right_margin = 20
            x_end = page_width - right_margin
            pdf.line(x_start, y_pos, x_end, y_pos)
            pdf.ln(6)

            prompt = f"As a hedge fund investor, comment on this headline in 2-3 sentences: '{headline}'"
            comment = generate_gpt_text(prompt, max_tokens=160).strip()

            pdf.set_text_color(0)
            pdf.set_font("DejaVu", size=11)
            pdf.multi_cell(0, 8, comment)
            pdf.ln(10)

    pdf.output(filepath)
    return filepath

def generate_briefing_pdf(period: str = "morning") -> str:
    headlines = get_top_headlines(period=period)
    return render_pdf(headlines, period)

if __name__ == "__main__":
    path = generate_briefing_pdf("morning")
    print(f"PDF created: {path}")

