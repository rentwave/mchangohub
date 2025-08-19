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


class PledgeNumberedCanvas:
    """Custom canvas to add page numbers and footers for pledge statements"""

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

        # Draw footer text - FIXED: Use drawString with manual centering
        self.canvas.setFillColor(colors.black)
        self.canvas.setFont("Helvetica", 8)

        # Calculate center position manually
        text_width = self.canvas.stringWidth(footer_text, "Helvetica", 8)
        center_x = page_width / 2 - text_width / 2

        self.canvas.drawString(
            center_x,
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

            # Header text - FIXED: Use drawString with manual centering
            self.canvas.setFillColor(colors.black)

            # Main header
            header_main = f"MCHANGO HUB PLEDGE SUMMARY - {self.contribution_name}"
            self.canvas.setFont("Helvetica-Bold", 12)
            main_text_width = self.canvas.stringWidth(header_main, "Helvetica-Bold", 12)
            main_center_x = page_width / 2 - main_text_width / 2

            self.canvas.drawString(
                main_center_x,
                page_height - self.doc.topMargin + 20,
                header_main
            )

            # Sub header
            header_sub = f"Report Period: {self.period_start.strftime('%Y-%m-%d')} to {self.period_end.strftime('%Y-%m-%d')}"
            self.canvas.setFont("Helvetica", 9)
            sub_text_width = self.canvas.stringWidth(header_sub, "Helvetica", 9)
            sub_center_x = page_width / 2 - sub_text_width / 2

            self.canvas.drawString(
                sub_center_x,
                page_height - self.doc.topMargin + 5,
                header_sub
            )


def on_pledge_first_page(canvas, doc, contribution_name: str, period_start: datetime, period_end: datetime):
    """First page callback for pledge statement"""
    numbered_canvas = PledgeNumberedCanvas(canvas, doc, contribution_name, period_start, period_end)
    numbered_canvas.draw_footer()


def on_pledge_later_pages(canvas, doc, contribution_name: str, period_start: datetime, period_end: datetime):
    """Later pages callback for pledge statement"""
    numbered_canvas = PledgeNumberedCanvas(canvas, doc, contribution_name, period_start, period_end)
    numbered_canvas.draw_header()
    numbered_canvas.draw_footer()


def generate_pledge_summary_pdf(
        pledges: List[Dict],
        contribution_name: str,
        period_start: datetime,
        period_end: datetime,
        filename: Optional[str] = None,
        pledges_per_page: int = 20,
) -> str:
    """
    Generate a pledge summary PDF with page breaks and consistent footers.

    Args:
        pledges: list of dicts with keys:
            - pledger_name: str
            - pledger_contact: str
            - amount: Decimal/float
            - planned_clear_date: datetime/date
            - contribution: str (contribution name)
            - status: str/object (pledge status)
            - total_paid: Decimal/float (optional - calculated amount paid)
            - balance: Decimal/float (optional - calculated remaining balance)
        contribution_name: name of the contribution
        period_start: start date for the report period
        period_end: end date for the report period
        filename: optional filename for the PDF
        pledges_per_page: number of pledges per page (default: 20)
    """

    temp_dir = os.path.join(settings.BASE_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    safe_name = contribution_name.replace(" ", "_").lower()
    if filename is None:
        filename = f"pledge_summary_{safe_name}.pdf"

    file_path = os.path.join(temp_dir, filename)

    # Calculate summary statistics
    total_pledged = sum(Decimal(str(p.get("amount", 0) or 0)) for p in pledges)
    total_paid = sum(Decimal(str(p.get("total_paid", 0) or 0)) for p in pledges)
    total_balance = sum(Decimal(str(p.get("balance", 0) or 0)) for p in pledges)
    total_pledgers = len(pledges)

    # Count by status
    status_counts = {}
    for pledge in pledges:
        status = str(pledge.get("status", "Unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

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
        onPage=lambda canvas, doc: on_pledge_first_page(canvas, doc, contribution_name, period_start, period_end)
    )

    later_page_template = PageTemplate(
        id='later',
        frames=later_frame,
        onPage=lambda canvas, doc: on_pledge_later_pages(canvas, doc, contribution_name, period_start, period_end)
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

    heading_para = Paragraph("<b>MCHANGO HUB PLEDGE SUMMARY</b>", main_heading)
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
    summary_info = [
        ["Contribution:", contribution_name, "Report Date:", datetime.now().strftime("%Y-%m-%d")],
        ["Total Pledgers:", str(total_pledgers), "Report Period:",
         f"{period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}"],
        ["Total Pledged:", f"KES {total_pledged:,.2f}", "Total Paid:", f"KES {total_paid:,.2f}"],
        ["Total Balance:", f"KES {total_balance:,.2f}", "Collection Rate:",
         f"{(total_paid / total_pledged * 100):,.1f}%" if total_pledged > 0 else "0.0%"],
    ]

    summary_table = Table(
        summary_info,
        colWidths=[usable_width * 0.2, usable_width * 0.3, usable_width * 0.2, usable_width * 0.3]
    )
    summary_table.setStyle(TableStyle([
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

    # Status breakdown (if more than one status exists)
    if len(status_counts) > 1:
        status_data = [["Status Breakdown", "", "", ""]]
        status_items = list(status_counts.items())

        # Arrange status items in pairs for better layout
        for i in range(0, len(status_items), 2):
            left_status, left_count = status_items[i]
            if i + 1 < len(status_items):
                right_status, right_count = status_items[i + 1]
                status_data.append([f"{left_status}:", str(left_count), f"{right_status}:", str(right_count)])
            else:
                status_data.append([f"{left_status}:", str(left_count), "", ""])

        status_table = Table(status_data,
                             colWidths=[usable_width * 0.2, usable_width * 0.3, usable_width * 0.2, usable_width * 0.3])
        status_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), faint_green),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("ALIGN", (3, 0), (3, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
        ]))

        # Keep summary and status together
        elements.append(KeepTogether([
            summary_table,
            Spacer(1, 15),
            status_table,
            Spacer(1, 20)
        ]))
    else:
        # Keep summary alone if only one status
        elements.append(KeepTogether([summary_table, Spacer(1, 20)]))

    # Prepare pledge data
    pledge_data = [["Pledger Name", "Contact", "Amount", "Planned Clear Date", "Status", "Total Paid", "Balance"]]

    # Process pledges
    for pledge in pledges:
        pledger_name = str(pledge.get("pledger_name", ""))
        pledger_contact = str(pledge.get("pledger_contact", "")) or "—"
        amount = Decimal(str(pledge.get("amount", 0) or 0))
        planned_clear_date = pledge.get("planned_clear_date")
        status = str(pledge.get("status", "Unknown"))
        total_paid = Decimal(str(pledge.get("total_paid", 0) or 0))
        balance = Decimal(str(pledge.get("balance", 0) or 0))

        # Format planned clear date
        if planned_clear_date:
            if hasattr(planned_clear_date, 'strftime'):
                date_str = planned_clear_date.strftime("%Y-%m-%d")
            else:
                date_str = str(planned_clear_date)
        else:
            date_str = "Not Set"

        pledge_data.append([
            pledger_name,
            pledger_contact,
            f"KES {amount:,.2f}",
            date_str,
            status,
            f"KES {total_paid:,.2f}" if total_paid > 0 else "—",
            f"KES {balance:,.2f}" if balance > 0 else "—",
        ])

    # Split pledges into pages
    header = [pledge_data[0]]  # Table header
    pledge_rows = pledge_data[1:]  # All pledge rows

    # Calculate how many pledges fit on first page vs subsequent pages
    first_page_pledges = max(1, pledges_per_page - 3)  # Account for header sections
    later_page_pledges = pledges_per_page

    # Process first page of pledges
    if pledge_rows:
        first_page_data = header + pledge_rows[:first_page_pledges]
        first_table = create_pledge_table(first_page_data, usable_width)
        elements.append(first_table)

        remaining_pledges = pledge_rows[first_page_pledges:]

        # Process remaining pledges in chunks
        while remaining_pledges:
            # Add page break and switch to later page template
            elements.append(PageBreak())
            elements.append(NextPageTemplate('later'))

            # Get next chunk
            chunk = remaining_pledges[:later_page_pledges]
            remaining_pledges = remaining_pledges[later_page_pledges:]

            # Create table for this chunk
            chunk_data = header + chunk
            chunk_table = create_pledge_table(chunk_data, usable_width)
            elements.append(chunk_table)

    # Build the document
    doc.build(elements)
    return file_path


def create_pledge_table(data, usable_width):
    """Create a consistently styled pledge table"""

    pledge_table = Table(
        data,
        repeatRows=1,
        colWidths=[
            usable_width * 0.20,  # Pledger Name
            usable_width * 0.15,  # Contact
            usable_width * 0.12,  # Amount
            usable_width * 0.12,  # Planned Clear Date
            usable_width * 0.12,  # Status
            usable_width * 0.12,  # Total Paid
            usable_width * 0.17,  # Balance
        ]
    )

    faint_green = colors.HexColor("#F0F9F0")

    # Helper function to get status color
    def get_status_color(status_text):
        status_lower = status_text.lower()
        if 'clear' in status_lower or 'paid' in status_lower:
            return colors.HexColor("#28a745")  # Green
        elif 'partial' in status_lower:
            return colors.HexColor("#ffc107")  # Yellow
        elif 'pending' in status_lower:
            return colors.HexColor("#dc3545")  # Red
        elif 'overdue' in status_lower:
            return colors.HexColor("#fd7e14")  # Orange
        else:
            return colors.black

    table_style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), faint_green),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),  # Name and Contact left-aligned
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),  # Amount columns right-aligned
        ("ALIGN", (3, 0), (4, -1), "CENTER"),  # Date and Status centered
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    # Style individual rows
    for row_idx in range(1, len(data)):
        # Color code the status
        if len(data[row_idx]) > 4:
            status = data[row_idx][4]
            status_color = get_status_color(status)
            table_style_commands.append(("TEXTCOLOR", (4, row_idx), (4, row_idx), status_color))
            table_style_commands.append(("FONTNAME", (4, row_idx), (4, row_idx), "Helvetica-Bold"))

        # Bold and color the amount columns
        if len(data[row_idx]) > 2:  # Amount column
            table_style_commands.append(("FONTNAME", (2, row_idx), (2, row_idx), "Helvetica-Bold"))

        if len(data[row_idx]) > 5 and data[row_idx][5] != "—":  # Total Paid column
            table_style_commands.append(("FONTNAME", (5, row_idx), (5, row_idx), "Helvetica-Bold"))
            table_style_commands.append(
                ("TEXTCOLOR", (5, row_idx), (5, row_idx), colors.HexColor("#28a745")))  # Green for payments

        if len(data[row_idx]) > 6 and data[row_idx][6] != "—":  # Balance column
            table_style_commands.append(("FONTNAME", (6, row_idx), (6, row_idx), "Helvetica-Bold"))
            # Color based on balance amount (you could make this dynamic)

        # Alternate row colors for better readability
        if row_idx % 2 == 0:
            table_style_commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#f8f9fa")))

    pledge_table.setStyle(TableStyle(table_style_commands))
    return pledge_table