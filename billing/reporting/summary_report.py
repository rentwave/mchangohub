import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
    PageBreak, KeepTogether, PageTemplate, BaseDocTemplate, Frame
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus.doctemplate import NextPageTemplate
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional

from mchangohub import settings


class ContributionNumberedCanvas:
    """Custom canvas to add page numbers and footers for contribution statements"""

    def __init__(self, canvas, doc, contribution_name: str, period_start: datetime, period_end: datetime):
        self.canvas = canvas
        self.doc = doc
        self.contribution_name = contribution_name
        self.period_start = period_start
        self.period_end = period_end

    def draw_footer(self):
        """Draw footer on each page"""
        page_width, page_height = self.canvas._pagesize

        # Footer text
        footer_text = (
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Page {self.canvas._pageNumber} | "
            f"Mchango Hub Digital Services"
        )

        # Draw footer background
        self.canvas.setFillColor(colors.HexColor("#F0F9F0"))
        self.canvas.rect(
            self.doc.leftMargin,
            self.doc.bottomMargin - 30,
            page_width - self.doc.leftMargin - self.doc.rightMargin,
            25,
            fill=1,
            stroke=1
        )

        # Draw footer text
        self.canvas.setFillColor(colors.black)
        self.canvas.setFont("Helvetica", 8)
        self.canvas.drawCentredText(
            page_width / 2,
            self.doc.bottomMargin - 20,
            footer_text
        )

    def draw_header(self):
        """Draw header on pages after first page"""
        if self.canvas._pageNumber > 1:
            page_width, page_height = self.canvas._pagesize

            # Header background
            self.canvas.setFillColor(colors.HexColor("#F0F9F0"))
            self.canvas.rect(
                self.doc.leftMargin,
                page_height - self.doc.topMargin,
                page_width - self.doc.leftMargin - self.doc.rightMargin,
                40,
                fill=1,
                stroke=1
            )

            # Header text
            self.canvas.setFillColor(colors.black)
            self.canvas.setFont("Helvetica-Bold", 12)
            self.canvas.drawCentredText(
                page_width / 2,
                page_height - self.doc.topMargin + 20,
                f"MCHANGO HUB CONTRIBUTION SUMMARY - {self.contribution_name}"
            )

            self.canvas.setFont("Helvetica", 9)
            self.canvas.drawCentredText(
                page_width / 2,
                page_height - self.doc.topMargin + 5,
                f"Period: {self.period_start.strftime('%Y-%m-%d')} to {self.period_end.strftime('%Y-%m-%d')}"
            )


def on_contribution_first_page(canvas, doc, contribution_name: str, period_start: datetime, period_end: datetime):
    """First page callback for contribution statement"""
    numbered_canvas = ContributionNumberedCanvas(canvas, doc, contribution_name, period_start, period_end)
    numbered_canvas.draw_footer()


def on_contribution_later_pages(canvas, doc, contribution_name: str, period_start: datetime, period_end: datetime):
    """Later pages callback for contribution statement"""
    numbered_canvas = ContributionNumberedCanvas(canvas, doc, contribution_name, period_start, period_end)
    numbered_canvas.draw_header()
    numbered_canvas.draw_footer()


def generate_contribution_summary_statement_pdf(
        transactions: List[Dict],
        contribution_name: str,
        target_amount: Decimal,
        period_start: datetime,
        period_end: datetime,
        filename: Optional[str] = None,
        transactions_per_page: int = 25,
) -> str:
    """
    Generate a contribution statement PDF with page breaks and consistent footers.
    Excludes charge & counterparty columns.

    Args:
        transactions: list of dicts with keys:
            - timestamp: datetime
            - type: str
            - narration: str
            - reference: str
            - paid_in: Decimal/float
            - withdrawn: Decimal/float
        contribution_name: name of the contribution
        target_amount: target contribution amount
        period_start: start date for the statement period
        period_end: end date for the statement period
        filename: optional filename for the PDF
        transactions_per_page: number of transactions per page (default: 25)
    """

    temp_dir = os.path.join(settings.BASE_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    safe_name = contribution_name.replace(" ", "_").lower()
    if filename is None:
        filename = f"statement_{safe_name}.pdf"

    file_path = os.path.join(temp_dir, filename)

    txs = sorted(transactions, key=lambda x: x["timestamp"])
    total_contributed = sum(Decimal(str(t.get("paid_in", 0) or 0)) for t in txs)
    total_withdrawn = sum(Decimal(str(t.get("withdrawn", 0) or 0)) for t in txs)
    net_contributed = total_contributed - total_withdrawn
    remaining = target_amount - net_contributed

    faint_green = colors.HexColor("#F0F9F0")

    # Create document with custom page templates
    doc = BaseDocTemplate(
        file_path,
        pagesize=landscape(A4),
        rightMargin=1 * cm,
        leftMargin=1 * cm,
        topMargin=1.5 * cm,  # Extra space for continuation headers
        bottomMargin=1.5 * cm,  # Extra space for footer
    )

    # calculate usable width for consistent table sizes
    page_width, page_height = landscape(A4)
    usable_width = page_width - doc.leftMargin - doc.rightMargin
    usable_height = page_height - doc.topMargin - doc.bottomMargin

    # Create page templates
    first_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        usable_width,
        usable_height,
        leftPadding=0,
        bottomPadding=30,  # Space for footer
        rightPadding=0,
        topPadding=0
    )

    later_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        usable_width,
        usable_height - 40,  # Less space due to header
        leftPadding=0,
        bottomPadding=30,  # Space for footer
        rightPadding=0,
        topPadding=40  # Space for header
    )

    # Define page templates
    first_page_template = PageTemplate(
        id='first',
        frames=first_frame,
        onPage=lambda canvas, doc: on_contribution_first_page(canvas, doc, contribution_name, period_start, period_end)
    )

    later_page_template = PageTemplate(
        id='later',
        frames=later_frame,
        onPage=lambda canvas, doc: on_contribution_later_pages(canvas, doc, contribution_name, period_start, period_end)
    )

    doc.addPageTemplates([first_page_template, later_page_template])

    styles = getSampleStyleSheet()

    main_heading = ParagraphStyle(
        name="MainHeading",
        fontSize=18,
        leading=22,
        alignment=1,
        spaceAfter=10,
        textColor=colors.black,
        fontName="Helvetica-Bold"
    )

    sub_heading = ParagraphStyle(
        name="SubHeading",
        fontSize=12,
        leading=14,
        alignment=1,
        spaceAfter=5,
        textColor=colors.black,
        fontName="Helvetica-Bold"
    )

    elements = []

    # Logo and header section
    logo_path = os.path.join(settings.BASE_DIR, "templates", "mchango.jpg")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=3 * cm, height=3 * cm)
    else:
        logo = Paragraph(
            "<b>MCHANGO<br/>HUB</b>",
            ParagraphStyle(
                name="LogoStyle",
                fontSize=14,
                leading=16,
                alignment=1,
                textColor=colors.black,
                fontName="Helvetica-Bold"
            )
        )

    heading_para = Paragraph("<b>MCHANGO HUB CONTRIBUTION SUMMARY</b>", main_heading)
    tagline_para = Paragraph("Your Digital Financial Partner", sub_heading)

    # Header table (3 columns)
    header_content = Table(
        [[logo, heading_para, tagline_para]],
        colWidths=[usable_width * 0.2, usable_width * 0.5, usable_width * 0.3]
    )
    header_content.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), faint_green),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
    ]))

    # Wrap header to keep it together
    elements.append(KeepTogether([header_content, Spacer(1, 20)]))

    # Contribution information and summary
    acc_info = [
        ["Contribution Name:", contribution_name, "Statement Date:", datetime.now().strftime("%Y-%m-%d")],
        ["Target Amount:", f"KES {target_amount:,.2f}", "Total Contributed:", f"KES {total_contributed:,.2f}"],
        ["Total Withdrawn:", f"KES {total_withdrawn:,.2f}", "Net Contributed:", f"KES {net_contributed:,.2f}"],
        ["Remaining Amount:", f"KES {remaining:,.2f}", "Period From:", period_start.strftime("%Y-%m-%d")],
        ["Completion %:", f"{(net_contributed / target_amount * 100):,.1f}%" if target_amount > 0 else "0.0%",
         "Period To:", period_end.strftime("%Y-%m-%d")],
    ]

    acc_table = Table(
        acc_info,
        colWidths=[usable_width * 0.2, usable_width * 0.3, usable_width * 0.2, usable_width * 0.3]
    )
    acc_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("ALIGN", (3, 0), (3, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))

    # Keep contribution info together
    elements.append(KeepTogether([acc_table, Spacer(1, 20)]))

    # Prepare transaction data
    data = [["Date/Time", "Type", "Narration", "Reference", "Paid In", "Withdrawn", "Balance"]]

    wrap_style = ParagraphStyle(
        name="WrapStyle",
        fontSize=8,
        leading=10,
        wordWrap="CJK"
    )

    # Process transactions
    running = Decimal("0.00")
    for i, t in enumerate(txs):
        paid_in = Decimal(str(t.get("paid_in", 0) or 0))
        withdrawn = Decimal(str(t.get("withdrawn", 0) or 0))
        running += paid_in
        running -= withdrawn

        narration_text = t.get("narration", "")
        words = narration_text.split()
        wrapped_lines = [" ".join(words[j:j + 4]) for j in range(0, len(words), 4)]
        narration_para = Paragraph("<br/>".join(wrapped_lines), wrap_style)

        data.append([
            t["timestamp"].strftime("%Y-%m-%d %H:%M"),
            t.get("type", ""),
            narration_para,
            t.get("reference", ""),
            f"KES {paid_in:,.2f}" if paid_in else "",
            f"KES {withdrawn:,.2f}" if withdrawn else "",
            f"KES {running:,.2f}",
        ])

    # Split transactions into pages
    header = [data[0]]  # Table header
    transaction_rows = data[1:]  # All transaction rows

    # Calculate how many transactions fit on first page vs subsequent pages
    first_page_transactions = max(1, transactions_per_page - 3)  # Account for header sections
    later_page_transactions = transactions_per_page

    # Process first page of transactions
    if transaction_rows:
        first_page_data = header + transaction_rows[:first_page_transactions]
        first_table = create_contribution_transaction_table(first_page_data, usable_width)
        elements.append(first_table)

        remaining_transactions = transaction_rows[first_page_transactions:]

        # Process remaining transactions in chunks
        while remaining_transactions:
            # Add page break and switch to later page template
            elements.append(PageBreak())
            elements.append(NextPageTemplate('later'))

            # Get next chunk
            chunk = remaining_transactions[:later_page_transactions]
            remaining_transactions = remaining_transactions[later_page_transactions:]

            # Create table for this chunk
            chunk_data = header + chunk
            chunk_table = create_contribution_transaction_table(chunk_data, usable_width)
            elements.append(chunk_table)

    # Build the document
    doc.build(elements)
    return file_path


def create_contribution_transaction_table(data, usable_width):
    """Create a consistently styled contribution transaction table"""

    transaction_table = Table(
        data,
        repeatRows=1,
        colWidths=[
            usable_width * 0.12,  # Date/Time
            usable_width * 0.12,  # Type
            usable_width * 0.28,  # Narration
            usable_width * 0.12,  # Reference
            usable_width * 0.14,  # Paid In
            usable_width * 0.14,  # Withdrawn
            usable_width * 0.08,  # Balance
        ]
    )

    faint_green = colors.HexColor("#F0F9F0")

    table_style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), faint_green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (3, -1), "LEFT"),  # Left align first 4 columns
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),  # Right align amount columns
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("VALIGN", (0, 1), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    # Style individual rows for better readability
    for row_idx in range(1, len(data)):
        # Bold the paid in amounts when they exist
        if len(data[row_idx]) > 4 and data[row_idx][4]:  # Paid In column
            table_style_commands.append(("FONTNAME", (4, row_idx), (4, row_idx), "Helvetica-Bold"))
            table_style_commands.append(
                ("TEXTCOLOR", (4, row_idx), (4, row_idx), colors.HexColor("#28a745")))  # Green for contributions

        # Bold the withdrawn amounts when they exist
        if len(data[row_idx]) > 5 and data[row_idx][5]:  # Withdrawn column
            table_style_commands.append(("FONTNAME", (5, row_idx), (5, row_idx), "Helvetica-Bold"))
            table_style_commands.append(
                ("TEXTCOLOR", (5, row_idx), (5, row_idx), colors.HexColor("#dc3545")))  # Red for withdrawals

        # Bold the balance column
        if len(data[row_idx]) > 6:  # Balance column
            table_style_commands.append(("FONTNAME", (6, row_idx), (6, row_idx), "Helvetica-Bold"))

        # Alternate row colors for better readability
        if row_idx % 2 == 0:
            table_style_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#f8f9fa")))

    transaction_table.setStyle(TableStyle(table_style_commands))
    return transaction_table