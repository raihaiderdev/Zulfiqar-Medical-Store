"""
PDF generation for invoices and reports (Phase 1 §26). Produces an A4-
sized PDF; a thermal-receipt-width variant would use the same data with
a narrower page size, which is a UI-layer choice (Settings > Printer)
left for the Phase 8+ UI to wire up rather than duplicated here.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

from app.config.settings import settings


def render_invoice_pdf(sale_detail: dict, destination: Path, pharmacy_name: str = "Pharmacy") -> Path:
    """`sale_detail` is the dict shape returned by sales_service.get_sale_detail()."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(destination), pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    story = [
        Paragraph(pharmacy_name, styles["Title"]),
        Paragraph(f"Invoice: {sale_detail['invoice_number']}", styles["Heading2"]),
        Paragraph(f"Date: {sale_detail['date']}", styles["Normal"]),
        Spacer(1, 8),
    ]

    table_data = [["Medicine", "Batch", "Qty", "Unit Price", "Discount", "Line Total"]]
    for item in sale_detail["items"]:
        table_data.append([
            item["medicine_name"], item["batch_number"], str(item["quantity"]),
            f"{settings.currency} {item['unit_price']:.2f}",
            f"{settings.currency} {item['line_discount']:.2f}",
            f"{settings.currency} {item['line_total']:.2f}",
        ])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    summary_rows = [
        ["Subtotal", f"{settings.currency} {sale_detail['subtotal']:.2f}"],
        ["Discount", f"{settings.currency} {sale_detail['discount_total']:.2f}"],
        ["Total", f"{settings.currency} {sale_detail['total']:.2f}"],
        ["Amount Paid", f"{settings.currency} {sale_detail['amount_paid']:.2f}"],
        ["Change Due", f"{settings.currency} {sale_detail['change_due']:.2f}"],
    ]
    summary_table = Table(summary_rows, colWidths=[100 * mm, 40 * mm])
    summary_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 10)]))
    story.append(summary_table)

    doc.build(story)
    return destination


def render_tabular_report_pdf(title: str, headers: list[str], rows: list[list[str]], destination: Path) -> Path:
    """Generic printable report (stock, expiry, sales list, etc.) — one
    title, one table. Used for the "printable" report types in Phase 1 §26
    that don't need an invoice's specific layout."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(destination), pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]

    table = Table([headers] + rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    doc.build(story)
    return destination
