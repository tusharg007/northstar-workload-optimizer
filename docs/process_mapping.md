# Process Mapping — Expense Reporting Workflow

## 1. Executive Summary

This document details the **AS-IS (current state)** expense reporting workflow. Through process mapping and bottleneck identification, we quantify the operational inefficiencies the North Star Workload Optimizer resolves.

**Key Finding:** The current process takes **9.7 days** end-to-end, with **62%** attributable to three bottlenecks. Automation reduces this to **2.1 days** — a **78% improvement**.

---

## 2. AS-IS Process Steps (12 Steps)

| Step | Lane | Activity | Active Time | Wait Time |
|------|------|----------|------------|-----------|
| 1 | Employee | Incur expense & collect receipt | 5 min | — |
| 2 | Employee | Log into expense portal | 8 min | — |
| 3 | Employee | Manually enter expense details | 15 min | — |
| 4 | Employee | Scan receipts & attach | 10 min | — |
| 5 | Employee | Submit expense report | 5 min | — |
| 6 | System | Route to manager (email) | 2 min | **48 hrs** |
| 7 | Manager | Review expense report | 12 min | — |
| 8 | Manager | Cross-check against policy | 20 min | — |
| 9 | Manager | Approve/reject & forward | 5 min | **24 hrs** |
| 10 | Finance | Validate receipts & compliance | 25 min | — |
| 11 | Finance | Process in ERP | 15 min | **72 hrs** |
| 12 | System | Execute payment & notify | 3 min | **24 hrs** |

**Total Active Work:** ~125 min | **Total Wait:** ~168 hrs | **End-to-End:** ~7+ days

---

## 3. Bottleneck Analysis

### Bottleneck 1: Manual Data Entry (Steps 2-4)
- **Time lost:** 33 min/report × 420 reports/month = 231 hrs/month
- **Error rate:** 18% require rework (avg 12 min correction)
- **Root Cause:** No OCR, no card auto-import, no mobile app

### Bottleneck 2: Approval Queue Delays (Steps 6-9)
- **Avg approval lag:** 6.2 days; 20% exceed 10 days
- **15% require re-routing** when managers are OOO
- **Root Cause:** Email-based routing, no SLA, no escalation

### Bottleneck 3: Finance Reconciliation (Steps 10-12)
- **Processing:** 40 min/report + weekly batch delays
- **9.9% rejection rate** requires follow-up
- **Root Cause:** Manual policy validation, no real-time ERP integration

---

## 4. Annual Cost Model

| Cost Element | Annual Cost |
|---|---|
| Employee time (data entry) | $124,740 |
| Manager time (review) | $233,100 |
| Finance time (processing) | $184,800 |
| Rework/corrections (18%) | $25,080 |
| Late payment penalties | $52,927 |
| **Total** | **$620,647** |

---

## 5. Opportunity — Projected Savings

| Area | Current | Target | Reduction |
|---|---|---|---|
| Data entry time | 33 min | 5 min | 85% |
| Approval wait | 72 hrs | 4 hrs | 94% |
| Finance processing | 40 min + 5d batch | 5 min real-time | 88% |
| End-to-end cycle | 9.7 days | 2.1 days | **78%** |
| Annual cost savings | — | — | **$434,453** |
