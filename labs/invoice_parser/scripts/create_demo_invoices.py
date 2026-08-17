"""Generate the permanent synthetic supplier-lookup invoice demos."""

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DEMO_DIRECTORY = Path("apps/labs/static/demos")
NAVY = HexColor("#1A4164")
BLUE = HexColor("#286291")
MUTED = HexColor("#5B6B77")
BORDER = HexColor("#D8D4CB")
CANVAS = HexColor("#F6F2EF")
WHITE = HexColor("#FFFFFF")


@dataclass(frozen=True, slots=True)
class DemoInvoice:
    """Content for one synthetic public invoice."""

    filename: str
    invoice_number: str
    seller: str
    seller_address: str
    buyer: str
    buyer_address: str
    issue_date: str
    due_date: str
    purchase_order: str
    terms: str
    line_items: tuple[tuple[str, str, str, str], ...]
    subtotal: str
    tax: str
    total: str
    note: str


INVOICES = (
    DemoInvoice(
        filename="invoice-supplier-match.pdf",
        invoice_number="PIS-3175",
        seller="Pacific Industrial Supply",
        seller_address="8200 Fictional Way, Portland, OR 97205",
        buyer="Summit Field Operations LLC",
        buyer_address="1150 Market Center Boulevard, Houston, TX 77002",
        issue_date="August 16, 2026",
        due_date="September 15, 2026",
        purchase_order="SFO-4410",
        terms="Net 30",
        line_items=(
            ("Safety harness kit", "8", "$245.00", "$1,960.00"),
            ("ANSI hard hat - vented", "12", "$42.50", "$510.00"),
            ("High-visibility field vest", "12", "$31.25", "$375.00"),
        ),
        subtotal="$2,845.00",
        tax="$237.71",
        total="$3,082.71",
        note="Please reference purchase order SFO-4410 with payment.",
    ),
    DemoInvoice(
        filename="invoice-supplier-review.pdf",
        invoice_number="PI-8841",
        seller="Pacific Industrial",
        seller_address="1400 Example Commerce Drive, Vancouver, WA 98660",
        buyer="Apex Field Systems Inc.",
        buyer_address="600 Demo Park Road, Dallas, TX 75201",
        issue_date="August 16, 2026",
        due_date="September 15, 2026",
        purchase_order="AFS-1178",
        terms="Net 30",
        line_items=(
            ("Portable equipment enclosure", "2", "$1,250.00", "$2,500.00"),
            ("Weatherproof cable assembly", "6", "$185.00", "$1,110.00"),
        ),
        subtotal="$3,610.00",
        tax="$297.83",
        total="$3,907.83",
        note="Please reference invoice PI-8841 with payment.",
    ),
)


def build_invoice(*, invoice: DemoInvoice) -> None:
    """Write one branded, one-page synthetic invoice PDF."""
    styles = getSampleStyleSheet()
    label = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=MUTED,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=NAVY,
    )
    title = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Times-Roman",
        fontSize=34,
        leading=38,
        textColor=WHITE,
    )
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    document = SimpleDocTemplate(
        str(DEMO_DIRECTORY / invoice.filename),
        pagesize=LETTER,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"Synthetic invoice {invoice.invoice_number}",
        author="Newman Labs",
    )
    header = Table(
        [
            [Paragraph("NEWMAN LABS / PUBLIC DEMO", label), Paragraph(invoice.invoice_number, right)],
            [Paragraph("Invoice", title), Paragraph("SYNTHETIC DEMO - NOT FOR PAYMENT", right)],
        ],
        colWidths=[4.6 * inch, 2.3 * inch],
        rowHeights=[0.35 * inch, 0.85 * inch],
    )
    header.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 18),
            ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ])
    )

    facts = Table(
        [
            [
                Paragraph("ISSUE DATE", label),
                Paragraph("DUE DATE", label),
                Paragraph("PURCHASE ORDER", label),
                Paragraph("TERMS", label),
            ],
            [invoice.issue_date, invoice.due_date, invoice.purchase_order, invoice.terms],
        ],
        colWidths=[1.72 * inch] * 4,
    )
    facts.setStyle(
        TableStyle([
            ("TEXTCOLOR", (0, 1), (-1, 1), NAVY),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, 1), 9),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ])
    )
    parties = Table(
        [
            [Paragraph("FROM", label), Paragraph("BILL TO", label)],
            [
                Paragraph(f"<b>{invoice.seller}</b><br/>{invoice.seller_address}", body),
                Paragraph(f"<b>{invoice.buyer}</b><br/>{invoice.buyer_address}", body),
            ],
        ],
        colWidths=[3.45 * inch, 3.45 * inch],
    )
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    line_data = [["DESCRIPTION", "QTY", "RATE", "AMOUNT"], *invoice.line_items]
    lines = Table(line_data, colWidths=[4.25 * inch, 0.65 * inch, 1 * inch, 1 * inch], repeatRows=1)
    lines.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("TEXTCOLOR", (0, 1), (-1, -1), NAVY),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ])
    )
    totals = Table(
        [["Subtotal", invoice.subtotal], ["Sales tax", invoice.tax], ["Total due", invoice.total]],
        colWidths=[1.2 * inch, 1.2 * inch],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle([
            ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
            ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
            ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (0, 2), (-1, 2), 1, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])
    )
    note = Table(
        [[Paragraph("NOTE", label)], [Paragraph(invoice.note, body)]],
        colWidths=[6.9 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), WHITE),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]),
    )

    story = [
        header,
        Spacer(1, 0.35 * inch),
        facts,
        HRFlowable(width="100%", thickness=0.6, color=BORDER),
        Spacer(1, 0.22 * inch),
        parties,
        Spacer(1, 0.35 * inch),
        lines,
        Spacer(1, 0.18 * inch),
        totals,
        Spacer(1, 0.3 * inch),
        note,
        Spacer(1, 0.18 * inch),
        Paragraph("All companies, addresses, contacts, and values in this invoice are fictional.", label),
    ]

    def paint_page(canvas: Canvas, _document: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setFillColor(CANVAS)
        canvas.rect(0, 0, LETTER[0], LETTER[1], fill=1, stroke=0)
        canvas.setFillColor(BLUE)
        canvas.rect(0, LETTER[1] - 4, LETTER[0], 4, fill=1, stroke=0)
        canvas.restoreState()

    document.build(story, onFirstPage=paint_page)


def main() -> None:
    """Regenerate the two permanent supplier-lookup demo PDFs."""
    DEMO_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for invoice in INVOICES:
        build_invoice(invoice=invoice)


if __name__ == "__main__":
    main()
