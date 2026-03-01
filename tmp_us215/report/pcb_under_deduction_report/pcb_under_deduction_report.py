"""PCB Under-Deduction Compliance Report (US-215).

Monthly compliance report listing all Salary Slips flagged for PCB
under-deduction under Section 107A ITA 1967, along with their
acknowledgement status and documented justification.

Provides LHDN audit trail for employer liability review.
"""
import frappe
from frappe import _


def get_columns():
    return [
        {
            "label": _("Salary Slip"),
            "fieldname": "salary_slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 160,
        },
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 130,
        },
        {
            "label": _("Employee Name"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Payroll Period"),
            "fieldname": "payroll_period",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("PCB Amount (RM)"),
            "fieldname": "pcb_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 130,
        },
        {
            "label": _("Alert Rule"),
            "fieldname": "alert_rule",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Acknowledged"),
            "fieldname": "acknowledged",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": _("Acknowledgement By"),
            "fieldname": "acknowledged_by",
            "fieldtype": "Link",
            "options": "User",
            "width": 150,
        },
        {
            "label": _("Acknowledgement Date"),
            "fieldname": "acknowledged_at",
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "label": _("Reason / Justification"),
            "fieldname": "reason",
            "fieldtype": "Small Text",
            "width": 250,
        },
    ]


def get_filters():
    return [
        {
            "fieldname": "from_date",
            "label": _("From Date"),
            "fieldtype": "Date",
            "default": frappe.utils.add_months(frappe.utils.today(), -1),
            "reqd": 1,
        },
        {
            "fieldname": "to_date",
            "label": _("To Date"),
            "fieldtype": "Date",
            "default": frappe.utils.today(),
            "reqd": 1,
        },
        {
            "fieldname": "company",
            "label": _("Company"),
            "fieldtype": "Link",
            "options": "Company",
        },
        {
            "fieldname": "employee",
            "label": _("Employee"),
            "fieldtype": "Link",
            "options": "Employee",
        },
    ]


def get_data(filters) -> list:
    """Return rows for PCB under-deduction acknowledgement logs.

    Queries PCB Change Log for 'Under-Deduction Acknowledged' entries
    within the specified date range.
    """
    from_date = str(getattr(filters, "from_date", "") or (filters.get("from_date") if hasattr(filters, "get") else "") or "")
    to_date = str(getattr(filters, "to_date", "") or (filters.get("to_date") if hasattr(filters, "get") else "") or "")
    company = getattr(filters, "company", None) or (filters.get("company") if hasattr(filters, "get") else None)
    employee = getattr(filters, "employee", None) or (filters.get("employee") if hasattr(filters, "get") else None)

    log_filters = {
        "change_type": "Under-Deduction Acknowledged",
    }
    if from_date and to_date:
        log_filters["change_datetime"] = ["between", [
            from_date + " 00:00:00",
            to_date + " 23:59:59",
        ]]
    if company:
        log_filters["company"] = company
    if employee:
        log_filters["employee"] = employee

    logs = frappe.get_all(
        "PCB Change Log",
        filters=log_filters,
        fields=[
            "salary_slip",
            "employee",
            "employee_name",
            "payroll_period",
            "new_pcb_amount",
            "changed_by",
            "change_datetime",
            "reason",
        ],
        order_by="change_datetime desc",
    )

    rows = []
    for log in logs:
        rows.append({
            "salary_slip": log.salary_slip,
            "employee": log.employee,
            "employee_name": log.employee_name or "",
            "payroll_period": log.payroll_period or "",
            "pcb_amount": float(log.new_pcb_amount or 0),
            "alert_rule": "PCB_DROP_50_PCT / ZERO_PCB_ABOVE_THRESHOLD",
            "acknowledged": "Yes",
            "acknowledged_by": log.changed_by,
            "acknowledged_at": log.change_datetime,
            "reason": log.reason or "",
        })

    return rows


def execute(filters=None):
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        filters = dict(filters)
    filters = frappe._dict(filters)

    columns = get_columns()
    data = get_data(filters)
    return columns, data
