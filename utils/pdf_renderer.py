import os
from datetime import datetime
from fpdf import FPDF
from utils.config import DATA_DIR
from utils.gpt import generate_gpt_text

BRIEFING_DIR = os.path.join(DATA_DIR, "briefings")
os.makedirs(BRIEFING_DIR, exist_ok=True)

def render_pdf(
    headlines: list[tuple], 
    equity_block: dict,
    macro_block: dict,
    crypto_block: dict,
    comment: str,
    period: str = "morning"
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

    render_block(equity_block, macro_block, crypto_block, comment, pdf)
    render_headlines_pages(pdf, headlines, date_str)

    pdf.output(filepath)
    return filepath

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
    comment_lines = temp_pdf.multi_cell(box_width_total - 4, 8, f"--- Market Sentiment Summary --- \n{comment}", split_only=True)
    comment_height = 10 * row_height + 8

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