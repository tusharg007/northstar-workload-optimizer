"""
North Star Workload Optimizer — Mock Expense Data Generator
============================================================
Generates 5,000 realistic expense report records for a mid-sized
professional services firm. Outputs CSV + JSON for downstream ETL.

Author : North Star Analytics Team
Version: 1.0.0
"""

import os
import json
import random
import hashlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

# ── Configuration ────────────────────────────────────────────────
SEED = 42
NUM_RECORDS = 5000
NUM_EMPLOYEES = 120
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

fake = Faker()
Faker.seed(SEED)
np.random.seed(SEED)
random.seed(SEED)

# ── Reference Data ───────────────────────────────────────────────
DEPARTMENTS = {
    "Sales":       {"weight": 0.25, "avg_expense": 280, "headcount": 30},
    "IT":          {"weight": 0.20, "avg_expense": 350, "headcount": 24},
    "Marketing":   {"weight": 0.18, "avg_expense": 220, "headcount": 22},
    "Finance":     {"weight": 0.15, "avg_expense": 150, "headcount": 18},
    "HR":          {"weight": 0.12, "avg_expense": 120, "headcount": 14},
    "Operations":  {"weight": 0.10, "avg_expense": 180, "headcount": 12},
}

EXPENSE_CATEGORIES = {
    "Travel":                {"min": 50,  "max": 5000, "mu": 6.0, "sigma": 0.8},
    "Meals & Entertainment": {"min": 10,  "max": 500,  "mu": 3.8, "sigma": 0.6},
    "Office Supplies":       {"min": 5,   "max": 300,  "mu": 3.2, "sigma": 0.5},
    "Software & Subscriptions": {"min": 15, "max": 2000, "mu": 4.5, "sigma": 0.7},
    "Training & Development":{"min": 100, "max": 3000, "mu": 5.5, "sigma": 0.6},
    "Client Entertainment":  {"min": 30,  "max": 2000, "mu": 4.8, "sigma": 0.7},
    "Transportation":        {"min": 10,  "max": 800,  "mu": 3.5, "sigma": 0.6},
    "Telecommunications":    {"min": 20,  "max": 500,  "mu": 3.8, "sigma": 0.4},
    "Equipment":             {"min": 50,  "max": 5000, "mu": 5.2, "sigma": 0.9},
    "Miscellaneous":         {"min": 5,   "max": 1000, "mu": 3.5, "sigma": 0.8},
}

PAYMENT_METHODS = ["Corporate Card", "Personal Card", "Cash", "Wire Transfer", "Petty Cash"]
PAYMENT_WEIGHTS = [0.45, 0.25, 0.15, 0.10, 0.05]

STATUSES = ["Pending", "Approved", "Rejected", "Under Review", "Escalated"]

CURRENCIES = ["USD", "USD", "USD", "USD", "EUR", "GBP"]  # Mostly USD

MERCHANTS_BY_CATEGORY = {
    "Travel": ["United Airlines", "Delta Airlines", "Marriott Hotels", "Hilton Hotels",
               "Hyatt Regency", "Hertz Rental", "Enterprise Rent-A-Car", "Expedia", "Booking.com"],
    "Meals & Entertainment": ["Starbucks", "Panera Bread", "Chipotle", "The Capital Grille",
                               "Olive Garden", "Subway", "McDonald's", "Local Restaurant"],
    "Office Supplies": ["Staples", "Office Depot", "Amazon Business", "W.B. Mason", "Uline"],
    "Software & Subscriptions": ["Microsoft 365", "Adobe Creative Cloud", "Slack Technologies",
                                   "Zoom Video", "Salesforce", "GitHub Enterprise", "Atlassian"],
    "Training & Development": ["Coursera", "Udemy Business", "LinkedIn Learning",
                                "PwC Academy", "Deloitte University", "Conference Registration"],
    "Client Entertainment": ["The Ritz-Carlton", "Four Seasons", "TopGolf", "Morton's Steakhouse",
                              "Peter Luger Steakhouse", "Live Nation Events"],
    "Transportation": ["Uber Business", "Lyft", "Yellow Cab", "Metro Transit", "Amtrak",
                        "Enterprise Fleet", "Zipcar"],
    "Telecommunications": ["AT&T Business", "Verizon Wireless", "T-Mobile", "Comcast Business"],
    "Equipment": ["Dell Technologies", "Apple Business", "Lenovo", "HP Enterprise",
                   "Best Buy Business", "CDW Corporation"],
    "Miscellaneous": ["FedEx", "UPS", "DHL Express", "Local Vendor", "Miscellaneous Vendor"],
}

BUSINESS_PURPOSES = [
    "Client meeting preparation", "Quarterly business review", "Team offsite planning",
    "Project kickoff supplies", "Conference attendance", "Client dinner",
    "Training certification", "Software renewal", "Hardware replacement",
    "Travel to client site", "Internal workshop", "Recruitment dinner",
    "Office maintenance", "Emergency procurement", "Vendor assessment visit",
    "Strategy session catering", "Annual license renewal", "Remote work equipment",
    "Industry event networking", "Cross-team collaboration lunch",
]


# ── Employee Master Data ─────────────────────────────────────────
def generate_employees(n: int) -> list[dict]:
    """Generate a consistent set of employees across departments."""
    employees = []
    emp_id = 1001

    dept_names = list(DEPARTMENTS.keys())
    dept_weights = [DEPARTMENTS[d]["weight"] for d in dept_names]

    for _ in range(n):
        dept = random.choices(dept_names, weights=dept_weights, k=1)[0]
        name = fake.name()
        employees.append({
            "employee_id": f"EMP-{emp_id:04d}",
            "employee_name": name,
            "department": dept,
            "email": f"{name.lower().replace(' ', '.')}@northstar.com",
            "hire_date": fake.date_between(start_date="-8y", end_date="-6m"),
            "manager_name": fake.name(),
        })
        emp_id += 1
    return employees


# ── Expense Amount Generator ─────────────────────────────────────
def generate_amount(category: str) -> float:
    """Generate expense amount using log-normal distribution per category."""
    params = EXPENSE_CATEGORIES[category]
    raw = np.random.lognormal(mean=params["mu"], sigma=params["sigma"])
    amount = np.clip(raw, params["min"], params["max"])
    return round(float(amount), 2)


# ── Date Generator ───────────────────────────────────────────────
def generate_dates(base_date: datetime) -> dict:
    """Generate transaction, submission, and approval dates with realistic lags."""
    transaction_date = base_date

    # Submission lag: usually 1-5 days, sometimes up to 30 (bottleneck!)
    if random.random() < 0.15:  # 15% late submissions
        submission_lag = int(np.random.gamma(shape=3, scale=5))  # Heavy tail
    else:
        submission_lag = random.randint(0, 3)

    submission_date = transaction_date + timedelta(days=submission_lag)

    # Approval lag: gamma distribution — most 1-5 days, some 15-30 (bottleneck!)
    if random.random() < 0.20:  # 20% slow approvals
        approval_lag = int(np.random.gamma(shape=4, scale=4)) + 3
    else:
        approval_lag = random.randint(1, 5)

    approval_date = submission_date + timedelta(days=approval_lag)

    return {
        "transaction_date": transaction_date.strftime("%Y-%m-%d"),
        "submission_date": submission_date.strftime("%Y-%m-%d"),
        "approval_date": approval_date.strftime("%Y-%m-%d"),
        "submission_lag_days": submission_lag,
        "approval_lag_days": approval_lag,
    }


# ── Anomaly Injector ─────────────────────────────────────────────
def inject_anomaly(record: dict, anomaly_type: str) -> dict:
    """Inject realistic anomaly patterns into expense records."""
    if anomaly_type == "duplicate":
        record["description"] = "DUPLICATE — " + record["description"]
        record["anomaly_type"] = "duplicate_submission"
    elif anomaly_type == "weekend":
        # Shift transaction to weekend
        dt = datetime.strptime(record["transaction_date"], "%Y-%m-%d")
        days_to_saturday = (5 - dt.weekday()) % 7
        weekend_date = dt + timedelta(days=days_to_saturday)
        record["transaction_date"] = weekend_date.strftime("%Y-%m-%d")
        record["anomaly_type"] = "weekend_transaction"
    elif anomaly_type == "round_amount":
        record["amount"] = round(record["amount"] / 100) * 100
        if record["amount"] == 0:
            record["amount"] = 100.0
        record["anomaly_type"] = "suspicious_round_amount"
    elif anomaly_type == "high_value":
        record["amount"] = round(record["amount"] * random.uniform(3, 8), 2)
        record["anomaly_type"] = "unusually_high_amount"
    elif anomaly_type == "missing_receipt":
        record["receipt_attached"] = False
        record["amount"] = round(record["amount"] * random.uniform(1.5, 3), 2)
        record["anomaly_type"] = "missing_receipt_high_value"
    else:
        record["anomaly_type"] = "none"

    return record


# ── Main Data Generation ─────────────────────────────────────────
def generate_expenses(num_records: int, employees: list[dict]) -> pd.DataFrame:
    """Generate the full expense dataset."""
    records = []
    expense_id = 1

    # Date range: last 18 months
    end_date = datetime(2026, 3, 31)
    start_date = end_date - timedelta(days=548)  # ~18 months

    categories = list(EXPENSE_CATEGORIES.keys())
    anomaly_types = ["duplicate", "weekend", "round_amount", "high_value", "missing_receipt"]

    for i in range(num_records):
        # Pick employee
        emp = random.choice(employees)

        # Pick category with weighted distribution
        category = random.choices(
            categories,
            weights=[0.20, 0.18, 0.10, 0.12, 0.08, 0.10, 0.08, 0.05, 0.05, 0.04],
            k=1
        )[0]

        # Generate base date
        days_offset = random.randint(0, (end_date - start_date).days)
        base_date = start_date + timedelta(days=days_offset)
        dates = generate_dates(base_date)

        # Generate amount
        amount = generate_amount(category)

        # Pick merchant
        merchant = random.choice(MERCHANTS_BY_CATEGORY[category])

        # Generate confidence score (higher = more confident it's legitimate)
        confidence = round(np.clip(np.random.normal(0.85, 0.12), 0.1, 1.0), 3)

        # Determine status based on confidence and amount
        if confidence < 0.5:
            status = random.choices(["Rejected", "Under Review", "Escalated"], weights=[0.4, 0.4, 0.2], k=1)[0]
        elif amount > 2000:
            status = random.choices(["Approved", "Under Review", "Escalated"], weights=[0.5, 0.3, 0.2], k=1)[0]
        else:
            status = random.choices(STATUSES, weights=[0.15, 0.55, 0.10, 0.15, 0.05], k=1)[0]

        # Policy compliance
        policy_compliant = confidence > 0.6 and amount < 5000
        receipt_attached = random.random() < 0.82  # 82% have receipts

        record = {
            "expense_id": f"EXP-{expense_id:05d}",
            "employee_id": emp["employee_id"],
            "employee_name": emp["employee_name"],
            "department": emp["department"],
            "transaction_date": dates["transaction_date"],
            "submission_date": dates["submission_date"],
            "approval_date": dates["approval_date"],
            "submission_lag_days": dates["submission_lag_days"],
            "approval_lag_days": dates["approval_lag_days"],
            "merchant": merchant,
            "category": category,
            "description": random.choice(BUSINESS_PURPOSES),
            "amount": amount,
            "currency": random.choices(CURRENCIES, k=1)[0],
            "payment_method": random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS, k=1)[0],
            "receipt_attached": receipt_attached,
            "status": status,
            "approver_name": emp["manager_name"],
            "policy_compliant": policy_compliant,
            "confidence_score": confidence,
            "anomaly_type": "none",
        }

        # Inject anomalies into ~5% of records
        if random.random() < 0.05:
            anomaly = random.choice(anomaly_types)
            record = inject_anomaly(record, anomaly)

        records.append(record)
        expense_id += 1

    return pd.DataFrame(records)


# ── Output Writers ────────────────────────────────────────────────
def save_data(df: pd.DataFrame, employees: list[dict]) -> None:
    """Save generated data in CSV and JSON formats."""
    csv_path = os.path.join(OUTPUT_DIR, "expenses.csv")
    json_path = os.path.join(OUTPUT_DIR, "expenses.json")
    emp_csv_path = os.path.join(OUTPUT_DIR, "employees.csv")

    # Save expenses
    df.to_csv(csv_path, index=False)
    print(f"✓ CSV saved: {csv_path} ({len(df):,} records)")

    df.to_json(json_path, orient="records", indent=2, date_format="iso")
    print(f"✓ JSON saved: {json_path} ({len(df):,} records)")

    # Save employee master
    emp_df = pd.DataFrame(employees)
    emp_df.to_csv(emp_csv_path, index=False)
    print(f"✓ Employee master saved: {emp_csv_path} ({len(emp_df):,} employees)")


# ── Summary Statistics ────────────────────────────────────────────
def print_summary(df: pd.DataFrame) -> None:
    """Print generation summary statistics."""
    print("\n" + "=" * 60)
    print("  NORTH STAR WORKLOAD OPTIMIZER — DATA GENERATION SUMMARY")
    print("=" * 60)
    print(f"\n  Total records generated : {len(df):,}")
    print(f"  Date range             : {df['transaction_date'].min()} → {df['transaction_date'].max()}")
    print(f"  Total expense value    : ${df['amount'].sum():,.2f}")
    print(f"  Average expense        : ${df['amount'].mean():,.2f}")
    print(f"  Median expense         : ${df['amount'].median():,.2f}")

    print(f"\n  ── Department Breakdown ──")
    dept_stats = df.groupby("department").agg(
        count=("expense_id", "count"),
        total=("amount", "sum"),
        avg=("amount", "mean")
    ).sort_values("total", ascending=False)
    for dept, row in dept_stats.iterrows():
        print(f"    {dept:<15} {row['count']:>5} records  ${row['total']:>12,.2f}  (avg ${row['avg']:>8,.2f})")

    print(f"\n  ── Category Breakdown ──")
    cat_stats = df.groupby("category")["amount"].agg(["count", "sum"]).sort_values("sum", ascending=False)
    for cat, row in cat_stats.iterrows():
        print(f"    {cat:<28} {row['count']:>5} records  ${row['sum']:>12,.2f}")

    print(f"\n  ── Status Distribution ──")
    for status, count in df["status"].value_counts().items():
        pct = count / len(df) * 100
        print(f"    {status:<15} {count:>5} ({pct:.1f}%)")

    anomalies = df[df["anomaly_type"] != "none"]
    print(f"\n  ── Anomaly Injection ──")
    print(f"    Total anomalies      : {len(anomalies)} ({len(anomalies)/len(df)*100:.1f}%)")
    for atype, count in anomalies["anomaly_type"].value_counts().items():
        print(f"    {atype:<30} {count:>3}")

    avg_sub_lag = df["submission_lag_days"].mean()
    avg_app_lag = df["approval_lag_days"].mean()
    print(f"\n  ── Processing Metrics ──")
    print(f"    Avg submission lag   : {avg_sub_lag:.1f} days")
    print(f"    Avg approval lag     : {avg_app_lag:.1f} days")
    print(f"    Receipts attached    : {df['receipt_attached'].sum()} ({df['receipt_attached'].mean()*100:.1f}%)")
    print(f"    Policy compliant     : {df['policy_compliant'].sum()} ({df['policy_compliant'].mean()*100:.1f}%)")
    print("=" * 60)


# ── Entry Point ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating employee master data...")
    employees = generate_employees(NUM_EMPLOYEES)

    print(f"Generating {NUM_RECORDS:,} mock expense records...")
    df = generate_expenses(NUM_RECORDS, employees)

    print("Saving output files...")
    save_data(df, employees)

    print_summary(df)
    print("\n✅ Data generation complete. Ready for ETL pipeline.")
