import os
from datetime import datetime
from fpdf import FPDF
from utils.config import DATA_DIR
from utils.gpt import generate_gpt_text

BRIEFING_DIR = os.path.join(DATA_DIR, "briefings")
os.makedirs(BRIEFING_DIR, exist_ok=True)

def render_pdf(
    headlines,
    equity_block,
    macro_block,
    crypto_block,
    comment,
    period,
    mover_block=None,
    mover_title=None,
    mover_news=None
) -> str:
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    filename = f"briefing_{period}_{date_str}.pdf"
    filepath = os.path.join(BRIEFING_DIR, filename)

    pdf = FPDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", uni=True)

    pdf.set_font("DejaVu", "B", 14)
    pdf.add_page()
    pdf.cell(0, 10, f"{period.capitalize()} Market Briefing - {date_str}", ln=True, align="C")

     # For morning and mid_day, pass macro block to render_block, no movers
    if period in {"morning", "mid_day"}:
        render_block(equity_block, macro_block, crypto_block, macro_block, comment, pdf)
    # For pre_market and after_market, pass movers block, no macro
    elif period in {"pre_market", "after_market"}:
        render_block(equity_block, None, crypto_block, mover_block, comment, pdf)
    
    # Page 2: Headlines (show for all briefing types if headlines exist)
    if headlines:
        render_headlines_pages(pdf, headlines, date_str)
    # Page 3: News behind movers (optional)
    # if mover_news:
    #    render_mover_news(pdf, mover_news)

    pdf.output(filepath)
    return filepath

def render_mover_block(pdf, mover_block: dict, title: str):
    if not mover_block:
        return

    pdf.ln(8)
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 10, title, ln=True)

    def render_section(heading: str, entries: dict, color: str):
        if not entries:
            return

        # Section header
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(0)  # Black for heading
        pdf.cell(0, 8, heading, ln=True)

        # Ticker lines
        pdf.set_font("DejaVu", "", 11)
        r, g, b = (0, 102, 204) if color == "blue" else (204, 0, 0)
        pdf.set_text_color(r, g, b)
        for symbol, value in entries.items():
            pdf.cell(0, 8, f"{symbol}: {value}", ln=True)
        pdf.ln(3)

    render_section("Top Gainers", mover_block.get("top_gainers", {}), color="blue")
    render_section("Top Losers", mover_block.get("top_losers", {}), color="red")

    # Reset color
    pdf.set_text_color(0)

def render_block(equity_block, macro_block, crypto_block, side_block, comment, pdf):
    """
    Render the main market data blocks in two columns:
    Left column: equity_block
    Right column: macro_block or mover_block (with gainers/losers sections)
    Bottom left: robot image
    Bottom right: crypto_block
    Below full width: comment block
    """

    pdf.set_font("DejaVu", size=11)
    margin_x = 15
    box_width_total = 190
    row_height = 8
    left_col_width = 110
    right_col_width = box_width_total - left_col_width
    left_x_start = margin_x + 2
    right_x_start = margin_x + left_col_width -8

    keys_eq = list(equity_block.keys()) if equity_block else []
    keys_side = list()
    is_movers = False

    # Determine if side_block is movers (dict with top_gainers and top_losers keys)
    if side_block and isinstance(side_block, dict) and "top_gainers" in side_block and "top_losers" in side_block:
        is_movers = True
    else:
        keys_side = list(side_block.keys()) if side_block else []

    # Calculate max rows for top part
    max_rows_top = max(len(keys_eq), len(keys_side) if not is_movers else max(len(side_block["top_gainers"]), len(side_block["top_losers"])))

    max_rows_crypto = len(crypto_block)

    # Create a temp PDF for calculating comment height
    temp_pdf = FPDF()
    temp_pdf.add_page()
    temp_pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", uni=True)
    temp_pdf.set_font("DejaVu", size=11)
    comment_lines = temp_pdf.multi_cell(box_width_total - 4, 8, f"--- Market Sentiment Summary --- \n{comment}", split_only=True)
    comment_height = len(comment_lines) * 8 + 8  # approx line height * number lines + padding

    def color_text(val, is_gainer=None):
        if is_gainer is not None:
            if is_gainer:
                pdf.set_text_color(0, 102, 204)  # Blue
            else:
                pdf.set_text_color(204, 0, 0)    # Red
        else:
            if "+" in val:
                pdf.set_text_color(0, 102, 204)
            elif "-" in val:
                pdf.set_text_color(204, 0, 0)
            else:
                pdf.set_text_color(0)

    y_start = pdf.get_y()

    # Left column: Equity block
    for i in range(max_rows_top):
        y = y_start + i * row_height
        if i < len(keys_eq):
            label = keys_eq[i]
            val = equity_block[label]
            pdf.set_xy(left_x_start, y + 1)
            color_text(val)
            pdf.set_font("DejaVu", "B", size=11)
            pdf.cell(45, 6, f"{label}:")
            pdf.set_font("DejaVu", size=11)
            pdf.cell(left_col_width - 47, 6, val)

    # Right column: Macro block or Movers block
    if is_movers:
        y_pos = y_start
        # Render Top Gainers Header
        pdf.set_xy(right_x_start, y_pos)
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(0)
        pdf.cell(0, 10, "Top Gainers", ln=True)
        y_pos += 10
        symbol_cell_width = 27

        # Render Top Gainers Entries with aligned symbol and price
        pdf.set_font("DejaVu", "", 11)
        for symbol, val in side_block["top_gainers"].items():
            pdf.set_xy(right_x_start, y_pos)
            pdf.set_font("DejaVu", "B", 11)
            color_text(val, is_gainer=True)  # blue for gainers
            pdf.cell(symbol_cell_width, 8, f"{symbol}:", ln=0)  # fixed width for symbol

            pdf.set_font("DejaVu", "", 11)
            color_text(val, is_gainer=True)  # blue for gainers
            pdf.cell(right_col_width - symbol_cell_width - 8, 8, val, ln=1)  # price + % aligned, new line after

            y_pos += 8

        y_pos += 5
        # Render Top Losers Header
        pdf.set_xy(right_x_start, y_pos)
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(0)
        pdf.cell(0, 10, "Top Losers", ln=True)
        y_pos += 10
        symbol_cell_width = 27

        # Render Top Losers Entries
        pdf.set_font("DejaVu", "", 11)
        for symbol, val in side_block["top_losers"].items():
            pdf.set_xy(right_x_start, y_pos)
            pdf.set_font("DejaVu", "B", 11)
            color_text(val, is_gainer=False)  # red for losers
            pdf.cell(symbol_cell_width, 8, f"{symbol}:", ln=0)  # fixed width symbol cell

            pdf.set_font("DejaVu", "", 11)
            color_text(val, is_gainer=False)  # red for losers
            pdf.cell(right_col_width - symbol_cell_width -8, 8, val, ln=1)

            y_pos += 8

        pdf.set_text_color(0)

    else:
        for i in range(max_rows_top):
            y = y_start + i * row_height
            if i < len(keys_side):
                label = keys_side[i]
                val = side_block[label]
                pdf.set_xy(right_x_start, y + 1)
                color_text(val)
                pdf.set_font("DejaVu", "B", 11)
                pdf.cell(45, 6, f"{label}:")
                pdf.set_font("DejaVu", size=11)
                pdf.cell(right_col_width - 47, 6, val)

    # Calculate height for left column (equity rows)
    height_left = max_rows_top * row_height

    # Calculate height for right column (macro or movers)
    if is_movers:
        movers = side_block
        height_right = (
            10 +  # Top Gainers header height
            len(movers.get("top_gainers", {})) * row_height +
            5 +   # space between sections
            10 +  # Top Losers header height
            len(movers.get("top_losers", {})) * row_height +
            5     # bottom padding
        )
    else:
        height_right = len(keys_side) * row_height

    max_top_height = max(height_left, height_right)

    # Bottom row heights
    robot_image_height = 45
    crypto_block_height = max_rows_crypto * row_height
    bottom_row_height = max(robot_image_height, crypto_block_height)

    # Total block height including all parts + padding
    total_height = max_top_height + bottom_row_height + comment_height + 30

    # Draw outer rectangles after all heights known
    pdf.set_draw_color(0)
    pdf.set_line_width(0.4)
    pdf.rect(margin_x - 1, y_start - 1, box_width_total + 2, total_height + 2)
    pdf.set_draw_color(160)
    pdf.set_line_width(0.2)
    pdf.rect(margin_x, y_start, box_width_total, total_height)

    # Draw horizontal dividing lines
    y_bottom = y_start + max_top_height + 6
    pdf.set_draw_color(180)
    pdf.line(margin_x, y_bottom, margin_x + box_width_total, y_bottom)

    y_comment_start = y_start + max_top_height + bottom_row_height + 10
    pdf.set_draw_color(180)
    pdf.line(margin_x, y_comment_start, margin_x + box_width_total, y_comment_start)

    # Robot image bottom left
    pdf.image("content/assets/AI Hedge Fund Analyst - resized for pdf.png", x=margin_x + 2, y=y_bottom + 4, w=45)

    # Crypto block bottom right
    keys_crypto = list(crypto_block.keys())
    for j, label in enumerate(keys_crypto):
        val = crypto_block[label]
        y = y_bottom + 4 + j * row_height
        pdf.set_xy(right_x_start, y)
        symbol_cell_width = 27

        # Print symbol aligned left in a fixed width cell
        pdf.set_font("DejaVu", "B", 11)
        color_text(val)  # Set color by plus/minus sign
        pdf.cell(symbol_cell_width, 6, f"{label}:", ln=0)

        # Print price and % change aligned left immediately after symbol
        pdf.set_font("DejaVu", size=11)
        color_text(val)  # Set color by plus/minus sign
        pdf.cell(right_col_width - symbol_cell_width -8, 6, val, ln=1)

    # Comment block full width below
    pdf.set_text_color(0)
    pdf.set_font("DejaVu", size=11)
    pdf.set_xy(margin_x + 2, y_comment_start + 3)
    pdf.multi_cell(box_width_total - 4, 8, f"--- Market Sentiment Summary --- \n{comment}")

def render_headlines_pages(pdf, headlines, date_str):
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Top Headlines –  {date_str}", ln=True, align="C")
    pdf.ln(5)

    pdf.set_left_margin(20)
    pdf.set_right_margin(20)
    pdf.set_font("DejaVu", size=11)

    if not headlines:
        pdf.cell(0, 10, "No headlines available.", ln=True)
    else:
        for idx, (score, headline, url) in enumerate(headlines):
            block_height_estimate = 60
            page_height = 297
            available_space = page_height - pdf.get_y() - 15

            if available_space < block_height_estimate:
                pdf.add_page()
                pdf.set_left_margin(20)
                pdf.set_right_margin(20)
                pdf.set_font("DejaVu", "B", 14)
                pdf.cell(0, 10, f"Top Headlines –  {date_str} (cont’d)", ln=True, align="C")
                pdf.ln(5)

            pdf.set_text_color(0)
            pdf.set_font("DejaVu", "B", 11)
            pdf.multi_cell(0, 8, headline)
            pdf.set_y(pdf.get_y() - 2)

            pdf.set_text_color(0, 0, 255)
            pdf.set_font("DejaVu", "", 11)
            pdf.write(8, url, url)
            pdf.set_y(pdf.get_y() + 8)

            pdf.set_draw_color(200)
            x_start = pdf.get_x()
            y_pos = pdf.get_y()
            x_end = 210 - 20
            pdf.line(x_start, y_pos, x_end, y_pos)
            pdf.ln(6)

            prompt = (
                "As a hedge fund investor, provide 2–3 sentences of market-relevant commentary "
                f"on the following news without repeating or restating the headline: {headline}"
            )

            comment = generate_gpt_text(prompt, max_tokens=160).strip()

            pdf.set_text_color(0)
            pdf.set_font("DejaVu", size=11)
            pdf.multi_cell(0, 8, comment)
            pdf.ln(10)

def render_mover_news(pdf, mover_news: dict):
    if not mover_news:
        return

    pdf.add_page()
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, "News Behind the Movers", ln=True)
    pdf.ln(5)

    for ticker, articles in mover_news.items():
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 8, ticker, ln=True)
        pdf.set_font("DejaVu", "", 11)
        for a in articles:
            pdf.multi_cell(0, 7, f"- {a['headline']} ({a['source']})")
            if a['url']:
                pdf.set_text_color(0, 0, 255)
                pdf.write(7, a['url'], a['url'])
                pdf.set_text_color(0)
            pdf.ln(4)
        pdf.ln(3)

def render_comment_block(pdf, comment: str):
    pdf.ln(5)
    pdf.set_text_color(0)
    pdf.set_font("DejaVu", size=11)
    pdf.multi_cell(0, 8, f"--- Market Sentiment Summary --- \n{comment}")

