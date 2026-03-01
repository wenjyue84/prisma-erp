"""Contracts Pending Stamping — Script Report.

Lists all employees with employment contracts that are pending stamping via
e-Duti Setem (MyTax) under the Stamp Duty Self-Assessment System (SAS)
mandatory from 1 January 2026.

Fixed stamp duty: RM10 per contract (Item 4, First Schedule, Stamp Act 1949).
Exemption: gross monthly salary <= RM3,000/month (Finance Bill 2025).
Deadline: 30 days from contract signing date.

US-175: Track Employment Contract Stamp Duty Compliance via e-Duti Setem MyTax.
"""
import frappe
from frappe.utils import getdate

from lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service import (
    get_contracts_pending_stamping,
    STAMP_DUTY_AMOUNT,
    STAMPING_DEADLINE_DAYS,
)


def get_columns():
    return [
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
            "label": "Contract Date",
            "fieldname": "contract_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Gross Salary (MYR/mo)",
            "fieldname": "gross_salary",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "Days Since Signing",
            "fieldname": "days_elapsed",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Overdue?",
            "fieldname": "is_overdue_label",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "Days Overdue",
            "fieldname": "days_overdue",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": "Est. Penalty (MYR)",
            "fieldname": "penalty_est",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
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
        {
            "label": "Show Only Overdue",
            "fieldname": "overdue_only",
            "fieldtype": "Check",
            "default": 0,
        },
    ]


def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")
    overdue_only = filters.get("overdue_only", 0)

    rows = get_contracts_pending_stamping(company=company)

    if overdue_only:
        rows = [r for r in rows if r["is_overdue"]]

    data = []
    for r in rows:
        data.append(
            {
                "employee": r["employee"],
                "employee_name": r["employee_name"],
                "company": r["company"],
                "contract_date": r["contract_date"],
                "gross_salary": r["gross_salary"],
                "days_elapsed": r["days_elapsed"],
                "is_overdue_label": "Yes" if r["is_overdue"] else "No",
                "days_overdue": r["days_overdue"],
                "penalty_est": r["penalty_est"],
            }
        )

    columns = get_columns()
    return columns, data
