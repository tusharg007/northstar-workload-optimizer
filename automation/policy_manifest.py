"""Business-policy configuration executed by the deterministic engine."""

from __future__ import annotations

DECISION_ENGINE_VERSION = "northstar-expense-decision/1.0.0"
RISK_ENGINE_VERSION = "northstar-anomaly-risk/1.0.0"

CATEGORY_LIMITS = {
    "Travel": 5000,
    "Meals & Entertainment": 500,
    "Office Supplies": 300,
    "Software & Subscriptions": 2000,
    "Training & Development": 3000,
    "Client Entertainment": 2000,
    "Transportation": 800,
    "Telecommunications": 500,
    "Equipment": 5000,
    "Miscellaneous": 1000,
}

RECEIPT_REQUIRED_ABOVE = 75
DESCRIPTION_REQUIRED_ABOVE = 500
DESCRIPTION_MINIMUM_CHARACTERS = 5
REVIEW_REQUIRED_ABOVE = 2000

APPROVAL_TIERS = [
    {"maximum_amount": 500, "role": "Direct Manager", "level": 1, "auto_approve": True},
    {"maximum_amount": 2000, "role": "Department Head", "level": 2, "auto_approve": False},
    {"maximum_amount": 5000, "role": "Finance Director", "level": 3, "auto_approve": False},
    {"maximum_amount": None, "role": "VP / C-Suite", "level": 4, "auto_approve": False},
]


def policy_execution_manifest() -> dict[str, dict[str, dict]]:
    """Return stable rule keys and structured parameters actually executed."""
    return {
        "EXPENSE_SUBMISSION_REQUIREMENTS": {
            "CATEGORY_SPENDING_LIMITS": {
                "effect": "WARNING",
                "limits": CATEGORY_LIMITS,
                "operator": "greater_than",
            },
            "RECEIPT_REQUIRED_THRESHOLD": {
                "effect": "WARNING",
                "amount_greater_than": RECEIPT_REQUIRED_ABOVE,
                "receipt_attached": False,
            },
            "DESCRIPTION_REQUIRED_THRESHOLD": {
                "effect": "WARNING",
                "amount_greater_than": DESCRIPTION_REQUIRED_ABOVE,
                "minimum_trimmed_characters": DESCRIPTION_MINIMUM_CHARACTERS,
            },
            "FUTURE_TRANSACTION_DATE_REJECTED": {
                "effect": "ERROR",
                "transaction_date": "not_after_processing_date",
            },
        },
        "EXPENSE_APPROVAL_ROUTING": {
            "AMOUNT_APPROVAL_TIERS": {"tiers": APPROVAL_TIERS},
            "HIGH_RISK_ESCALATION_ROUTE": {
                "role": "Finance Director + Compliance",
                "risk_levels": ["HIGH", "CRITICAL"],
                "auto_approve": False,
                "minimum_level": 3,
            },
            "MEDIUM_RISK_REQUIRES_HUMAN": {
                "risk_levels": ["MEDIUM"],
                "auto_approve": False,
            },
            "REVIEW_REQUIRED_THRESHOLD": {
                "any": [
                    {"algorithmic_anomaly": True},
                    {"amount_greater_than": REVIEW_REQUIRED_ABOVE},
                ]
            },
        },
    }
