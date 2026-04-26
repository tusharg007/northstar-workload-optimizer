# DAX Measures — North Star Workload Optimizer Dashboard

## Overview

This document contains all DAX measures used in the Power BI dashboard, with detailed explanations of the business logic, calculation methodology, and intended visualization context.

---

## Measure 1: Total Expenses YTD

**Purpose:** Calculate the cumulative total expense amount for the current year-to-date, enabling comparison with prior year and budget targets.

```dax
Total Expenses YTD = 
CALCULATE(
    SUM(fact_expenses[amount]),
    DATESYTD('Calendar'[Date])
)
```

**Explanation:**
- `SUM(fact_expenses[amount])` — aggregates all expense amounts
- `DATESYTD('Calendar'[Date])` — filters the Calendar table to include only dates from January 1 to the current date within the selected year
- Requires a Calendar/Date dimension table with a continuous date range
- Responds to slicer selections (department, category, status)

**Used in:** KPI Card on Executive Summary page

---

## Measure 2: Average Approval Lag (Days)

**Purpose:** Calculate the mean number of days between expense submission and approval, a key operational efficiency metric.

```dax
Avg Approval Lag = 
AVERAGE(fact_expenses[approval_lag_days])
```

**Conditional Formatting Variant:**
```dax
Approval Lag Color = 
VAR AvgLag = [Avg Approval Lag]
RETURN
    SWITCH(
        TRUE(),
        AvgLag <= 3, "#2ECC71",    -- Green: Fast
        AvgLag <= 7, "#F39C12",    -- Amber: Acceptable
        AvgLag <= 14, "#E74C3C",   -- Red: Slow
        "#8E44AD"                   -- Purple: Critical
    )
```

**Explanation:**
- Simple average of the `approval_lag_days` column
- The color variant enables conditional formatting in KPI cards
- Target: ≤ 3 days (industry best practice for automated workflows)

**Used in:** KPI Card + Approval Lag Histogram on Approval Pipeline page

---

## Measure 3: Anomaly Rate %

**Purpose:** Calculate the percentage of expense submissions flagged as anomalous by the detection engine.

```dax
Anomaly Rate % = 
DIVIDE(
    COUNTROWS(
        FILTER(fact_expenses, fact_expenses[anomaly_flag] = 1)
    ),
    COUNTROWS(fact_expenses),
    0
) * 100
```

**Explanation:**
- `FILTER` isolates rows where `anomaly_flag = 1` (TRUE in SQLite is stored as 1)
- `DIVIDE` handles division-by-zero gracefully (returns 0 if no rows)
- Multiplied by 100 for percentage display
- Expected range: 8–15% based on simulated data

**Used in:** KPI Card + Anomaly Flag Table on Anomaly Detection page

---

## Measure 4: Policy Compliance Rate %

**Purpose:** Track the percentage of expenses that comply with company policy, a critical governance metric.

```dax
Policy Compliance % = 
DIVIDE(
    COUNTROWS(
        FILTER(fact_expenses, fact_expenses[policy_compliant] = 1)
    ),
    COUNTROWS(fact_expenses),
    0
) * 100
```

**Explanation:**
- Same pattern as Anomaly Rate but for `policy_compliant` field
- Target: >95% compliance rate
- Can be sliced by department to identify training needs

**Used in:** KPI Card on Executive Summary + Department Deep Dive pages

---

## Measure 5: Month-over-Month Growth %

**Purpose:** Calculate the percentage change in total expenses compared to the previous month, enabling trend detection.

```dax
MoM Growth % = 
VAR CurrentMonth = 
    CALCULATE(
        SUM(fact_expenses[amount]),
        DATESMTD('Calendar'[Date])
    )
VAR PreviousMonth = 
    CALCULATE(
        SUM(fact_expenses[amount]),
        DATEADD('Calendar'[Date], -1, MONTH)
    )
RETURN
    DIVIDE(
        CurrentMonth - PreviousMonth,
        PreviousMonth,
        0
    ) * 100
```

**Explanation:**
- `DATESMTD` calculates the current month's running total
- `DATEADD(..., -1, MONTH)` shifts context to the previous month
- `DIVIDE` computes percentage change with zero-division protection
- Positive values = spending increase; Negative = spending decrease

**Used in:** Time-trend line chart on Executive Summary page

---

## Measure 6: Expense Count by Status

**Purpose:** Count expenses filtered by a specific status for donut/bar chart visualization.

```dax
Approved Count = 
CALCULATE(
    COUNTROWS(fact_expenses),
    fact_expenses[status] = "Approved"
)

Pending Count = 
CALCULATE(
    COUNTROWS(fact_expenses),
    fact_expenses[status] = "Pending"
)

Rejected Count = 
CALCULATE(
    COUNTROWS(fact_expenses),
    fact_expenses[status] = "Rejected"
)
```

**Used in:** Status donut chart on Executive Summary page

---

## Measure 7: Top N Spenders (Dynamic)

**Purpose:** Dynamically rank employees by total spending and highlight top spenders.

```dax
Employee Rank = 
RANKX(
    ALL(fact_expenses[employee_name]),
    [Total Expenses YTD],
    ,
    DESC,
    DENSE
)

Is Top 10 Spender = 
IF([Employee Rank] <= 10, 1, 0)
```

**Explanation:**
- `RANKX` ranks each employee by their total YTD spending
- `ALL` ensures ranking considers all employees, not just filtered ones
- `DENSE` ranking ensures no gaps in rank numbers
- `Is Top 10 Spender` is a boolean flag for conditional formatting

**Used in:** Top Spenders table on Department Deep Dive page

---

## Calendar Table (Required)

The following DAX creates the required Calendar dimension:

```dax
Calendar = 
ADDCOLUMNS(
    CALENDARAUTO(),
    "Year", YEAR([Date]),
    "Month", FORMAT([Date], "MMMM"),
    "MonthNumber", MONTH([Date]),
    "Quarter", "Q" & FORMAT([Date], "Q"),
    "YearMonth", FORMAT([Date], "YYYY-MM"),
    "WeekDay", FORMAT([Date], "dddd"),
    "WeekDayNumber", WEEKDAY([Date], 2),
    "IsWeekend", IF(WEEKDAY([Date], 2) >= 6, TRUE(), FALSE())
)
```

---

## Power Query (M) — Data Connection

To connect Power BI to the SQLite database:

```m
let
    Source = Odbc.DataSources(),
    // Alternatively, use the SQLite ODBC driver:
    // Source = Odbc.Query("Driver={SQLite3 ODBC Driver};Database=C:\path\to\northstar.db;", "SELECT * FROM fact_expenses")
    
    // Recommended: Import from CSV for portability
    Source = Csv.Document(
        File.Contents("C:\path\to\northstar-workload-optimizer\data\expenses.csv"),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    ChangedTypes = Table.TransformColumnTypes(PromotedHeaders, {
        {"amount", type number},
        {"transaction_date", type date},
        {"submission_date", type date},
        {"approval_date", type date},
        {"approval_lag_days", Int64.Type},
        {"submission_lag_days", Int64.Type},
        {"confidence_score", type number},
        {"receipt_attached", type logical},
        {"policy_compliant", type logical},
        {"anomaly_flag", type logical}
    })
in
    ChangedTypes
```

---

## Dashboard Page Layout

### Page 1: Executive Summary
| Visual | Type | Measures |
|--------|------|----------|
| Total Expenses | KPI Card | `Total Expenses YTD` |
| Avg Approval Lag | KPI Card | `Avg Approval Lag` |
| Anomaly Rate | KPI Card | `Anomaly Rate %` |
| Compliance Rate | KPI Card | `Policy Compliance %` |
| MoM Growth | KPI Card | `MoM Growth %` |
| Monthly Trend | Line Chart | Sum of Amount by Month |
| Status Breakdown | Donut Chart | Count by Status |

### Page 2: Department Deep Dive
| Visual | Type | Measures |
|--------|------|----------|
| Department Heatmap | Matrix | Amount by Dept × Category |
| Top Spenders | Table | Employee, Rank, Total |
| Dept Comparison | Clustered Bar | Amount by Department |

### Page 3: Anomaly Detection
| Visual | Type | Measures |
|--------|------|----------|
| Anomaly Flag Table | Table | Flagged records with details |
| Risk Distribution | Pie Chart | Count by Anomaly Type |
| Amount vs Confidence | Scatter Plot | Amount × Confidence Score |

### Page 4: Approval Pipeline
| Visual | Type | Measures |
|--------|------|----------|
| Approval Lag Histogram | Histogram | Distribution of lag days |
| Processing Timeline | Gantt-style | Submission → Approval flow |
| Speed Category | Stacked Bar | Fast/Normal/Slow/Critical |
