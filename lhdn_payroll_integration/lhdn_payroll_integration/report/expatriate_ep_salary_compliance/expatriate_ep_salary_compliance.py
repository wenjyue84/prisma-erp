"""Expatriate EP Salary Compliance Report.

Lists all active EP holders, their EP category, latest gross salary,
the applicable ESD minimum, and compliance status (Compliant / Non-Compliant).

Also surfaces EP holders approaching expiry within 90 days.

US-142 acceptance criterion: "A report 'Expatriate EP Salary Compliance' lists all EP
holders, their category, current salary, category minimum, and compliance status."
"""
from datetime import date

import frappe
from frappe import _

from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_validator_service import (
    EP_POLICY_EFFECTIVE_DATE,
    get_ep_category_minimum,
)


def get_columns():
    return [
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 140,
        },
        {
            "label": _("Employee Name"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("EP Category"),
            "fieldname": "ep_category",
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "label": _("EP Number"),
            "fieldname": "ep_number",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("EP Expiry Date"),
            "fieldname": "ep_expiry_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Current Gross Salary (MYR)"),
            "fieldname": "current_salary",
            "fieldtype": "Currency",
            "width": 170,
        },
        {
            "label": _("Category Minimum (MYR)"),
            "fieldname": "category_minimum",
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "label": _("Compliance Status"),
            "fieldname": "compliance_status",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Days to Expiry"),
            "fieldname": "days_to_expiry",
            "fieldtype": "Int",
            "width": 110,
        },
    ]


def get_data(filters=None):
    today = date.today()

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "custom_ep_category": ["in", ["Cat I", "Cat II", "Cat III"]],
        },
        fields=[
            "name", "employee_name",
            "custom_ep_category", "custom_ep_number",
            "custom_ep_expiry_date",
        ],
    )

    rows = []
    for emp in employees:
        ep_category = emp.get("custom_ep_category") or ""
        ep_number = emp.get("custom_ep_number") or ""
        ep_expiry_raw = emp.get("custom_ep_expiry_date")

        ep_expiry = None
        days_to_expiry = None
        if ep_expiry_raw:
            if isinstance(ep_expiry_raw, str):
                from datetime import datetime
                ep_expiry = datetime.strptime(ep_expiry_raw, "%Y-%m-%d").date()
            else:
                ep_expiry = ep_expiry_raw
            days_to_expiry = (ep_expiry - today).days

        # Get latest salary from most recent submitted Salary Slip
        latest_slip = frappe.db.get_value(
            "Salary Slip",
            filters={"employee": emp.name, "docstatus": 1},
            fieldname=["gross_pay", "end_date"],
            order_by="end_date desc",
            as_dict=True,
        )
        current_salary = float(latest_slip.gross_pay) if latest_slip else 0.0
        slip_end_date = latest_slip.end_date if latest_slip else today

        if isinstance(slip_end_date, str):
            from datetime import datetime
            slip_end_date = datetime.strptime(slip_end_date, "%Y-%m-%d").date()

        category_minimum = get_ep_category_minimum(ep_category, slip_end_date)

        if slip_end_date >= EP_POLICY_EFFECTIVE_DATE:
            if current_salary >= category_minimum:
                status = "Compliant"
            elif current_salary == 0:
                status = "No Salary Slip"
            else:
                status = "Non-Compliant"
        else:
            status = "Not Yet Applicable"

        rows.append({
            "employee": emp.name,
            "employee_name": emp.employee_name,
            "ep_category": ep_category,
            "ep_number": ep_number,
            "ep_expiry_date": str(ep_expiry) if ep_expiry else "",
            "current_salary": current_salary,
            "category_minimum": category_minimum,
            "compliance_status": status,
            "days_to_expiry": days_to_expiry,
        })

    return sorted(rows, key=lambda r: r["compliance_status"])


def execute(filters=None):
    return get_columns(), get_data(filters)
