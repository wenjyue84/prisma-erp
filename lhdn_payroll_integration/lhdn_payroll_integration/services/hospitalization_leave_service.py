"""
Hospitalization Leave Compliance Service — Employment Act 1955 S.60F(2)
US-201: Track 60-Day Hospitalization Leave Quota Separately from Ordinary Sick Leave

EA S.60F provides TWO distinct entitlements:
  (1) Ordinary sick leave: 14 days (<2yr), 18 days (2-5yr), 22 days (>5yr) — S.60F(1)
  (2) Hospitalization leave: up to 60 days per year — S.60F(2)

These pools are SEPARATE; using hospitalization leave does NOT reduce ordinary sick leave.
"""

import frappe
from frappe import _

HOSPITALIZATION_LEAVE_TYPE = "Hospitalization Leave (EA)"
SICK_LEAVE_TYPE = "Sick Leave (EA)"
EA_HOSPITALIZATION_DAYS = 60
EA_ORDINARY_SICK_DAYS_TIERS = {
    "< 2 years": 14,
    "2-5 years": 18,
    "> 5 years": 22,
}


def validate_hospitalization_leave(doc, method=None):
    """Hook: validate Leave Application for Hospitalization Leave (EA) requirements."""
    if doc.leave_type != HOSPITALIZATION_LEAVE_TYPE:
        return

    _validate_required_hospitalization_fields(doc)
    _warn_if_balance_zero(doc)


def _validate_required_hospitalization_fields(doc):
    """Enforce that hospitalization-specific fields are provided."""
    if not doc.get("custom_hospitalization_discharge_date"):
        frappe.throw(
            _(
                "Hospitalization Leave (EA) requires the hospital discharge date. "
                "Please fill in 'Hospital Discharge Date' under the LHDN Leave Details section."
            ),
            title=_("Missing Discharge Date"),
        )

    if not doc.get("custom_medical_certificate_type"):
        frappe.throw(
            _(
                "Hospitalization Leave (EA) requires the medical certificate type. "
                "Please select either 'Hospitalization Certificate' or "
                "'Post-Hospitalization Medical Advice'."
            ),
            title=_("Missing Medical Certificate Type"),
        )


def _warn_if_balance_zero(doc):
    """Alert HR if the employee's Hospitalization Leave balance has reached zero."""
    employee = doc.get("employee")
    if not employee:
        return

    leave_year = _get_leave_year(doc)
    if not leave_year:
        return

    allocation = frappe.db.get_value(
        "Leave Allocation",
        {
            "employee": employee,
            "leave_type": HOSPITALIZATION_LEAVE_TYPE,
            "from_date": ["<=", doc.from_date],
            "to_date": [">=", doc.to_date or doc.from_date],
            "docstatus": 1,
        },
        ["total_leaves_allocated", "total_leaves_encashed"],
        as_dict=True,
    )
    if not allocation:
        return

    used = frappe.db.get_value(
        "Leave Ledger Entry",
        {
            "employee": employee,
            "leave_type": HOSPITALIZATION_LEAVE_TYPE,
            "docstatus": 1,
        },
        "sum(leaves)",
        as_dict=False,
    )
    used = abs(used or 0)
    remaining = (allocation.total_leaves_allocated or EA_HOSPITALIZATION_DAYS) - used
    if remaining <= 0:
        frappe.msgprint(
            _(
                "<b>Hospitalization Leave Balance Zero</b><br>"
                "Employee {0} has exhausted their {1}-day annual Hospitalization Leave (EA) quota. "
                "No further hospitalization leave is available for this leave year."
            ).format(employee, EA_HOSPITALIZATION_DAYS),
            title=_("Hospitalization Leave Balance Exhausted"),
            indicator="red",
        )


def _get_leave_year(doc):
    """Return the leave year start date for a Leave Application doc."""
    return doc.get("from_date")
