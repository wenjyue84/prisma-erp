"""Unstamped Employment Contracts — Script Report.

Lists all LHDN STAMPS Employment Contract records with status 'Pending'
(i.e. no stamp reference number and not legacy-stamped), along with
days since contract start.

US-150: LHDN STAMPS Employment Contract Digital Stamp Status Tracker.
Stamp amount: RM10 (fixed, First Schedule, Stamp Act 1949).
Portal: https://stamps.hasil.gov.my
"""
import frappe

from lhdn_payroll_integration.lhdn_payroll_integration.services.stamps_employment_contract_service import (
    STAMP_AMOUNT,
    STAMPS_PORTAL_URL,
    get_unstamped_contracts,
)


def get_columns():
    return [
        {
            "label": "Record",
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "LHDN STAMPS Employment Contract",
            "width": 160,
        },
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 150,
        },
        {
            "label": "Contract Start Date",
            "fieldname": "contract_start_date",
            "fieldtype": "Date",
            "width": 140,
        },
        {
            "label": "Days Since Start",
            "fieldname": "days_since_start",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Stamp Amount (MYR)",
            "fieldname": "stamp_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "STAMPS Portal",
            "fieldname": "stamps_portal",
            "fieldtype": "Data",
            "width": 200,
        },
    ]


def get_filters():
    return [
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
        },
    ]


def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")

    rows = get_unstamped_contracts(company=company)

    data = []
    for r in rows:
        data.append({
            "name": r["name"],
            "employee": r["employee"],
            "employee_name": r["employee_name"],
            "company": r["company"],
            "contract_start_date": r["contract_start_date"],
            "days_since_start": r["days_since_start"],
            "stamp_amount": STAMP_AMOUNT,
            "stamps_portal": STAMPS_PORTAL_URL,
        })

    return get_columns(), data
