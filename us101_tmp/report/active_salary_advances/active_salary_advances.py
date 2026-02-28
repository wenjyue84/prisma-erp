"""Active Salary Advances Report (US-101).

Lists all employees with active salary advance loans, their outstanding balances,
scheduled monthly repayment, and projected clearance date.

Employment Act 1955 S.22-24 compliance report for HR.
"""
import frappe


def execute(filters=None):
    columns = _get_columns()
    data = _get_data(filters or {})
    return columns, data


def _get_columns():
    return [
        {
            "label": "Loan ID",
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Salary Advance Loan",
            "width": 180,
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
            "width": 160,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 140,
        },
        {
            "label": "Advance Date",
            "fieldname": "advance_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Advance Amount (RM)",
            "fieldname": "amount",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "label": "Monthly Repayment (RM)",
            "fieldname": "repayment_amount_per_period",
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "label": "Outstanding Balance (RM)",
            "fieldname": "outstanding_balance",
            "fieldtype": "Currency",
            "width": 170,
        },
        {
            "label": "Projected Clearance",
            "fieldname": "projected_clearance_date",
            "fieldtype": "Date",
            "width": 140,
        },
        {
            "label": "Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 100,
        },
    ]


def _get_data(filters):
    conditions = {}
    if filters.get("company"):
        conditions["company"] = filters["company"]
    if filters.get("employee"):
        conditions["employee"] = filters["employee"]
    if filters.get("status"):
        conditions["status"] = filters["status"]
    else:
        conditions["status"] = "Active"

    records = frappe.get_all(
        "Salary Advance Loan",
        filters=conditions,
        fields=[
            "name",
            "employee",
            "employee_name",
            "company",
            "advance_date",
            "amount",
            "repayment_amount_per_period",
            "outstanding_balance",
            "projected_clearance_date",
            "status",
        ],
        order_by="advance_date asc",
    )
    return records
