"""Stage 5: PDF Report Generator

Generates professional PDF case reports using ReportLab.

The PDF includes:
- Cover page with case details
- Borrower profile
- Document status checklist
- Strengths & risk analysis
- Lender match table with color coding
- Submission recommendations
"""

import logging
from typing import Optional
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, Frame, PageTemplate
)
from reportlab.pdfgen import canvas

from app.schemas.shared import CaseReportData, EligibilityResult
from app.core.enums import HardFilterStatus, ApprovalProbability, DocumentType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# PDF STYLES
# ═══════════════════════════════════════════════════════════════

def get_custom_styles():
    """Create custom paragraph styles for the PDF."""
    styles = getSampleStyleSheet()

    # Title style
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    ))

    # Heading1
    styles.add(ParagraphStyle(
        name='CustomHeading1',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    ))

    # Heading2
    styles.add(ParagraphStyle(
        name='CustomHeading2',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=10,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    ))

    # Body text
    styles.add(ParagraphStyle(
        name='CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        leading=14
    ))

    # Small text
    styles.add(ParagraphStyle(
        name='CustomSmall',
        parent=styles['BodyText'],
        fontSize=8,
        textColor=colors.HexColor('#666666'),
        spaceAfter=4
    ))

    return styles


# ═══════════════════════════════════════════════════════════════
# PAGE HEADER/FOOTER
# ═══════════════════════════════════════════════════════════════

class NumberedCanvas(canvas.Canvas):
    """Custom canvas to add page numbers and header/footer."""

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        """Add page number at bottom."""
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.grey)
        page_num = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 1*cm, 1*cm, page_num)

        # Footer text
        self.drawString(1*cm, 1*cm, "DSA Case OS - Confidential")


# ═══════════════════════════════════════════════════════════════
# PDF GENERATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def generate_pdf_report(report_data: CaseReportData) -> bytes:
    """Generate PDF report from CaseReportData.

    Args:
        report_data: The assembled case report data

    Returns:
        PDF bytes
    """
    logger.info(f"Generating PDF report for case {report_data.case_id}")

    # Create BytesIO buffer
    buffer = BytesIO()

    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2.5*cm,
        title=f"Case Report - {report_data.case_id}"
    )

    # Get styles
    styles = get_custom_styles()

    # Build story (content)
    story = []

    # Page 1: Cover
    story.extend(build_cover_page(report_data, styles))
    story.append(PageBreak())

    # Page 2: Borrower Profile
    story.extend(build_borrower_profile_page(report_data, styles))
    story.append(PageBreak())

    # Page 3: Document Status
    story.extend(build_document_status_page(report_data, styles))
    story.append(PageBreak())

    # Page 4: Strengths & Risks
    story.extend(build_strengths_risks_page(report_data, styles))
    story.append(PageBreak())

    # Page 5-6: Lender Match Table
    story.extend(build_lender_matches_page(report_data, styles))

    # Page 7: Recommendations (if there's space, otherwise new page)
    if len(report_data.lender_matches) > 15:
        story.append(PageBreak())

    story.extend(build_recommendations_page(report_data, styles))

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)

    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(f"PDF generated successfully ({len(pdf_bytes)} bytes)")

    return pdf_bytes


def build_cover_page(report_data: CaseReportData, styles):
    """Build cover page elements."""
    elements = []

    # Spacer from top
    elements.append(Spacer(1, 2*inch))

    # Title
    elements.append(Paragraph("Case Intelligence Report", styles['CustomTitle']))
    elements.append(Spacer(1, 0.3*inch))

    # Case ID
    case_id_text = f"<b>Case ID:</b> {report_data.case_id}"
    elements.append(Paragraph(case_id_text, styles['CustomHeading2']))
    elements.append(Spacer(1, 0.1*inch))

    # Date
    date_text = f"<b>Generated:</b> {datetime.now().strftime('%d %B %Y, %I:%M %p')}"
    elements.append(Paragraph(date_text, styles['CustomBody']))
    elements.append(Spacer(1, 0.3*inch))

    # Borrower basic info
    borrower = report_data.borrower_profile

    info_data = [
        ["Borrower Name", borrower.full_name or "N/A"],
        ["Entity Type", borrower.entity_type.value if borrower.entity_type else "N/A"],
        ["Business Vintage", f"{borrower.business_vintage_years:.1f} years" if borrower.business_vintage_years else "N/A"],
        ["Industry", borrower.industry_type or "N/A"],
    ]

    info_table = Table(info_data, colWidths=[2.5*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))

    elements.append(info_table)
    elements.append(Spacer(1, 1*inch))

    # Footer branding
    branding = Paragraph(
        "<i>Prepared by <b>DSA Case OS</b></i><br/>Intelligent Lending Decision Support",
        ParagraphStyle(
            'BrandingStyle',
            parent=styles['CustomBody'],
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        )
    )
    elements.append(branding)

    return elements


def build_borrower_profile_page(report_data: CaseReportData, styles):
    """Build borrower profile page."""
    elements = []

    elements.append(Paragraph("Borrower Profile", styles['CustomHeading1']))
    elements.append(Spacer(1, 0.2*inch))

    borrower = report_data.borrower_profile

    # Profile table
    profile_data = [
        ["Field", "Value"],
        ["Full Name", borrower.full_name or "N/A"],
        ["PAN", borrower.pan_number or "Not provided"],
        ["Entity Type", borrower.entity_type.value if borrower.entity_type else "N/A"],
        ["Business Vintage", f"{borrower.business_vintage_years:.1f} years" if borrower.business_vintage_years else "N/A"],
        ["Industry", borrower.industry_type or "N/A"],
        ["Pincode", borrower.pincode or "N/A"],
        ["GSTIN", borrower.gstin or "Not registered"],
    ]

    profile_table = Table(profile_data, colWidths=[2.5*inch, 4*inch])
    profile_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
    ]))

    elements.append(profile_table)
    elements.append(Spacer(1, 0.3*inch))

    # Financial snapshot
    elements.append(Paragraph("Financial Snapshot", styles['CustomHeading2']))
    elements.append(Spacer(1, 0.1*inch))

    financial_data = [
        ["Metric", "Value"],
        ["Annual Turnover", f"₹{borrower.annual_turnover:.2f} Lakhs" if borrower.annual_turnover else "N/A"],
        ["CIBIL Score", str(borrower.cibil_score) if borrower.cibil_score else "N/A"],
        ["Avg Bank Balance", f"₹{borrower.avg_monthly_balance:,.0f}" if borrower.avg_monthly_balance else "N/A"],
        ["Monthly Credits (Avg)", f"₹{borrower.monthly_credit_avg:,.0f}" if borrower.monthly_credit_avg else "N/A"],
        ["EMI Outflow", f"₹{borrower.emi_outflow_monthly:,.0f}" if borrower.emi_outflow_monthly else "N/A"],
        ["Bounces (12M)", str(borrower.bounce_count_12m) if borrower.bounce_count_12m is not None else "N/A"],
        ["Cash Deposit Ratio", f"{borrower.cash_deposit_ratio*100:.1f}%" if borrower.cash_deposit_ratio else "N/A"],
    ]

    financial_table = Table(financial_data, colWidths=[2.5*inch, 4*inch])
    financial_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
    ]))

    elements.append(financial_table)

    return elements


def build_document_status_page(report_data: CaseReportData, styles):
    """Build document status checklist page."""
    elements = []

    elements.append(Paragraph("Document Checklist", styles['CustomHeading1']))
    elements.append(Spacer(1, 0.2*inch))

    checklist = report_data.checklist

    # Completeness bar
    completeness_text = f"<b>Document Completeness:</b> {checklist.completeness_score:.0f}%"
    elements.append(Paragraph(completeness_text, styles['CustomBody']))
    elements.append(Spacer(1, 0.1*inch))

    # Completeness progress bar (simple table)
    complete_width = int(checklist.completeness_score / 10)  # Out of 10 cells
    bar_data = [[''] * 10]
    bar_table = Table(bar_data, colWidths=[0.6*inch] * 10, rowHeights=[0.2*inch])

    bar_style = [
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]

    # Color the completed portion green
    if complete_width > 0:
        bar_style.append(('BACKGROUND', (0, 0), (complete_width - 1, 0), colors.HexColor('#4CAF50')))

    bar_table.setStyle(TableStyle(bar_style))
    elements.append(bar_table)
    elements.append(Spacer(1, 0.3*inch))

    # Documents table
    doc_data = [["Document Type", "Status"]]

    # Combine all document types
    all_docs = set(checklist.available + checklist.missing + checklist.optional_present)

    for doc_type in sorted(all_docs, key=lambda x: x.value):
        doc_name = doc_type.value.replace('_', ' ').title()

        if doc_type in checklist.available:
            status = "✓ Available"
            status_color = colors.HexColor('#4CAF50')
        else:
            status = "✗ Missing"
            status_color = colors.HexColor('#f44336')

        doc_data.append([doc_name, status])

    doc_table = Table(doc_data, colWidths=[3.5*inch, 2*inch])

    doc_table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]

    # Color status column based on availability
    for i, doc_type in enumerate(sorted(all_docs, key=lambda x: x.value), start=1):
        if doc_type in checklist.available:
            doc_table_style.append(('TEXTCOLOR', (1, i), (1, i), colors.HexColor('#4CAF50')))
        else:
            doc_table_style.append(('TEXTCOLOR', (1, i), (1, i), colors.HexColor('#f44336')))

    doc_table.setStyle(TableStyle(doc_table_style))
    elements.append(doc_table)

    # Unreadable files
    if checklist.unreadable:
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Unreadable Files:", styles['CustomHeading2']))
        elements.append(Spacer(1, 0.05*inch))

        for filename in checklist.unreadable:
            elements.append(Paragraph(f"• {filename}", styles['CustomSmall']))

    return elements


def build_strengths_risks_page(report_data: CaseReportData, styles):
    """Build strengths and risks analysis page."""
    elements = []

    # STRENGTHS section
    elements.append(Paragraph("Strengths", styles['CustomHeading1']))
    elements.append(Spacer(1, 0.1*inch))

    if report_data.strengths:
        strength_data = []
        for strength in report_data.strengths:
            strength_data.append([Paragraph(f"✓ {strength}", styles['CustomBody'])])

        strength_table = Table(strength_data, colWidths=[6.5*inch])
        strength_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E8F5E9')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1B5E20')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#A5D6A7')),
        ]))
        elements.append(strength_table)
    else:
        elements.append(Paragraph("<i>No significant strengths identified</i>", styles['CustomBody']))

    elements.append(Spacer(1, 0.3*inch))

    # RISK FLAGS section
    elements.append(Paragraph("Risk Flags", styles['CustomHeading1']))
    elements.append(Spacer(1, 0.1*inch))

    if report_data.risk_flags:
        risk_data = []
        for risk in report_data.risk_flags:
            risk_data.append([Paragraph(f"⚠ {risk}", styles['CustomBody'])])

        risk_table = Table(risk_data, colWidths=[6.5*inch])
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFEBEE')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#B71C1C')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#EF9A9A')),
        ]))
        elements.append(risk_table)
    else:
        elements.append(Paragraph("<i>No major risks identified</i>", styles['CustomBody']))

    elements.append(Spacer(1, 0.3*inch))

    # ADVISORY section
    if report_data.missing_data_advisory:
        elements.append(Paragraph("Missing Data Advisory", styles['CustomHeading2']))
        elements.append(Spacer(1, 0.1*inch))

        for advisory in report_data.missing_data_advisory:
            elements.append(Paragraph(f"• {advisory}", styles['CustomSmall']))

    return elements


def build_lender_matches_page(report_data: CaseReportData, styles):
    """Build lender match table page."""
    elements = []

    elements.append(Paragraph("Lender Match Analysis", styles['CustomHeading1']))
    elements.append(Spacer(1, 0.2*inch))

    # Summary stats
    passed_count = len([lm for lm in report_data.lender_matches if lm.hard_filter_status == HardFilterStatus.PASS])
    total_count = len(report_data.lender_matches)

    summary_text = f"<b>{passed_count}</b> out of <b>{total_count}</b> lenders passed eligibility criteria"
    elements.append(Paragraph(summary_text, styles['CustomBody']))
    elements.append(Spacer(1, 0.2*inch))

    # Lender table - show top 15 or all passed
    display_matches = [lm for lm in report_data.lender_matches if lm.hard_filter_status == HardFilterStatus.PASS][:15]

    if not display_matches:
        elements.append(Paragraph("<i>No lenders currently match this profile</i>", styles['CustomBody']))
        return elements

    # Build table data
    table_data = [["Rank", "Lender", "Product", "Score", "Probability", "Expected Ticket"]]

    for match in display_matches:
        rank = str(match.rank) if match.rank else "-"
        score = f"{match.eligibility_score:.0f}" if match.eligibility_score else "-"
        prob = match.approval_probability.value.upper() if match.approval_probability else "-"

        ticket = "-"
        if match.expected_ticket_min and match.expected_ticket_max:
            ticket = f"₹{match.expected_ticket_min:.1f}L - ₹{match.expected_ticket_max:.1f}L"

        table_data.append([
            rank,
            match.lender_name,
            match.product_name,
            score,
            prob,
            ticket
        ])

    # Create table
    lender_table = Table(
        table_data,
        colWidths=[0.6*inch, 2*inch, 1.2*inch, 0.8*inch, 1*inch, 1.9*inch]
    )

    # Base style
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]

    # Color rows based on probability
    for i, match in enumerate(display_matches, start=1):
        if match.approval_probability == ApprovalProbability.HIGH:
            table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#E8F5E9')))
        elif match.approval_probability == ApprovalProbability.MEDIUM:
            table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFF9C4')))
        else:
            table_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFEBEE')))

    lender_table.setStyle(TableStyle(table_style))
    elements.append(lender_table)

    # Legend
    elements.append(Spacer(1, 0.2*inch))
    legend_text = (
        "<b>Color Legend:</b> "
        '<font color="#1B5E20">■</font> High Probability &nbsp;&nbsp; '
        '<font color="#F57F17">■</font> Medium Probability &nbsp;&nbsp; '
        '<font color="#B71C1C">■</font> Low Probability'
    )
    elements.append(Paragraph(legend_text, styles['CustomSmall']))

    return elements


def build_recommendations_page(report_data: CaseReportData, styles):
    """Build recommendations page."""
    elements = []

    elements.append(Paragraph("Submission Strategy & Recommendations", styles['CustomHeading1']))
    elements.append(Spacer(1, 0.2*inch))

    # Submission strategy (already formatted as markdown-style)
    # Convert markdown bold to PDF bold (use regex to replace **text** with <b>text</b>)
    import re
    strategy_html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', report_data.submission_strategy)
    strategy_html = strategy_html.replace("\n\n", "<br/><br/>")
    strategy_html = strategy_html.replace("\n", "<br/>")

    elements.append(Paragraph(strategy_html, styles['CustomBody']))

    elements.append(Spacer(1, 0.3*inch))

    # Expected loan range
    if report_data.expected_loan_range:
        elements.append(Paragraph("Expected Loan Range", styles['CustomHeading2']))
        elements.append(Spacer(1, 0.05*inch))
        elements.append(Paragraph(report_data.expected_loan_range, styles['CustomBody']))

    return elements


# ═══════════════════════════════════════════════════════════════
# FILE MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def save_pdf_to_file(pdf_bytes: bytes, filepath: str) -> None:
    """Save PDF bytes to a file.

    Args:
        pdf_bytes: PDF content as bytes
        filepath: Path to save the PDF
    """
    with open(filepath, 'wb') as f:
        f.write(pdf_bytes)

    logger.info(f"PDF saved to {filepath}")
