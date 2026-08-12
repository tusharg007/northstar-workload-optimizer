"""
North Star Workload Optimizer — Diagram Generator
===================================================
Generates AS-IS, TO-BE process flow diagrams and architecture diagram
using matplotlib for professional visual output.
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Color Palette (EY-inspired) ──
COLORS = {
    "navy": "#1B2A4A",
    "teal": "#2E86AB",
    "gold": "#FFD23F",
    "coral": "#EE6C4D",
    "green": "#2ECC71",
    "red": "#E74C3C",
    "gray": "#95A5A6",
    "light_gray": "#ECF0F1",
    "white": "#FFFFFF",
    "dark": "#2C3E50",
    "purple": "#8E44AD",
    "blue_light": "#3498DB",
}

def draw_box(ax, x, y, w, h, text, color, text_color="white", fontsize=8, style="round"):
    box = FancyBboxPatch((x, y), w, h, boxstyle=f"{style},pad=0.02",
                          facecolor=color, edgecolor=COLORS["dark"], linewidth=1.2)
    ax.add_patch(box)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center',
            fontsize=fontsize, color=text_color, fontweight='bold', wrap=True,
            fontfamily='sans-serif')

def draw_arrow(ax, x1, y1, x2, y2, color=COLORS["dark"]):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5))

def draw_bottleneck(ax, x, y, w, h, text):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02",
                          facecolor=COLORS["coral"], edgecolor=COLORS["red"],
                          linewidth=2.5, linestyle='--')
    ax.add_patch(box)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center',
            fontsize=7, color="white", fontweight='bold', wrap=True)


def generate_as_is_diagram():
    """Generate AS-IS process flow diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(18, 10))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Title
    ax.text(9, 9.6, "AS-IS Process Flow — Expense Reporting Workflow",
            ha='center', fontsize=16, fontweight='bold', color=COLORS["navy"])
    ax.text(9, 9.2, "Current State: Manual, Email-Based Process with 3 Critical Bottlenecks",
            ha='center', fontsize=10, color=COLORS["gray"])

    # Swim lane labels
    lanes = [("Employee", 7.5), ("Manager", 5.5), ("Finance", 3.5), ("System", 1.5)]
    for name, y_pos in lanes:
        ax.text(0.3, y_pos + 0.3, name, fontsize=11, fontweight='bold', color=COLORS["navy"])
        ax.axhline(y=y_pos - 0.5, color=COLORS["light_gray"], linewidth=1, linestyle='-')

    # Employee lane steps
    draw_box(ax, 1.5, 7.2, 2, 0.7, "1. Incur\nExpense", COLORS["teal"])
    draw_arrow(ax, 3.5, 7.55, 4, 7.55)

    draw_bottleneck(ax, 4, 7.2, 2.2, 0.7, "2-4. Manual Entry\n& Receipt Scan\n⚠ BOTTLENECK 1")
    draw_arrow(ax, 6.2, 7.55, 6.7, 7.55)

    draw_box(ax, 6.7, 7.2, 2, 0.7, "5. Submit\nvia Email", COLORS["teal"])
    draw_arrow(ax, 8.7, 7.2, 9.5, 2.2)

    # System lane
    draw_box(ax, 9.5, 1.2, 2, 0.7, "6. Route to\nManager (Email)", COLORS["gray"])
    draw_arrow(ax, 10.5, 1.9, 10.5, 5.2)
    ax.text(11, 3.5, "⏱ 48hr\nwait", fontsize=8, color=COLORS["red"], fontweight='bold')

    # Manager lane
    draw_bottleneck(ax, 9.5, 5.2, 2.3, 0.7, "7-9. Review &\nApprove/Reject\n⚠ BOTTLENECK 2")
    draw_arrow(ax, 11.8, 5.55, 12.5, 5.55)
    ax.text(12, 6.1, "⏱ 24hr wait", fontsize=8, color=COLORS["red"], fontweight='bold')

    draw_box(ax, 12.5, 5.2, 1.8, 0.7, "Forward to\nFinance", COLORS["teal"])
    draw_arrow(ax, 13.4, 5.2, 13.4, 4.2)

    # Finance lane
    draw_bottleneck(ax, 12.5, 3.2, 2.3, 0.7, "10-11. Validate\n& Process ERP\n⚠ BOTTLENECK 3")
    draw_arrow(ax, 14.8, 3.55, 15.5, 3.55)
    ax.text(14.9, 4.1, "⏱ 72hr batch", fontsize=8, color=COLORS["red"], fontweight='bold')

    # Final system step
    draw_box(ax, 15.2, 1.2, 2, 0.7, "12. Payment\n& Notify", COLORS["green"])
    draw_arrow(ax, 15.5, 3.2, 16.2, 1.9)

    # Legend
    legend_y = 0.3
    draw_box(ax, 1, legend_y, 1.5, 0.4, "Normal Step", COLORS["teal"], fontsize=7)
    draw_bottleneck(ax, 3, legend_y, 1.5, 0.4, "Bottleneck")
    ax.text(5, legend_y + 0.15, "⏱ = Queue/Wait Time", fontsize=9, color=COLORS["red"])
    ax.text(8, legend_y + 0.15, "Total: 12 steps | ~9.7 days end-to-end | $620K annual cost",
            fontsize=9, color=COLORS["navy"], fontweight='bold')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "as_is_process_flow.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ AS-IS diagram saved: {path}")


def generate_to_be_diagram():
    """Generate TO-BE automated process flow diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(18, 10))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 10)
    ax.axis('off')

    ax.text(9, 9.6, "TO-BE Process Flow — Automated Expense Workflow",
            ha='center', fontsize=16, fontweight='bold', color=COLORS["navy"])
    ax.text(9, 9.2, "Future State: AI-Powered Automation with Power Automate Integration",
            ha='center', fontsize=10, color=COLORS["green"])

    # Swim lanes
    lanes = [("Employee", 7.5), ("AI/Automation", 5.5), ("Finance", 3.5), ("System", 1.5)]
    for name, y_pos in lanes:
        ax.text(0.3, y_pos + 0.3, name, fontsize=11, fontweight='bold', color=COLORS["navy"])
        ax.axhline(y=y_pos - 0.5, color=COLORS["light_gray"], linewidth=1, linestyle='-')

    # Step 1: Mobile capture
    draw_box(ax, 1.5, 7.2, 2.2, 0.7, "1. Snap Receipt\n(Mobile OCR)", COLORS["green"])
    draw_arrow(ax, 3.7, 7.55, 4.5, 7.55)

    # Step 2: Auto-extract
    draw_box(ax, 4.5, 7.2, 2.2, 0.7, "2. Auto-Extract\nData (AI)", COLORS["green"])
    draw_arrow(ax, 5.6, 7.2, 5.6, 6.2)

    # AI/Automation lane
    draw_box(ax, 4.5, 5.2, 2.2, 0.7, "3. Validate &\nFlag Anomalies", COLORS["purple"],
             text_color="white")
    draw_arrow(ax, 6.7, 5.55, 7.5, 5.55)

    draw_box(ax, 7.5, 5.2, 2.2, 0.7, "4. Auto-Route\nfor Approval", COLORS["purple"])
    ax.text(7.5, 6.1, "⚡ < $500 = Auto-approve", fontsize=8, color=COLORS["green"], fontweight='bold')
    draw_arrow(ax, 9.7, 5.55, 10.5, 5.55)

    draw_box(ax, 10.5, 5.2, 2.2, 0.7, "5. Teams/Mobile\nApproval", COLORS["teal"])
    ax.text(10.5, 4.7, "⏱ < 4hrs (SLA enforced)", fontsize=8, color=COLORS["green"])
    draw_arrow(ax, 11.6, 5.2, 11.6, 4.2)

    # Finance lane
    draw_box(ax, 10.5, 3.2, 2.2, 0.7, "6. Auto-Process\n& Reconcile", COLORS["green"])
    draw_arrow(ax, 12.7, 3.55, 13.5, 3.55)

    # System lane
    draw_box(ax, 13, 1.2, 2.5, 0.7, "7. Real-Time\nPayment & Notify", COLORS["green"])
    draw_arrow(ax, 13, 3.2, 14.2, 1.9)

    # Improvement callouts
    ax.text(1, 0.4, "✅ 5 automated steps (vs. 12 manual)", fontsize=10,
            color=COLORS["green"], fontweight='bold')
    ax.text(7, 0.4, "✅ 2.1 days end-to-end (vs. 9.7 days)", fontsize=10,
            color=COLORS["green"], fontweight='bold')
    ax.text(13, 0.4, "✅ $434K annual savings", fontsize=10,
            color=COLORS["green"], fontweight='bold')

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "to_be_process_flow.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ TO-BE diagram saved: {path}")


def generate_architecture_diagram():
    """Generate solution architecture diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis('off')

    ax.text(8, 9.5, "North Star Workload Optimizer — Solution Architecture",
            ha='center', fontsize=16, fontweight='bold', color=COLORS["navy"])

    # Layer 1: Data Sources (top)
    ax.text(8, 8.8, "─── Data Sources ───", ha='center', fontsize=10, color=COLORS["gray"])
    sources = [("SharePoint\nLists", 1.5), ("Email\n(Outlook)", 4.5),
               ("MS Forms", 7.5), ("Corporate\nCard Feed", 10.5), ("Mobile\nApp", 13.5)]
    for label, x in sources:
        draw_box(ax, x, 7.8, 1.8, 0.7, label, COLORS["teal"], fontsize=8)

    # Layer 2: Ingestion
    ax.text(8, 7.3, "─── Ingestion & ETL Layer ───", ha='center', fontsize=10, color=COLORS["gray"])
    draw_box(ax, 3, 6.3, 4, 0.7, "Power Automate Trigger\n(Event-Driven Ingestion)", COLORS["navy"])
    draw_box(ax, 9, 6.3, 4, 0.7, "Python ETL Pipeline\n(Pandas + Validation)", COLORS["navy"])

    for _, x in sources:
        draw_arrow(ax, x + 0.9, 7.8, 5, 7.0, COLORS["gray"])

    # Layer 3: AI/Processing
    ax.text(8, 5.8, "─── AI & Processing Layer ───", ha='center', fontsize=10, color=COLORS["gray"])
    draw_box(ax, 1, 4.8, 3, 0.7, "Anomaly Detection\n(Rule-Based + ML)", COLORS["purple"])
    draw_box(ax, 5, 4.8, 3, 0.7, "Policy Validation\n(Pydantic Engine)", COLORS["purple"])
    draw_box(ax, 9, 4.8, 3, 0.7, "Approval Router\n(Threshold Logic)", COLORS["purple"])
    draw_box(ax, 13, 4.8, 2.5, 0.7, "OCR\n(Azure AI)", COLORS["purple"])

    # Layer 4: Data Store
    ax.text(8, 4.3, "─── Data Store ───", ha='center', fontsize=10, color=COLORS["gray"])
    draw_box(ax, 3, 3.3, 3, 0.7, "SQLite / Azure SQL\n(Normalized Schema)", COLORS["dark"])
    draw_box(ax, 8, 3.3, 3, 0.7, "SharePoint\n(Documents/Receipts)", COLORS["dark"])
    draw_box(ax, 13, 3.3, 2.5, 0.7, "Blob Storage\n(Archive)", COLORS["dark"])

    # Layer 5: Analytics & Reporting
    ax.text(8, 2.8, "─── Analytics & Reporting ───", ha='center', fontsize=10, color=COLORS["gray"])
    draw_box(ax, 2, 1.8, 3, 0.7, "Power BI Dashboard\n(5 KPIs, 4 Pages)", COLORS["gold"],
             text_color=COLORS["dark"])
    draw_box(ax, 6, 1.8, 3, 0.7, "Excel Reports\n(ROI + Benchmarks)", COLORS["gold"],
             text_color=COLORS["dark"])
    draw_box(ax, 10, 1.8, 3, 0.7, "Teams Notifications\n(Adaptive Cards)", COLORS["gold"],
             text_color=COLORS["dark"])

    # Bottom label
    ax.text(8, 0.8, "Technology Stack: Python 3.13 | Pandas | SQLite | Power BI | Power Automate | Azure AI",
            ha='center', fontsize=10, fontweight='bold', color=COLORS["navy"],
            bbox=dict(boxstyle='round,pad=0.3', facecolor=COLORS["light_gray"], edgecolor=COLORS["navy"]))

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "architecture_diagram.png")
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Architecture diagram saved: {path}")


if __name__ == "__main__":
    print("Generating diagrams...")
    generate_as_is_diagram()
    generate_to_be_diagram()
    generate_architecture_diagram()
    print("\n✅ All diagrams generated successfully.")
