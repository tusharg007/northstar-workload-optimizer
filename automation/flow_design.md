# Power Automate Flow Design — Mapping Document

## Overview

This document maps each component of the Python automation pipeline (`automation_flow.py`) to its equivalent Microsoft Power Automate action. It serves as a **TO-BE implementation blueprint** for deploying this logic in a production enterprise environment.

---

## Architecture Comparison

| Python Component | Power Automate Equivalent | Connector/Action |
|---|---|---|
| `ExpenseTrigger` | Automated Cloud Flow Trigger | "When a new item is created" (SharePoint) |
| `ExpenseValidator` | Condition + Parse JSON | "Parse JSON" + "Condition" actions |
| `AnomalyDetector` | Azure AI / Custom Connector | Azure ML endpoint or Logic App |
| `ApprovalRouter` | Approval Connector | "Start and wait for an approval" |
| `NotificationEngine` | Teams + Outlook Connectors | "Post message in Teams" / "Send email" |
| `AutomationPipeline` | Flow Orchestration | Parent flow with error handling |

---

## Step-by-Step Flow Mapping

### Step 1: Trigger — `ExpenseTrigger`

**Python Implementation:**
```python
class ExpenseTrigger:
    def poll_new_submissions(self, csv_path):
        # Reads new rows from CSV file
```

**Power Automate Equivalent:**
- **Trigger:** "When a new item is created" (SharePoint List)
- **Alternative Triggers:**
  - "When a new email arrives" (Outlook — for emailed expense receipts)
  - "When a new response is submitted" (Microsoft Forms)
  - "When a file is created in a folder" (OneDrive/SharePoint)

**Configuration:**
```
Site Address: https://contoso.sharepoint.com/sites/Finance
List Name: ExpenseSubmissions
Trigger Condition: @equals(triggerOutputs()?['body/Status'], 'New')
```

---

### Step 2: Validate — `ExpenseValidator`

**Python Implementation:**
```python
class ExpenseValidator:
    AMOUNT_LIMITS = {"Travel": 5000, "Meals": 500, ...}
    
    def validate(self, record):
        expense = ExpenseSubmission(**record)  # Pydantic validation
        # Check amount limits, receipt requirements, date logic
```

**Power Automate Equivalent:**
1. **"Parse JSON"** — Validate the incoming payload schema
2. **"Condition"** — Check each business rule:
   - `@greater(triggerOutputs()?['body/Amount'], 0)` — Amount positive
   - `@less(triggerOutputs()?['body/Amount'], variables('CategoryLimit'))` — Under limit
   - `@not(empty(triggerOutputs()?['body/Receipt']))` — Receipt attached
3. **"Compose"** — Aggregate validation results

**Error Handling:**
- If validation fails → "Send email" to submitter with rejection reason
- If validation passes → Continue to anomaly detection

---

### Step 3: Detect Anomalies — `AnomalyDetector`

**Python Implementation:**
```python
class AnomalyDetector:
    def detect(self, expense):
        # Rule 1: Z-score statistical outlier
        # Rule 2: Weekend transaction
        # Rule 3: Suspicious round amount
        # Rule 4: Missing receipt + high value
        # Rule 5: Duplicate pattern
```

**Power Automate Equivalent:**

**Option A — Built-in Logic:**
- Multiple **"Condition"** actions in a **"Switch"** control
- Each condition checks one anomaly rule
- Compose action aggregates all flags

**Option B — Azure AI (Recommended for Production):**
- **"HTTP"** action calling Azure ML endpoint
- Model trained on historical expense data
- Returns anomaly score + confidence level

**Option C — Custom Connector:**
- **Azure Logic App** with SQL query checking for duplicates
- **Azure Functions** running the Python detection logic as serverless API

```
HTTP POST: https://northstar-anomaly.azurewebsites.net/api/detect
Body: { expense_id, amount, category, transaction_date, ... }
Response: { is_anomalous, confidence_score, risk_level, flags[] }
```

---

### Step 4: Route for Approval — `ApprovalRouter`

**Python Implementation:**
```python
class ApprovalRouter:
    THRESHOLDS = [
        {"max_amount": 500,  "role": "Direct Manager",  "auto_approve": True},
        {"max_amount": 2000, "role": "Department Head",  "auto_approve": False},
        {"max_amount": 5000, "role": "Finance Director", "auto_approve": False},
        ...
    ]
```

**Power Automate Equivalent:**
1. **"Switch"** control on amount ranges:
   - Case 1 (≤$500): Auto-approve + update SharePoint status
   - Case 2 ($500–$2000): **"Start and wait for an approval"** → Department Head
   - Case 3 ($2000–$5000): **"Start and wait for an approval"** → Finance Director
   - Case 4 (>$5000): **Sequential approval** → Director → VP

2. **Approval Configuration:**
```
Approval Type: Approve/Reject - First to respond
Title: "Expense Approval: @{triggerOutputs()?['body/Category']} - $@{triggerOutputs()?['body/Amount']}"
Assigned To: @{outputs('Get_Manager')?['body/mail']}
Details: [Formatted expense summary with anomaly flags]
```

3. **Escalation for Anomalies:**
   - If `risk_level` = HIGH/CRITICAL → Override routing to Compliance
   - **"Parallel Branch"** to also notify Finance team

---

### Step 5: Notify — `NotificationEngine`

**Python Implementation:**
```python
class NotificationEngine:
    def generate_notification(self, expense, validation, anomaly, decision):
        # Generates JSON payload for Teams/Outlook
        payload = NotificationPayload(
            channel="teams",
            subject="⚠️ Review Required...",
            body="...",
            priority="high"
        )
```

**Power Automate Equivalent:**
1. **"Post message in a chat or channel" (Teams):**
   - Channel: Finance > #expense-approvals
   - Adaptive Card format with action buttons
   
2. **"Send an email (V2)" (Outlook):**
   - To: Approver email
   - Subject: Dynamic with expense details
   - Body: HTML formatted summary

3. **Adaptive Card Template (Teams):**
```json
{
  "type": "AdaptiveCard",
  "body": [
    {"type": "TextBlock", "text": "Expense Approval Required", "weight": "Bolder"},
    {"type": "FactSet", "facts": [
      {"title": "Employee", "value": "@{triggerOutputs()?['body/EmployeeName']}"},
      {"title": "Amount", "value": "$@{triggerOutputs()?['body/Amount']}"},
      {"title": "Risk Level", "value": "@{variables('RiskLevel')}"}
    ]}
  ],
  "actions": [
    {"type": "Action.Submit", "title": "Approve", "data": {"action": "approve"}},
    {"type": "Action.Submit", "title": "Reject", "data": {"action": "reject"}}
  ]
}
```

---

## Error Handling Strategy

| Error Type | Python Handling | Power Automate Handling |
|---|---|---|
| Validation failure | Return `ValidationResult(is_valid=False)` | "Configure run after" → Send rejection email |
| API timeout | Try/except with retry | "Retry Policy" (exponential backoff) |
| Approval timeout | N/A (mock) | "Timeout" property on approval action (72h) |
| System error | Logging + error status | "Scope" with "Configure run after" → alert IT |

---

## Environment Mapping

| Environment | Data Source | Approval System | Notification |
|---|---|---|---|
| **Development** (this project) | CSV files + SQLite | Python mock (console output) | JSON payload (printed) |
| **Staging** | SharePoint List | Power Automate (test flow) | Teams (test channel) |
| **Production** | Dataverse / Azure SQL | Power Automate (production) | Teams + Outlook + Mobile |

---

## Deployment Checklist

1. [ ] Create SharePoint List with expense submission schema
2. [ ] Configure Power Automate connection to SharePoint
3. [ ] Set up Azure AD groups for approver roles
4. [ ] Deploy anomaly detection model to Azure ML (or use rule-based Logic App)
5. [ ] Create Teams channels for notifications
6. [ ] Configure approval timeout policies (72h default)
7. [ ] Set up error notification email for IT support
8. [ ] Test with 50 sample submissions before go-live
9. [ ] Enable flow analytics for monitoring
10. [ ] Document escalation procedures for manual intervention
