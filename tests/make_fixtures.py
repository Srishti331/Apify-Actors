"""
make_fixtures.py
Generates the 5 test resumes in tests/fixtures/ (dev-only; needs reportlab).

    python tests/make_fixtures.py
"""

from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "fixtures"
UNICODE_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
W, H = LETTER


def _write_lines(c, x, y, lines, font="Helvetica", size=10, leading=14):
    for line in lines:
        if line.startswith("## "):
            c.setFont(font + "-Bold" if font == "Helvetica" else font, size + 2)
            c.drawString(x, y, line[3:])
        else:
            c.setFont(font, size)
            c.drawString(x, y, line)
        y -= leading
    return y


def two_column_pdf():
    """Sidebar (contacts/skills/education) on the left, experience on the right."""
    c = canvas.Canvas(str(OUT / "two_column.pdf"), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(W / 2, H - 60, "Priya Ramanathan")
    _write_lines(c, 40, H - 110, [
        "## Contact",
        "priya.r@gmail.com",
        "+91 98450 12345",
        "Bangalore, India",
        "linkedin.com/in/priyaram",
        "",
        "## Skills",
        "Python",
        "SQL",
        "Apache Spark",
        "Airflow",
        "AWS",
        "",
        "## Education",
        "B.E. Computer Science",
        "RV College of Engineering",
        "2016",
    ])
    c.line(205, H - 95, 205, 80)
    _write_lines(c, 225, H - 110, [
        "## Experience",
        "Senior Data Engineer - Flipkart",
        "Mar 2021 - Present",
        "Built streaming pipelines on Spark and Kafka.",
        "",
        "Data Engineer - Swiggy",
        "Jul 2018 - Apr 2021",
        "Owned the order-events warehouse in Redshift.",
        "",
        "Freelance Data Consultant - Self-employed",
        "Jan 2020 - Dec 2020",
        "Weekend analytics projects for two startups.",
        "",
        "Software Engineer - Infosys",
        "Aug 2016 - Jun 2018",
        "Java services for a banking client.",
    ])
    c.save()


def fresher_pdf():
    c = canvas.Canvas(str(OUT / "fresher.pdf"), pagesize=LETTER)
    _write_lines(c, 50, H - 60, [
        "## Rahul Verma",
        "rahul.verma2024@outlook.com | 98989-22331 | Pune, India",
        "",
        "## Objective",
        "Recent computer science graduate looking for an entry-level software developer role where I can",
        "apply my knowledge of web development and data structures in a collaborative team environment.",
        "",
        "## Education",
        "B.Tech Computer Science, Vishwakarma Institute of Technology, 2024",
        "Higher Secondary Certificate, Fergusson College, 2020",
        "",
        "## Skills",
        "Java, JavaScript, React, HTML, CSS, Git",
        "",
        "## Projects",
        "Campus Canteen App - React front end with a Firebase back end used by 300 students daily.",
        "Library Tracker - Java Swing desktop app for tracking issued books in the department library.",
    ])
    c.save()


def non_english_pdf():
    """Vietnamese name and city — requires a Unicode font."""
    pdfmetrics.registerFont(TTFont("ArialUnicode", UNICODE_FONT))
    c = canvas.Canvas(str(OUT / "non_english.pdf"), pagesize=LETTER)
    _write_lines(c, 50, H - 60, [
        "## Nguyễn Thị Hương",
        "huong.nguyen@fpt.com.vn",
        "+84 912 345 678",
        "Hà Nội, Vietnam",
        "linkedin.com/in/nguyen-thi-huong",
        "",
        "## Experience",
        "Product Manager, FPT Software, Feb 2020 - Present",
        "Business Analyst, Viettel Group, Jun 2017 - Jan 2020",
        "",
        "## Education",
        "MBA, National Economics University, 2017",
        "",
        "## Skills",
        "Product Strategy, Jira, SQL, Agile, Stakeholder Management",
    ], font="ArialUnicode")
    c.save()


def single_column_pdf():
    """Classic single-column US resume with long lines that span the page midpoint."""
    c = canvas.Canvas(str(OUT / "single_column.pdf"), pagesize=LETTER)
    _write_lines(c, 50, H - 60, [
        "## Michael O'Connor",
        "Austin, TX | (512) 555-0148 | mike.oconnor@protonmail.com | https://www.linkedin.com/in/mikeoconnor",
        "",
        "## Summary",
        "Backend engineer with experience building payment systems and internal developer platforms.",
        "",
        "## Experience",
        "Staff Software Engineer, Stripe                                                          Jan 2022 - Present",
        "Led the migration of ledger services to a sharded Postgres cluster serving 40k requests per second.",
        "Software Engineer, Dell Technologies                                                May 2017 - Dec 2021",
        "Built the internal deployment platform used by 600 engineers across four business units.",
        "",
        "## Education",
        "B.S. Computer Science, University of Texas at Austin, 2017",
        "",
        "## Skills",
        "Go, Python, PostgreSQL, Kubernetes, Terraform",
    ])
    c.save()


def present_docx():
    """DOCX with experience in a table and a 'Present' end date."""
    doc = Document()
    doc.add_heading("Sofia Martínez", level=1)
    doc.add_paragraph("sofia.martinez@example.es · +34 612 345 678 · Madrid, Spain")
    doc.add_paragraph("https://linkedin.com/in/sofiamartinez")
    doc.add_heading("Experience", level=2)
    table = doc.add_table(rows=3, cols=3)
    rows = [
        ("Role", "Company", "Dates"),
        ("UX Designer", "Telefónica", "Sep 2019 - Present"),
        ("Junior Designer", "Cabify", "Jan 2018 - Aug 2019"),
    ]
    for r, values in zip(table.rows, rows):
        for cell, v in zip(r.cells, values):
            cell.text = v
    doc.add_heading("Education", level=2)
    doc.add_paragraph("BA Graphic Design, Universidad Complutense de Madrid, 2017")
    doc.add_heading("Skills", level=2)
    doc.add_paragraph("Figma, User Research, Prototyping, Design Systems")
    doc.save(str(OUT / "present.docx"))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    two_column_pdf()
    fresher_pdf()
    non_english_pdf()
    single_column_pdf()
    present_docx()
    print(f"Wrote fixtures to {OUT}")
