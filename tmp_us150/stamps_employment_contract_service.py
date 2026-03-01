"""Service layer for US-150: LHDN STAMPS Employment Contract tracking.

Provides helper functions for:
- Querying unstamped employment contracts
- Computing days since contract start
- Determining stamp compliance status
"""
from datetime import date

import frappe
from frappe.utils import getdate, today

STAMPS_PORTAL_URL = "https://stamps.hasil.gov.my"
STAMP_AMOUNT = 10.0
PRE_STAMPS_YEAR = 2021  # Contracts before 2021 may be legacy-stamped


def get_days_since_contract_start(contract_start_date):
    """Return the number of days elapsed since contract_start_date.

    Returns 0 if contract_start_date is None or in the future.
    """
    if not contract_start_date:
        return 0
    start = getdate(contract_start_date)
    today_date = getdate(today())
    delta = (today_date - start).days
    return max(delta, 0)


def is_legacy_contract(contract_start_date):
    """Return True if contract_start_date is before the STAMPS era (pre-2021)."""
    if not contract_start_date:
        return False
    return getdate(contract_start_date).year < PRE_STAMPS_YEAR


def get_unstamped_contracts(company=None):
    """Return a list of active employees with unstamped contracts.

    Filters:
    - LHDN STAMPS Employment Contract records with status = 'Pending'
    - legacy_stamped = 0 (legacy stamped contracts are suppressed)

    Each record includes days_since_start.

    Args:
        company (str, optional): Limit to a specific company.

    Returns:
        list[dict]: Sorted by days_since_start descending (most overdue first).
    """
    filters = {"status": "Pending", "legacy_stamped": 0}
    if company:
        filters["company"] = company

    records = frappe.get_all(
        "LHDN STAMPS Employment Contract",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "company",
            "contract_start_date",
            "stamp_reference_number",
            "stamp_date",
            "stamp_amount",
            "stamping_method",
            "legacy_stamped",
            "status",
        ],
    )

    results = []
    for r in records:
        days = get_days_since_contract_start(r.get("contract_start_date"))
        results.append({
            "name": r["name"],
            "employee": r["employee"],
            "employee_name": r.get("employee_name", ""),
            "company": r.get("company", ""),
            "contract_start_date": r.get("contract_start_date"),
            "stamp_reference_number": r.get("stamp_reference_number", ""),
            "stamp_amount": STAMP_AMOUNT,
            "stamping_method": r.get("stamping_method", ""),
            "status": r.get("status", "Pending"),
            "days_since_start": days,
        })

    results.sort(key=lambda x: x["days_since_start"], reverse=True)
    return results
