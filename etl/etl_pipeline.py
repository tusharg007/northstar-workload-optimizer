"""
North Star Workload Optimizer — ETL Pipeline
==============================================
Extract, Transform, Load pipeline that:
  1. Reads raw CSV expense data
  2. Validates & cleans records
  3. Engineers analytical features
  4. Loads into a normalized SQLite database

Author : North Star Analytics Team
Version: 1.0.0
"""

import os
import sys
import logging
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

# ── Configuration ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
DB_PATH = os.path.join(PROJECT_DIR, "data", "northstar.db")
CSV_PATH = os.path.join(DATA_DIR, "expenses.csv")

# ── Logging Setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("etl_pipeline")


# ══════════════════════════════════════════════════════════════════
#  EXTRACT
# ══════════════════════════════════════════════════════════════════
def extract(filepath: str) -> pd.DataFrame:
    """Read raw CSV with proper type inference and date parsing."""
    log.info(f"EXTRACT │ Reading from {filepath}")

    date_cols = ["transaction_date", "submission_date", "approval_date"]
    df = pd.read_csv(
        filepath,
        parse_dates=date_cols,
        dtype={
            "expense_id": str,
            "employee_id": str,
            "employee_name": str,
            "department": str,
            "merchant": str,
            "category": str,
            "description": str,
            "currency": str,
            "payment_method": str,
            "status": str,
            "approver_name": str,
            "anomaly_type": str,
        },
    )

    log.info(f"EXTRACT │ Loaded {len(df):,} records with {len(df.columns)} columns")
    log.info(f"EXTRACT │ Date range: {df['transaction_date'].min()} → {df['transaction_date'].max()}")
    return df


# ══════════════════════════════════════════════════════════════════
#  TRANSFORM — Validation
# ══════════════════════════════════════════════════════════════════
class DataValidator:
    """Validates expense records against business rules."""

    def __init__(self):
        self.issues = []

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run all validation checks and flag issues."""
        log.info("VALIDATE │ Running validation checks...")
        df = df.copy()
        df["validation_flags"] = ""

        # 1. Null checks on critical fields
        critical = ["expense_id", "employee_id", "amount", "category", "transaction_date"]
        for col in critical:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                log.warning(f"VALIDATE │ {null_count} null values in '{col}'")
                df.loc[df[col].isnull(), "validation_flags"] += f"NULL_{col};"
                self.issues.append({"field": col, "issue": "null_values", "count": int(null_count)})

        # 2. Amount range validation
        neg_amounts = (df["amount"] <= 0).sum()
        if neg_amounts > 0:
            log.warning(f"VALIDATE │ {neg_amounts} records with non-positive amounts")
            df.loc[df["amount"] <= 0, "validation_flags"] += "INVALID_AMOUNT;"
            self.issues.append({"field": "amount", "issue": "non_positive", "count": int(neg_amounts)})

        extreme_amounts = (df["amount"] > 50000).sum()
        if extreme_amounts > 0:
            log.warning(f"VALIDATE │ {extreme_amounts} records with extreme amounts (>$50,000)")
            df.loc[df["amount"] > 50000, "validation_flags"] += "EXTREME_AMOUNT;"

        # 3. Date consistency: transaction ≤ submission ≤ approval
        date_issues = (df["transaction_date"] > df["submission_date"]).sum()
        if date_issues > 0:
            log.warning(f"VALIDATE │ {date_issues} records where transaction_date > submission_date")
            df.loc[df["transaction_date"] > df["submission_date"], "validation_flags"] += "DATE_INCONSISTENCY;"

        # 4. Category validation
        valid_categories = [
            "Travel", "Meals & Entertainment", "Office Supplies",
            "Software & Subscriptions", "Training & Development",
            "Client Entertainment", "Transportation", "Telecommunications",
            "Equipment", "Miscellaneous"
        ]
        invalid_cats = ~df["category"].isin(valid_categories)
        if invalid_cats.sum() > 0:
            log.warning(f"VALIDATE │ {invalid_cats.sum()} records with invalid categories")
            df.loc[invalid_cats, "validation_flags"] += "INVALID_CATEGORY;"

        total_issues = (df["validation_flags"] != "").sum()
        log.info(f"VALIDATE │ Validation complete. {total_issues} records flagged.")
        return df


# ══════════════════════════════════════════════════════════════════
#  TRANSFORM — Cleaning
# ══════════════════════════════════════════════════════════════════
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and normalize expense data."""
    log.info("CLEAN │ Starting data cleaning...")
    df = df.copy()

    # 1. Trim whitespace from string columns
    str_cols = df.select_dtypes(include=["object"]).columns
    for col in str_cols:
        df[col] = df[col].str.strip()
    log.info(f"CLEAN │ Trimmed whitespace on {len(str_cols)} string columns")

    # 2. Normalize category names
    df["category"] = df["category"].str.title()

    # 3. Normalize department names
    df["department"] = df["department"].str.title()

    # 4. Standardize currency to uppercase
    df["currency"] = df["currency"].str.upper()

    # 5. Fill missing receipts as False
    df["receipt_attached"] = df["receipt_attached"].fillna(False)

    # 6. Ensure amount is positive
    df["amount"] = df["amount"].abs()

    # 7. Round amounts to 2 decimal places
    df["amount"] = df["amount"].round(2)

    log.info(f"CLEAN │ Data cleaning complete. {len(df):,} records processed.")
    return df


# ══════════════════════════════════════════════════════════════════
#  TRANSFORM — Feature Engineering
# ══════════════════════════════════════════════════════════════════
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create analytical features for downstream analysis."""
    log.info("FEATURES │ Engineering analytical features...")
    df = df.copy()

    # 1. Recalculate lag days from actual dates (in case of cleaning changes)
    df["submission_lag_days"] = (df["submission_date"] - df["transaction_date"]).dt.days
    df["approval_lag_days"] = (df["approval_date"] - df["submission_date"]).dt.days
    df["total_processing_days"] = (df["approval_date"] - df["transaction_date"]).dt.days

    # 2. Weekend submission flag
    df["is_weekend_submission"] = df["submission_date"].dt.dayofweek.isin([5, 6])

    # 3. Weekend transaction flag
    df["is_weekend_transaction"] = df["transaction_date"].dt.dayofweek.isin([5, 6])

    # 4. Round amount flag (amounts divisible by 50)
    df["is_round_amount"] = (df["amount"] % 50 == 0) & (df["amount"] > 0)

    # 5. Amount z-score per category
    df["amount_zscore"] = df.groupby("category")["amount"].transform(
        lambda x: (x - x.mean()) / x.std()
    ).round(3)

    # 6. Composite anomaly flag
    df["anomaly_flag"] = (
        (df["amount_zscore"].abs() > 2.5) |  # Statistical outlier
        (df["is_weekend_transaction"] & (df["amount"] > 500)) |  # Weekend high-value
        (df["is_round_amount"] & (df["amount"] > 1000)) |  # Suspicious round amounts
        (~df["receipt_attached"] & (df["amount"] > 200)) |  # No receipt, high value
        (df["anomaly_type"] != "none")  # Pre-flagged anomalies
    )

    # 7. Expense tier
    df["expense_tier"] = pd.cut(
        df["amount"],
        bins=[0, 50, 200, 500, 2000, float("inf")],
        labels=["Micro", "Low", "Medium", "High", "Premium"],
    )

    # 8. Month and quarter extraction
    df["transaction_month"] = df["transaction_date"].dt.to_period("M").astype(str)
    df["transaction_quarter"] = df["transaction_date"].dt.to_period("Q").astype(str)
    df["transaction_year"] = df["transaction_date"].dt.year

    # 9. Day of week name
    df["day_of_week"] = df["transaction_date"].dt.day_name()

    # 10. Approval speed category
    df["approval_speed"] = pd.cut(
        df["approval_lag_days"],
        bins=[-1, 2, 5, 10, float("inf")],
        labels=["Fast (≤2d)", "Normal (3-5d)", "Slow (6-10d)", "Critical (>10d)"],
    )

    anomaly_count = df["anomaly_flag"].sum()
    log.info(f"FEATURES │ Engineered 10 features. {anomaly_count} anomalies flagged ({anomaly_count/len(df)*100:.1f}%)")
    return df


# ══════════════════════════════════════════════════════════════════
#  TRANSFORM — Deduplication
# ══════════════════════════════════════════════════════════════════
def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Identify and flag potential duplicate submissions."""
    log.info("DEDUP │ Checking for duplicate submissions...")

    # Flag exact duplicates on key fields
    dup_cols = ["employee_id", "merchant", "amount", "transaction_date"]
    df["is_potential_duplicate"] = df.duplicated(subset=dup_cols, keep=False)

    dup_count = df["is_potential_duplicate"].sum()
    log.info(f"DEDUP │ Found {dup_count} potential duplicates ({dup_count/len(df)*100:.1f}%)")

    return df


# ══════════════════════════════════════════════════════════════════
#  LOAD — SQLite Database
# ══════════════════════════════════════════════════════════════════
def load_to_sqlite(df: pd.DataFrame, db_path: str) -> None:
    """Load cleaned data into a normalized SQLite database."""
    log.info(f"LOAD │ Connecting to SQLite: {db_path}")

    # Remove existing DB to start fresh
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── Create dimension tables ──────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_departments (
            department_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            department_name TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_employees (
            employee_id     TEXT PRIMARY KEY,
            employee_name   TEXT NOT NULL,
            department_name TEXT NOT NULL,
            email           TEXT,
            hire_date       DATE,
            manager_name    TEXT,
            FOREIGN KEY (department_name) REFERENCES dim_departments(department_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_categories (
            category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL
        )
    """)

    # ── Create fact table ────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_expenses (
            expense_id              TEXT PRIMARY KEY,
            employee_id             TEXT NOT NULL,
            employee_name           TEXT NOT NULL,
            department              TEXT NOT NULL,
            transaction_date        DATE NOT NULL,
            submission_date         DATE NOT NULL,
            approval_date           DATE,
            submission_lag_days     INTEGER,
            approval_lag_days       INTEGER,
            total_processing_days   INTEGER,
            merchant                TEXT,
            category                TEXT NOT NULL,
            description             TEXT,
            amount                  REAL NOT NULL,
            currency                TEXT DEFAULT 'USD',
            payment_method          TEXT,
            receipt_attached        BOOLEAN,
            status                  TEXT,
            approver_name           TEXT,
            policy_compliant        BOOLEAN,
            confidence_score        REAL,
            anomaly_type            TEXT DEFAULT 'none',
            anomaly_flag            BOOLEAN DEFAULT 0,
            is_weekend_submission   BOOLEAN DEFAULT 0,
            is_weekend_transaction  BOOLEAN DEFAULT 0,
            is_round_amount         BOOLEAN DEFAULT 0,
            amount_zscore           REAL,
            expense_tier            TEXT,
            transaction_month       TEXT,
            transaction_quarter     TEXT,
            transaction_year        INTEGER,
            day_of_week             TEXT,
            approval_speed          TEXT,
            is_potential_duplicate   BOOLEAN DEFAULT 0,
            validation_flags        TEXT,
            FOREIGN KEY (employee_id) REFERENCES dim_employees(employee_id),
            FOREIGN KEY (category) REFERENCES dim_categories(category_name)
        )
    """)

    conn.commit()
    log.info("LOAD │ Database schema created.")

    # ── Populate dimension tables ────────────────────────────────
    departments = df["department"].unique()
    for dept in departments:
        cursor.execute("INSERT OR IGNORE INTO dim_departments (department_name) VALUES (?)", (dept,))

    # Load employee data if available
    emp_csv = os.path.join(DATA_DIR, "employees.csv")
    if os.path.exists(emp_csv):
        emp_df = pd.read_csv(emp_csv)
        emp_df.to_sql("dim_employees", conn, if_exists="replace", index=False)
        log.info(f"LOAD │ Loaded {len(emp_df)} employees into dim_employees")
    else:
        # Extract unique employees from expense data
        emp_data = df[["employee_id", "employee_name", "department"]].drop_duplicates("employee_id")
        emp_data.columns = ["employee_id", "employee_name", "department_name"]
        emp_data.to_sql("dim_employees", conn, if_exists="replace", index=False)
        log.info(f"LOAD │ Extracted {len(emp_data)} unique employees into dim_employees")

    categories = df["category"].unique()
    for cat in categories:
        cursor.execute("INSERT OR IGNORE INTO dim_categories (category_name) VALUES (?)", (cat,))

    conn.commit()
    log.info(f"LOAD │ Populated {len(departments)} departments, {len(categories)} categories")

    # ── Load fact table ──────────────────────────────────────────
    # Convert boolean columns for SQLite compatibility
    bool_cols = ["receipt_attached", "policy_compliant", "anomaly_flag",
                 "is_weekend_submission", "is_weekend_transaction",
                 "is_round_amount", "is_potential_duplicate"]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(int)

    # Convert dates to string for SQLite
    date_cols = ["transaction_date", "submission_date", "approval_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].dt.strftime("%Y-%m-%d")

    df.to_sql("fact_expenses", conn, if_exists="replace", index=False)
    log.info(f"LOAD │ Loaded {len(df):,} records into fact_expenses")

    # ── Create indexes for performance ───────────────────────────
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_dept ON fact_expenses(department)",
        "CREATE INDEX IF NOT EXISTS idx_category ON fact_expenses(category)",
        "CREATE INDEX IF NOT EXISTS idx_status ON fact_expenses(status)",
        "CREATE INDEX IF NOT EXISTS idx_txn_date ON fact_expenses(transaction_date)",
        "CREATE INDEX IF NOT EXISTS idx_employee ON fact_expenses(employee_id)",
        "CREATE INDEX IF NOT EXISTS idx_anomaly ON fact_expenses(anomaly_flag)",
        "CREATE INDEX IF NOT EXISTS idx_month ON fact_expenses(transaction_month)",
    ]
    for idx_sql in indexes:
        cursor.execute(idx_sql)

    conn.commit()
    log.info("LOAD │ Created 7 performance indexes")

    # ── Summary statistics ───────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM fact_expenses")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM dim_employees")
    emp_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM dim_departments")
    dept_count = cursor.fetchone()[0]

    conn.close()
    log.info(f"LOAD │ Database finalized: {total:,} expenses, {emp_count} employees, {dept_count} departments")
    log.info(f"LOAD │ Database size: {os.path.getsize(db_path) / 1024:.0f} KB")


# ══════════════════════════════════════════════════════════════════
#  PIPELINE ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════
def run_pipeline():
    """Execute the full ETL pipeline."""
    start = datetime.now()
    log.info("=" * 60)
    log.info("  NORTH STAR WORKLOAD OPTIMIZER — ETL PIPELINE")
    log.info("=" * 60)

    # ── Step 1: Extract ──
    if not os.path.exists(CSV_PATH):
        log.error(f"Source file not found: {CSV_PATH}")
        log.info("Run 'python data/generate_data.py' first to generate mock data.")
        sys.exit(1)

    df = extract(CSV_PATH)

    # ── Step 2: Validate ──
    validator = DataValidator()
    df = validator.validate(df)

    # ── Step 3: Clean ──
    df = clean_data(df)

    # ── Step 4: Feature Engineering ──
    df = engineer_features(df)

    # ── Step 5: Deduplicate ──
    df = deduplicate(df)

    # ── Step 6: Load ──
    load_to_sqlite(df, DB_PATH)

    # ── Pipeline Summary ──
    elapsed = (datetime.now() - start).total_seconds()
    log.info("=" * 60)
    log.info(f"  PIPELINE COMPLETE in {elapsed:.1f}s")
    log.info(f"  Records processed : {len(df):,}")
    log.info(f"  Anomalies flagged : {df['anomaly_flag'].sum()}")
    log.info(f"  Duplicates found  : {df['is_potential_duplicate'].sum()}")
    log.info(f"  Database location : {DB_PATH}")
    log.info("=" * 60)

    return df


# ── Entry Point ───────────────────────────────────────────────────
if __name__ == "__main__":
    run_pipeline()
    print("\n✅ ETL pipeline complete. Database ready for analysis.")
