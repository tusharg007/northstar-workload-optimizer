"""North Star — Problem Statement PDF Generator"""
import os
from fpdf import FPDF

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "problem_statement.pdf")

class PDF(FPDF):
    def header(self):
        self.set_fill_color(27, 42, 74)
        self.rect(0, 0, 210, 18, 'F')
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(255, 210, 63)
        self.cell(0, 12, 'NORTH STAR WORKLOAD OPTIMIZER', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Confidential | Page {self.page_no()}', align='C')

def build():
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(27, 42, 74)
    pdf.cell(0, 12, 'Problem Statement', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100)
    pdf.cell(0, 6, 'Digital Strategy & Discovery | Process Reengineering', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Horizontal line
    pdf.set_draw_color(255, 210, 63)
    pdf.set_line_width(1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)

    # Context
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(27, 42, 74)
    pdf.cell(0, 8, 'Business Context', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(50)
    pdf.multi_cell(0, 5.5,
        "A mid-sized professional services firm processes approximately 420 expense reports per month "
        "across 6 departments and 120 employees. The current workflow is manual, email-driven, and "
        "fragmented across spreadsheets, email inboxes, and legacy ERP systems. This creates significant "
        "delays, data quality issues, and employee dissatisfaction.")
    pdf.ln(5)

    # Problem
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(27, 42, 74)
    pdf.cell(0, 8, 'Problem Definition', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(50)
    problems = [
        "12-step manual process with 4 handoff points between Employee, Manager, Finance, and System",
        "Average cycle time of 9.7 days (industry best practice: 2 days)",
        "18% data entry error rate requiring costly rework cycles",
        "Annual operational cost of $620,647 for expense processing alone",
        "20% of approvals delayed beyond 10 days due to email queue bottlenecks",
        "81.5% receipt attachment rate vs. 98% compliance requirement",
        "No real-time visibility into approval status for employees"
    ]
    for p in problems:
        pdf.cell(5)
        pdf.cell(0, 6, f"  * {p}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Three bottlenecks
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(27, 42, 74)
    pdf.cell(0, 8, 'Three Critical Bottlenecks', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(50)
    bottlenecks = [
        ("1. Manual Data Entry & Receipt Management", "33 minutes per report, $124K/year"),
        ("2. Approval Queue Delays", "72+ hour average wait, $233K/year"),
        ("3. Finance Reconciliation & Batch Processing", "40 min active + 5-day batch, $185K/year"),
    ]
    for title, impact in bottlenecks:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, f"  {title}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 5, f"     Impact: {impact}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Proposed Solution
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(27, 42, 74)
    pdf.cell(0, 8, 'Proposed Solution', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(50)
    pdf.multi_cell(0, 5.5,
        "The North Star Workload Optimizer is an end-to-end digital transformation solution that combines "
        "AI-powered data extraction (OCR), automated approval routing (Power Automate), real-time analytics "
        "(Power BI), and anomaly detection (Python ML) to reduce the expense workflow from 12 manual steps "
        "to 5 automated steps.")
    pdf.ln(3)
    solutions = [
        "Reduce cycle time from 9.7 days to 2.1 days (78% improvement)",
        "Cut annual costs by $434,453 (70% reduction)",
        "Achieve 865% ROI in Year 1 with 1.2-month payback",
        "Increase automation rate from 0% to 85% of routine approvals",
    ]
    for s in solutions:
        pdf.cell(0, 6, f"  * {s}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Data evidence
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(27, 42, 74)
    pdf.cell(0, 8, 'Data-Driven Evidence', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(50)
    pdf.multi_cell(0, 5.5,
        "All metrics are derived from analysis of 5,000 simulated expense records spanning 18 months, "
        "calibrated against published benchmarks from GBTA, Aberdeen Group, and SAP Concur. "
        "The ETL pipeline processed records through validation, cleaning, feature engineering, and "
        "anomaly detection, identifying 664 flagged transactions (13.3% anomaly rate).")

    pdf.output(OUTPUT)
    print(f"PDF saved: {OUTPUT}")

if __name__ == "__main__":
    build()
