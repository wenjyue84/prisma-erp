"""
US-087: Employee Self-Service Portal API

Whitelisted API methods for the employee self-service portal.
Employees can view payslips, download EA forms, check YTD earnings,
and submit TP1 relief declarations online.

All methods enforce that employees can only access their own records
via frappe.session.user validation.
"""

import json
import frappe
from frappe import _
from frappe.utils import nowdate, getdate


def _get_employee_for_user():
    """Return the Employee name linked to the current session user.

    Raises:
        frappe.PermissionError: If no Employee record is linked to the user.
    """
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw(
            _("No Employee record found for your user account."),
            frappe.PermissionError,
        )
    return employee


def _check_employee_permission(employee):
    """Ensure the logged-in user is only accessing their own employee record.

    Args:
        employee (str): Employee name to validate access for.

    Raises:
        frappe.PermissionError: If the employee does not match the session user.
    """
    my_employee = _get_employee_for_user()
    if employee != my_employee:
        frappe.throw(
            _("You are not permitted to access other employees' records."),
            frappe.PermissionError,
        )


@frappe.whitelist()
def get_my_payslips():
    """Return all submitted Salary Slips for the logged-in employee.

    Returns:
        list[dict]: Salary Slip records with key financial fields.
    """
    employee = _get_employee_for_user()
    slips = frappe.db.get_list(
        "Salary Slip",
        filters={"employee": employee, "docstatus": 1},
        fields=[
            "name",
            "employee",
            "employee_name",
            "start_date",
            "end_date",
            "gross_pay",
            "net_pay",
            "total_deduction",
        ],
        order_by="end_date desc",
    )
    return slips


@frappe.whitelist()
def get_my_ea_forms():
    """Return available EA form tax years for the logged-in employee.

    Returns:
        list[dict]: List of dicts with 'tax_year' key for each year that has
            submitted Salary Slips.
    """
    employee = _get_employee_for_user()
    years = frappe.db.sql(
        """
        SELECT DISTINCT YEAR(end_date) AS tax_year
        FROM `tabSalary Slip`
        WHERE employee = %(employee)s AND docstatus = 1
        ORDER BY tax_year DESC
        """,
        {"employee": employee},
        as_dict=True,
    )
    return years


@frappe.whitelist()
def get_my_ytd_summary():
    """Return year-to-date earnings summary for the logged-in employee.

    Returns:
        dict: Aggregated YTD gross, net, deductions, and slip count.
    """
    employee = _get_employee_for_user()
    today = nowdate()
    year_start = str(getdate(today).year) + "-01-01"

    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(gross_pay), 0) AS ytd_gross,
            COALESCE(SUM(net_pay), 0) AS ytd_net,
            COALESCE(SUM(total_deduction), 0) AS ytd_deductions,
            COUNT(*) AS slip_count
        FROM `tabSalary Slip`
        WHERE employee = %(employee)s
          AND docstatus = 1
          AND end_date >= %(year_start)s
          AND end_date <= %(today)s
        """,
        {"employee": employee, "year_start": year_start, "today": today},
        as_dict=True,
    )
    if result:
        return result[0]
    return {"ytd_gross": 0, "ytd_net": 0, "ytd_deductions": 0, "slip_count": 0}


@frappe.whitelist()
def get_my_tp1_declarations():
    """Return current-year TP1 relief declarations for the logged-in employee.

    Returns:
        list[dict]: Employee TP1 Relief records for the current tax year.
    """
    employee = _get_employee_for_user()
    year = getdate(nowdate()).year
    records = frappe.db.get_list(
        "Employee TP1 Relief",
        filters={"employee": employee, "tax_year": year},
        fields=[
            "name",
            "employee",
            "tax_year",
            "total_reliefs",
            "self_relief",
            "spouse_relief",
            "child_relief_normal",
            "child_relief_disabled",
            "life_insurance",
            "medical_insurance",
            "education_fees_self",
            "lifestyle_expenses",
            "epf_employee",
        ],
    )
    return records


@frappe.whitelist()
def submit_tp1_form(data):
    """Create or update an Employee TP1 Relief record for the logged-in employee.

    Args:
        data (dict|str): TP1 relief field values. Must include 'tax_year'.
            If a string, will be JSON-decoded.

    Returns:
        dict: {'action': 'created'|'updated', 'name': <doc name>}
    """
    if isinstance(data, str):
        data = json.loads(data)

    employee = _get_employee_for_user()
    tax_year = data.get("tax_year", getdate(nowdate()).year)

    _ALLOWED_FIELDS = [
        "self_relief",
        "spouse_relief",
        "child_relief_normal",
        "child_relief_disabled",
        "life_insurance",
        "medical_insurance",
        "education_fees_self",
        "sspn",
        "childcare_fees",
        "lifestyle_expenses",
        "prs_contribution",
        "serious_illness_expenses",
        "parents_medical",
        "housing_loan_interest_500k",
        "housing_loan_interest_750k",
        "disability_self",
        "disability_spouse",
        "socso_employee",
        "epf_employee",
        "annual_zakat",
    ]

    existing = frappe.db.get_value(
        "Employee TP1 Relief",
        {"employee": employee, "tax_year": tax_year},
        "name",
    )

    if existing:
        doc = frappe.get_doc("Employee TP1 Relief", existing)
        for field in _ALLOWED_FIELDS:
            if field in data:
                setattr(doc, field, data[field])
        doc.save()
        return {"action": "updated", "name": doc.name}
    else:
        doc = frappe.new_doc("Employee TP1 Relief")
        doc.employee = employee
        doc.tax_year = tax_year
        for field in _ALLOWED_FIELDS:
            if field in data:
                setattr(doc, field, data[field])
        doc.insert()
        return {"action": "created", "name": doc.name}
