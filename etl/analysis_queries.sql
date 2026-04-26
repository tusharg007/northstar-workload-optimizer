-- ══════════════════════════════════════════════════════════════════
--  NORTH STAR WORKLOAD OPTIMIZER — ANALYTICAL QUERIES
--  5 SQL Window Function Queries for Expense Pattern Analysis
-- ══════════════════════════════════════════════════════════════════


-- ──────────────────────────────────────────────────────────────────
-- QUERY 1: Cumulative Running Total by Department
-- Purpose : Track how expense spending accumulates month-over-month
--           within each department to identify budget burn patterns.
-- Window  : SUM() OVER (PARTITION BY ... ORDER BY ...)
-- ──────────────────────────────────────────────────────────────────

SELECT
    department,
    transaction_month,
    COUNT(*)                                                    AS num_transactions,
    ROUND(SUM(amount), 2)                                       AS monthly_total,
    ROUND(
        SUM(SUM(amount)) OVER (
            PARTITION BY department
            ORDER BY transaction_month
        ), 2
    )                                                           AS cumulative_total,
    ROUND(
        AVG(SUM(amount)) OVER (
            PARTITION BY department
            ORDER BY transaction_month
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ), 2
    )                                                           AS running_avg
FROM fact_expenses
GROUP BY department, transaction_month
ORDER BY department, transaction_month;


-- ──────────────────────────────────────────────────────────────────
-- QUERY 2: Approval Lag Ranking within Each Department
-- Purpose : Identify the slowest-approved expenses per department
--           to pinpoint approval bottlenecks and outlier approvers.
-- Window  : RANK() OVER (PARTITION BY ... ORDER BY ...)
-- ──────────────────────────────────────────────────────────────────

WITH ranked_expenses AS (
    SELECT
        expense_id,
        employee_name,
        department,
        category,
        amount,
        approval_lag_days,
        approver_name,
        status,
        RANK() OVER (
            PARTITION BY department
            ORDER BY approval_lag_days DESC
        )                                                       AS lag_rank,
        DENSE_RANK() OVER (
            PARTITION BY department
            ORDER BY approval_lag_days DESC
        )                                                       AS lag_dense_rank,
        ROUND(
            PERCENT_RANK() OVER (
                PARTITION BY department
                ORDER BY approval_lag_days
            ) * 100, 1
        )                                                       AS percentile
    FROM fact_expenses
    WHERE approval_lag_days IS NOT NULL
)
SELECT *
FROM ranked_expenses
WHERE lag_rank <= 10
ORDER BY department, lag_rank;


-- ──────────────────────────────────────────────────────────────────
-- QUERY 3: Month-over-Month Expense Change (LAG Analysis)
-- Purpose : Compare each month's total spending to the previous month
--           to detect sudden spikes or drops by department.
-- Window  : LAG() OVER (PARTITION BY ... ORDER BY ...)
-- ──────────────────────────────────────────────────────────────────

WITH monthly_totals AS (
    SELECT
        department,
        transaction_month,
        ROUND(SUM(amount), 2)                                   AS monthly_total,
        COUNT(*)                                                AS num_transactions
    FROM fact_expenses
    GROUP BY department, transaction_month
)
SELECT
    department,
    transaction_month,
    monthly_total,
    num_transactions,
    LAG(monthly_total, 1) OVER (
        PARTITION BY department
        ORDER BY transaction_month
    )                                                           AS prev_month_total,
    ROUND(
        monthly_total - COALESCE(
            LAG(monthly_total, 1) OVER (
                PARTITION BY department
                ORDER BY transaction_month
            ), monthly_total
        ), 2
    )                                                           AS mom_change,
    CASE
        WHEN LAG(monthly_total, 1) OVER (
            PARTITION BY department
            ORDER BY transaction_month
        ) IS NULL THEN NULL
        ELSE ROUND(
            (monthly_total - LAG(monthly_total, 1) OVER (
                PARTITION BY department
                ORDER BY transaction_month
            )) / LAG(monthly_total, 1) OVER (
                PARTITION BY department
                ORDER BY transaction_month
            ) * 100, 1
        )
    END                                                         AS mom_pct_change,
    LEAD(monthly_total, 1) OVER (
        PARTITION BY department
        ORDER BY transaction_month
    )                                                           AS next_month_total
FROM monthly_totals
ORDER BY department, transaction_month;


-- ──────────────────────────────────────────────────────────────────
-- QUERY 4: 3-Month Rolling Average by Category
-- Purpose : Smooth out volatile monthly spending to identify
--           underlying trends per expense category.
-- Window  : AVG() OVER (... ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
-- ──────────────────────────────────────────────────────────────────

WITH category_monthly AS (
    SELECT
        category,
        transaction_month,
        ROUND(SUM(amount), 2)                                   AS monthly_total,
        COUNT(*)                                                AS num_transactions,
        ROUND(AVG(amount), 2)                                   AS avg_per_transaction
    FROM fact_expenses
    GROUP BY category, transaction_month
)
SELECT
    category,
    transaction_month,
    monthly_total,
    num_transactions,
    avg_per_transaction,
    ROUND(
        AVG(monthly_total) OVER (
            PARTITION BY category
            ORDER BY transaction_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2
    )                                                           AS rolling_3m_avg,
    ROUND(
        AVG(monthly_total) OVER (
            PARTITION BY category
            ORDER BY transaction_month
            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
        ), 2
    )                                                           AS rolling_6m_avg,
    ROUND(
        monthly_total - AVG(monthly_total) OVER (
            PARTITION BY category
            ORDER BY transaction_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ), 2
    )                                                           AS deviation_from_3m_avg
FROM category_monthly
ORDER BY category, transaction_month;


-- ──────────────────────────────────────────────────────────────────
-- QUERY 5: Anomaly Percentile Ranking by Category
-- Purpose : Calculate the percentile rank of each expense amount
--           within its category to flag statistical outliers and
--           support anomaly detection.
-- Window  : PERCENT_RANK() OVER (PARTITION BY ... ORDER BY ...)
--           NTILE() OVER (PARTITION BY ... ORDER BY ...)
-- ──────────────────────────────────────────────────────────────────

WITH expense_percentiles AS (
    SELECT
        expense_id,
        employee_name,
        department,
        category,
        amount,
        confidence_score,
        anomaly_flag,
        anomaly_type,
        ROUND(
            PERCENT_RANK() OVER (
                PARTITION BY category
                ORDER BY amount
            ) * 100, 2
        )                                                       AS percentile_rank,
        NTILE(4) OVER (
            PARTITION BY category
            ORDER BY amount
        )                                                       AS quartile,
        NTILE(10) OVER (
            PARTITION BY category
            ORDER BY amount
        )                                                       AS decile,
        amount - AVG(amount) OVER (PARTITION BY category)       AS deviation_from_cat_avg,
        ROUND(
            (amount - AVG(amount) OVER (PARTITION BY category)) /
            NULLIF(
                -- Manual stddev calculation for SQLite compatibility
                SQRT(AVG(amount * amount) OVER (PARTITION BY category) -
                     AVG(amount) OVER (PARTITION BY category) *
                     AVG(amount) OVER (PARTITION BY category)),
                0
            ), 3
        )                                                       AS z_score_approx
    FROM fact_expenses
)
SELECT *
FROM expense_percentiles
WHERE percentile_rank >= 95      -- Top 5% most expensive per category
   OR anomaly_flag = 1           -- All flagged anomalies
ORDER BY category, percentile_rank DESC;
