import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional

from mchangohub import settings


def generate_contribution_summary_statement_pdf(
        transactions: List[Dict],
        contribution_name: str,
        target_amount: Decimal,
        period_start: datetime,
        period_end: datetime,
        filename: Optional[str] = None,
) -> str:
    """
    Generate a contribution statement PDF (similar to MPESA statements).
    Excludes charge & counterparty columns.
    """

    temp_dir = os.path.join(settings.BASE_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    safe_name = contribution_name.replace(" ", "_").lower()
    if filename is None:
        filename = f"statement_{safe_name}.pdf"

    file_path = os.path.join(temp_dir, filename)

    txs = sorted(transactions, key=lambda x: x["timestamp"])
    total_contributed = sum(Decimal(str(t.get("paid_in", 0) or 0)) for t in txs)
    remaining = target_amount - total_contributed

    faint_green = colors.HexColor("#F0F9F0")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(A4),
        rightMargin=1 * cm,
        leftMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )

    page_width, _ = landscape(A4)
    usable_width = page_width - doc.leftMargin - doc.rightMargin

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

    logo_path = os.path.join(settings.BASE_DIR, "templates", "mchango.jpg")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=3 * cm, height=3 * cm)
    else:
        logo = Paragraph("<b>MCHANGO HUB</b>", sub_heading)

    heading_para = Paragraph("<b>MCHANGO HUB</b><br/>SUMMARY STATEMENT", main_heading)
    tagline_para = Paragraph("Your Digital Financial Partner", sub_heading)

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
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(header_content)
    elements.append(Spacer(1, 20))

    acc_info = [
        ["Contribution Name:", contribution_name, "Period From:", period_start.strftime("%Y-%m-%d")],
        ["Target Amount:", f"KES {target_amount:,.2f}", "Period To:", period_end.strftime("%Y-%m-%d")],
        ["Statement Date:", datetime.now().strftime("%Y-%m-%d"), "Remaining:", f"KES {remaining:,.2f}"],
        ["Total Contributed:", f"KES {total_contributed:,.2f}", "", ""],
    ]
    acc_table = Table(acc_info, colWidths=[usable_width * 0.2, usable_width * 0.3,
                                           usable_width * 0.2, usable_width * 0.3])
    acc_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(acc_table)
    elements.append(Spacer(1, 15))

    wrap_style = ParagraphStyle(name="WrapStyle", fontSize=8, leading=10, wordWrap="CJK")

    chunk_size = 10
    for chunk_start in range(0, len(txs), chunk_size):
        chunk = txs[chunk_start:chunk_start + chunk_size]

        data = [["Date/Time", "Type", "Narration", "Reference", "Paid In", "Withdrawn", "Balance"]]

        running = Decimal("0.00")
        for t in chunk:
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

        transaction_table = Table(data, repeatRows=1, colWidths=[
            usable_width * 0.1, usable_width * 0.1, usable_width * 0.25,
            usable_width * 0.1, usable_width * 0.125,
            usable_width * 0.125, usable_width * 0.125
        ])
        transaction_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), faint_green),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(transaction_table)

        if chunk_start + chunk_size < len(txs):
            elements.append(PageBreak())

    doc.build(elements)
    return file_path
