"""Generate professional submission PDF for Composio AI Product Ops assignment.
Includes live links, pattern findings, verification metrics, and system architecture diagram.
"""
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable, PageBreak

BASE = Path("C:/Users/Ansh/Downloads/composio-research-agent/composio-research-agent")
PDF_PATH = BASE / "Composio_TakeHome_Submission_Ansh_Final.pdf"

doc = SimpleDocTemplate(
    str(PDF_PATH),
    pagesize=letter,
    rightMargin=36,
    leftMargin=36,
    topMargin=36,
    bottomMargin=36
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    "TitleStyle",
    parent=styles["Heading1"],
    fontSize=18,
    leading=22,
    textColor=colors.HexColor("#1E293B"),
    spaceAfter=3
)
subtitle_style = ParagraphStyle(
    "SubTitleStyle",
    parent=styles["Normal"],
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#64748B"),
    spaceAfter=8
)
h2_style = ParagraphStyle(
    "H2Style",
    parent=styles["Heading2"],
    fontSize=12,
    leading=16,
    textColor=colors.HexColor("#4C6EF5"),
    spaceBefore=6,
    spaceAfter=4
)
body_style = ParagraphStyle(
    "BodyStyle",
    parent=styles["Normal"],
    fontSize=8.5,
    leading=12,
    textColor=colors.HexColor("#1E293B"),
    spaceAfter=4
)
link_style = ParagraphStyle(
    "LinkStyle",
    parent=styles["Normal"],
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#2563EB"),
    spaceAfter=2
)

story = []

# Title & Metadata
story.append(Paragraph("<b>Composio AI Product Ops &mdash; 100-App Case Study Submission</b>", title_style))
story.append(Paragraph("<b>Candidate:</b> Ansh &nbsp;|&nbsp; <b>Time:</b> < 8 Hours &nbsp;|&nbsp; <b>Deliverables:</b> Live Case Study, GitHub Repo &amp; System Architecture", subtitle_style))
story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#4C6EF5"), spaceAfter=8))

# Deliverables / Links Box
links_data = [
    [Paragraph("<b>DELIVERABLE</b>", body_style), Paragraph("<b>LIVE LINK / ACCESS</b>", body_style)],
    [Paragraph("<b>Live Interactive Case Study</b>", body_style), Paragraph('<font color="#2563EB"><u>https://anshdarji12.github.io/Composio-AI-Product-Ops-Intern-assessment/</u></font>', link_style)],
    [Paragraph("<b>GitHub Source Repository</b>", body_style), Paragraph('<font color="#2563EB"><u>https://github.com/AnshDarji12/Composio-AI-Product-Ops-Intern-assessment</u></font>', link_style)],
]
t_links = Table(links_data, colWidths=[170, 370])
t_links.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#EEF2FF")),
    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#C7D2FE")),
    ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E0E7FF")),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(t_links)
story.append(Spacer(1, 8))

# Section 1: Executive Findings
story.append(Paragraph("<b>1. Headline Pattern Analysis Across 100 Apps</b>", h2_style))
metrics_data = [
    [Paragraph("<b>Total Apps Analyzed</b><br/><font size='13' color='#4C6EF5'><b>100</b></font><br/>Across 10 Categories", body_style),
     Paragraph("<b>Developer Self-Serve</b><br/><font size='13' color='#10B981'><b>78.3%</b></font><br/>Instant API Access", body_style),
     Paragraph("<b>Official MCP Servers</b><br/><font size='13' color='#F59E0B'><b>40</b></font><br/>Vendor Supported", body_style),
     Paragraph("<b>Composio Immediate Wins</b><br/><font size='13' color='#10B981'><b>51</b></font><br/>Ready for Toolkits", body_style)]
]
t_metrics = Table(metrics_data, colWidths=[135, 135, 135, 135])
t_metrics.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#E2E8F0")),
    ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(t_metrics)
story.append(Spacer(1, 6))

insights_text = (
    "<b>Key Insights:</b><br/>"
    "&bull; <b>Auth Patterns:</b> API Key (54%) and Bearer / OAuth 2.0 (46%) dominate. Financial/CRM apps enforce OAuth2 with webhook HMAC verification.<br/>"
    "&bull; <b>Access Barriers:</b> 78.3% are self-serve. Enterprise-gated apps (DealCloud, PitchBook) require sales outreach.<br/>"
    "&bull; <b>Composio Wedge:</b> 42 apps already integrated in Composio. <b>51 apps are immediate candidates</b> with public self-serve APIs where no official MCP exists."
)
story.append(Paragraph(insights_text, body_style))
story.append(Spacer(1, 4))

# Section 2: Verification & Accuracy
story.append(Paragraph("<b>2. Multi-Layer Verification &amp; Accuracy Methodology</b>", h2_style))
story.append(Paragraph(
    "&bull; <b>Adversarial Verifier LLM:</b> Challenges every extracted claim against fetched documentation URLs and records disputes.<br/>"
    "&bull; <b>Live Web-Fetch Verification:</b> Direct HTTP verification on live vendor docs (7 PASS, 3 bot-protected 403s honestly documented).<br/>"
    "&bull; <b>Human Audit Sample:</b> 20 apps (80 fields) cross-checked against ground truth docs; 11 honest misses transparently logged.<br/>"
    "&bull; <b>Tamper-Evident Audit Chain:</b> <code>verify_audit.py</code> validates 2,654 SHA-256 hash-chained records with 0 breaks.",
    body_style
))
story.append(Spacer(1, 6))

# Visual Charts
chart1 = BASE / "data" / "charts" / "auth-mix.png"
chart2 = BASE / "data" / "charts" / "composio-status.png"
if chart1.exists() and chart2.exists():
    img_data = [[
        Image(str(chart1), width=265, height=125),
        Image(str(chart2), width=265, height=125)
    ]]
    t_img = Table(img_data, colWidths=[270, 270])
    t_img.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(t_img)

# PAGE BREAK FOR ARCHITECTURE DIAGRAM
story.append(PageBreak())

# Page 2: System Architecture Diagram
story.append(Paragraph("<b>3. Research Agent Architecture &mdash; End-to-End Pipeline</b>", title_style))
story.append(Paragraph("Governed multi-stage pipeline: Search &rarr; Governed Fetch &rarr; Extraction &rarr; Confidence Gate &rarr; Adversarial Verifier &rarr; Canonical Store", subtitle_style))
story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#4C6EF5"), spaceAfter=10))

arch_img_path = BASE / "data" / "charts" / "architecture_diagram.jpg"
if arch_img_path.exists():
    # Fit nicely on letter page: 540 width x 580 height
    story.append(Image(str(arch_img_path), width=530, height=620))

doc.build(story)
print(f"Generated PDF successfully at: {PDF_PATH} ({PDF_PATH.stat().st_size} bytes)")
