from fpdf import FPDF

def create_pdf_with_chart(title: str, chart_path: str, summary_text: str, output_file: str):
    """
    Generate a PDF containing a chart and additional info.
    :param title: The title of the PDF document.
    :param chart_path: Path to the chart image.
    :param summary_text: Text content summarizing market trends.
    :param output_file: Path to save the PDF file.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Arial", size=16)
    pdf.cell(0, 10, title, ln=True, align="C")

    # Add chart
    pdf.image(chart_path, x=10, y=30, w=180)

    # Add summary text
    pdf.set_font("Arial", size=12)
    pdf.ln(100)  # Move below the image
    pdf.multi_cell(0, 10, summary_text)

    # Save PDF
    pdf.output(output_file)
    print(f"PDF saved to {output_file}")
