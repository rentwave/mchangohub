import os

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
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
    Generate an MPESA-like statement as PDF.
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
        filename = f"Mchango_Hub_Statement_{safe_msisdn}_{period_start:%Y%m%d}_to_{period_end:%Y%m%d}.pdf"
    
    file_path = os.path.join(temp_dir, filename)
    txs = sorted(transactions, key=lambda x: x["timestamp"])
    running = opening_balance
    total_in = sum(Decimal(str(t.get("paid_in", 0) or 0)) for t in txs)
    total_out = sum(Decimal(str(t.get("withdrawn", 0) or 0)) for t in txs)
    total_charges = sum(Decimal(str(t.get("charge", 0) or 0)) for t in txs)
    net_movement = total_in - (total_out + total_charges)
    closing_balance = opening_balance + net_movement

    doc = SimpleDocTemplate(
        filename,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    heading = ParagraphStyle(name="Heading", fontSize=14, leading=16, alignment=1, spaceAfter=10, bold=True)

    elements = []

    elements.append(Paragraph("<b>MCHANGO HUB STATEMENT</b>", heading))
    elements.append(Spacer(1, 12))

    acc_info = [
        ["Account Name:", customer_name, "MSISDN:", msisdn],
        ["Account No:", account_number or "—", "Period From:", period_start.strftime("%Y-%m-%d")],
        ["", "", "Period To:", period_end.strftime("%Y-%m-%d")],
        ["Opening Balance:", f"{opening_balance:,.2f}", "Closing Balance:", f"{closing_balance:,.2f}"],
    ]
    table = Table(acc_info, colWidths=[3*cm, 6*cm, 3*cm, 6*cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (1,0), (1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))

    summary_data = [
        ["Total In", f"{total_in:,.2f}", "Total Out", f"{total_out:,.2f}", "Total Charges", f"{total_charges:,.2f}", "Net Movement", f"{net_movement:,.2f}"],
    ]
    table = Table(summary_data, colWidths=[3*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E6F0FF")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOX", (0,0), (-1,-1), 0.25, colors.grey),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.grey),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))
    data = [["Date/Time", "Type", "Narration", "Reference", "Counterparty", "Paid In", "Withdrawn", "Charge", "Balance"]]
    for t in txs:
        paid_in = Decimal(str(t.get("paid_in", 0) or 0))
        withdrawn = Decimal(str(t.get("withdrawn", 0) or 0))
        charge = Decimal(str(t.get("charge", 0) or 0))
        running += paid_in
        running -= (withdrawn + charge)

        data.append([
            t["timestamp"].strftime("%Y-%m-%d %H:%M"),
            t.get("type", ""),
            t.get("narration", ""),
            t.get("reference", ""),
            t.get("counterparty", ""),
            f"{paid_in:,.2f}" if paid_in else "",
            f"{withdrawn:,.2f}" if withdrawn else "",
            f"{charge:,.2f}" if charge else "",
            f"{running:,.2f}",
        ])
    table = Table(data, repeatRows=1, colWidths=[3*cm, 3*cm, 5*cm, 3*cm, 4*cm, 2.5*cm, 2.5*cm, 2.5*cm, 3*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E6F0FF")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("ALIGN", (0,0), (4,-1), "LEFT"),
        ("ALIGN", (5,0), (-1,-1), "RIGHT"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("BOX", (0,0), (-1,-1), 0.25, colors.grey),
    ]))
    elements.append(table)
    doc.build(elements)
    return file_path

