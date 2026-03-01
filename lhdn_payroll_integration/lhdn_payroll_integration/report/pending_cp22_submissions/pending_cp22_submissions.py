"""Pending CP22 Submissions Report (US-114).

Lists all Active employees with CP22 Submission Status = Pending,
showing days since hire and days remaining before the 30-day LHDN deadline.

Statutory basis: Income Tax Act 1967, Section 83(2).
LHDN mandatory e-CP22 on MyTax effective 1 September 2024.
"""
import frappe
from lhdn_payroll_integration.services.cp22_tracking_service import get_pending_cp22_employees


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


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
            "width": 180,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 150,
        },
        {
            "label": "Date of Joining",
            "fieldname": "date_of_joining",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Days Since Hire",
            "fieldname": "days_since_hire",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": "Days Remaining (30-day deadline)",
            "fieldname": "days_remaining",
            "fieldtype": "Int",
            "width": 200,
        },
        {
            "label": "CP22 Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_data(filters=None):
    rows = get_pending_cp22_employees()

    # Apply optional company filter
    if filters and filters.get("company"):
        rows = [r for r in rows if r["company"] == filters["company"]]

    return rows
