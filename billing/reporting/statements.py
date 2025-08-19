import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional

from mchangohub import settings


def generate_mpesa_statement_pdf(
        transactions: List[Dict],
        customer_name: str,
        msisdn: str,
        account_number: Optional[str],
        period_start: datetime,
        period_end: datetime,
        opening_balance: Decimal = Decimal("0.00"),
        filename: Optional[str] = None,
) -> str:
    """
    Generate an MPESA-like statement as PDF with a styled header in purple and green.
    transactions: list of dicts with keys:
        - timestamp: datetime
        - type: str
        - narration: str
        - reference: str
        - counterparty: Optional[str]
        - paid_in: Decimal/float
        - withdrawn: Decimal/float
        - charge: Decimal/float
    """

    temp_dir = os.path.join(settings.BASE_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    if filename is None:
        safe_msisdn = msisdn.replace("+", "")
        filename = f"statement_{safe_msisdn}.pdf"

    file_path = os.path.join(temp_dir, filename)
    txs = sorted(transactions, key=lambda x: x["timestamp"])
    running = opening_balance
    total_in = sum(Decimal(str(t.get("paid_in", 0) or 0)) for t in txs)
    total_out = sum(Decimal(str(t.get("withdrawn", 0) or 0)) for t in txs)
    total_charges = sum(Decimal(str(t.get("charge", 0) or 0)) for t in txs)
    net_movement = total_in - (total_out + total_charges)
    closing_balance = opening_balance + net_movement

    faint_green = colors.HexColor("#F0F9F0")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(A4),
        rightMargin=1 * cm,
        leftMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )

    # calculate usable width for consistent table sizes
    page_width, _ = landscape(A4)
    usable_width = page_width - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()
    normal = styles["Normal"]

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

    heading_para = Paragraph("<b>MCHANGO HUB FULL STATEMENT </br>", main_heading)
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
    elements.append(header_content)
    elements.append(Spacer(1, 20))

    acc_info = [
        ["Account Name:", customer_name, "Admin Contact:", msisdn],
        ["Account No:", account_number or "—", "Period From:", period_start.strftime("%Y-%m-%d")],
        ["Statement Date:", datetime.now().strftime("%Y-%m-%d"), "Period To:", period_end.strftime("%Y-%m-%d")],
        ["Opening Balance:", f"KES {opening_balance:,.2f}", "Closing Balance:", f"KES {closing_balance:,.2f}"],
    ]

    # Account info table (4 columns)
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
    elements.append(acc_table)
    elements.append(Spacer(1, 15))

    summary_data = [
        ["Total In", f"KES {total_in:,.2f}", "Total Out", f"KES {total_out:,.2f}",
         "Total Charges", f"KES {total_charges:,.2f}", "Net Movement", f"KES {net_movement:,.2f}"],
    ]
    # Summary table (8 equal columns)
    summary_table = Table(summary_data, colWidths=[usable_width / 8.0] * 8)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), faint_green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    data = [["Date/Time", "Type", "Narration", "Reference", "Counterparty",
             "Paid In", "Withdrawn", "Charge", "Balance"]]

    wrap_style = ParagraphStyle(
        name="WrapStyle",
        fontSize=8,
        leading=10,
        wordWrap="CJK"
    )

    for i, t in enumerate(txs):
        paid_in = Decimal(str(t.get("paid_in", 0) or 0))
        withdrawn = Decimal(str(t.get("withdrawn", 0) or 0))
        charge = Decimal(str(t.get("charge", 0) or 0))
        running += paid_in
        running -= (withdrawn + charge)

        narration_text = t.get("narration", "")
        words = narration_text.split()
        wrapped_lines = [" ".join(words[j:j + 4]) for j in range(0, len(words), 4)]
        narration_para = Paragraph("<br/>".join(wrapped_lines), wrap_style)

        data.append([
            t["timestamp"].strftime("%Y-%m-%d %H:%M"),
            t.get("type", ""),
            narration_para,
            t.get("reference", ""),
            t.get("counterparty", ""),
            f"KES {paid_in:,.2f}" if paid_in else "",
            f"KES {withdrawn:,.2f}" if withdrawn else "",
            f"KES {charge:,.2f}" if charge else "",
            f"KES {running:,.2f}",
        ])

    # Transaction table (9 columns, weighted)
    transaction_table = Table(
        data, repeatRows=1,
        colWidths=[
            usable_width * 0.1,   # Date
            usable_width * 0.1,   # Type
            usable_width * 0.2,   # Narration
            usable_width * 0.1,   # Reference
            usable_width * 0.15,  # Counterparty
            usable_width * 0.075, # Paid In
            usable_width * 0.075, # Withdrawn
            usable_width * 0.075, # Charge
            usable_width * 0.125  # Balance
        ]
    )

    table_style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), faint_green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (4, -1), "LEFT"),
        ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("VALIGN", (0, 1), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]

    for row_idx in range(1, len(data)):
        if data[row_idx][5]:
            table_style_commands.append(("FONTNAME", (5, row_idx), (5, row_idx), "Helvetica-Bold"))
        table_style_commands.append(("FONTNAME", (8, row_idx), (8, row_idx), "Helvetica-Bold"))

    transaction_table.setStyle(TableStyle(table_style_commands))
    elements.append(transaction_table)

    elements.append(Spacer(1, 20))
    footer_para = Paragraph(
        f"<b>Generated on:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"<b>Page 1 of 1</b> | "
        f"<b>Mchango Hub Digital Services</b>",
        ParagraphStyle(
            name="Footer",
            fontSize=8,
            alignment=1,
            textColor=colors.black,
            fontName="Helvetica"
        )
    )

    footer_table = Table([[footer_para]], colWidths=[usable_width])
    footer_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    return file_path
