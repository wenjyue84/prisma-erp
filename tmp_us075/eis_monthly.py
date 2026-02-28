"""EIS Monthly Contribution Report Script Report.

Generates the monthly EIS (Sistem Insurans Pekerjaan) contribution schedule
listing each employee's wages, employee EIS, employer EIS and total
for a given month/year.

Columns: Employee Name, NRIC, Wages, EIS Employee, EIS Employer, Total, Warning
Sources: Submitted Salary Slips (docstatus=1) with EIS deduction/earning lines.

US-075: Validates each row against calculate_eis_contribution() and flags:
- Exempt employees incorrectly included (foreign workers, age <18 or >=60)
- Wrong ceiling (wages > RM6,000 not capped correctly)
"""
import frappe
from frappe.utils import flt, getdate

from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
    EIS_WAGE_CEILING,
    calculate_eis_contribution,
)

_EIS_EMPLOYEE_COMPONENTS = {"EIS", "EIS Employee", "EIS - Employee"}
_EIS_EMPLOYER_COMPONENTS = {"EIS - Employer", "EIS Employer"}

EIS_TOLERANCE = 0.05  # 5% tolerance for rounding differences


def get_eis_contribution_warning(wages, date_of_birth, is_foreign, actual_employee, actual_employer, payroll_date=None):
    """Return a warning string if the actual EIS amounts deviate from expected.

    Flags:
    - Exempt employee incorrectly included (foreign, age <18 or >=60)
    - Employee wages incorrectly calculated (wrong ceiling, wrong rate)

    Args:
        wages: Monthly gross wages in MYR.
        date_of_birth: datetime.date of employee's birth (or None).
        is_foreign: bool, True if employee is a foreign worker.
        actual_employee: Actual employee EIS deducted from salary slip.
        actual_employer: Actual employer EIS contributed.
        payroll_date: datetime.date for age calculation (defaults to today).

    Returns:
        Warning string, or empty string if correct.
    """
    from datetime import date as _date

    actual_employee = flt(actual_employee)
    actual_employer = flt(actual_employer)

    if date_of_birth is None:
        # Cannot validate without DOB — skip
        return ""

    if not isinstance(date_of_birth, _date):
        try:
            date_of_birth = getdate(date_of_birth)
        except Exception:
            return ""

    expected = calculate_eis_contribution(wages, date_of_birth, bool(is_foreign), payroll_date=payroll_date)

    expected_employee = expected["employee"]
    expected_employer = expected["employer"]

    # Case 1: employee should be exempt but has EIS deducted
    if expected_employee == 0.0 and expected_employer == 0.0:
        if actual_employee > 0 or actual_employer > 0:
            reason = "foreign worker" if is_foreign else "age exemption (<18 or >=60)"
            return (
                f"EIS exempt ({reason}) but EIS deducted: "
                f"employee=RM{actual_employee:.2f}, employer=RM{actual_employer:.2f}"
            )
        return ""

    # Case 2: contribution amount mismatch (wrong ceiling or rate)
    warnings = []
    if expected_employee > 0:
        deviation = abs(actual_employee - expected_employee) / expected_employee
        if deviation > EIS_TOLERANCE:
            warnings.append(
                f"employee EIS RM{actual_employee:.2f} (expected RM{expected_employee:.2f})"
            )

    if expected_employer > 0:
        deviation = abs(actual_employer - expected_employer) / expected_employer
        if deviation > EIS_TOLERANCE:
            warnings.append(
                f"employer EIS RM{actual_employer:.2f} (expected RM{expected_employer:.2f})"
            )

    if warnings:
        return "EIS mismatch: " + "; ".join(warnings) + f" [ceiling=RM{EIS_WAGE_CEILING:,.0f}]"

    return ""


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
            "label": "NRIC",
            "fieldname": "nric",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": "Wages (MYR)",
            "fieldname": "wages",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "EIS Employee (MYR)",
            "fieldname": "eis_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "EIS Employer (MYR)",
            "fieldname": "eis_employer",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Total EIS (MYR)",
            "fieldname": "total_eis",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "EIS Warning",
            "fieldname": "eis_contribution_warning",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": "Salary Slip",
            "fieldname": "salary_slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 160,
        },
    ]


def get_filters():
    current_month = frappe.utils.getdate().month
    current_year = frappe.utils.getdate().year
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 0,
        },
        {
            "fieldname": "month",
            "label": "Month",
            "fieldtype": "Select",
            "options": "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
            "default": str(current_month).zfill(2),
        },
        {
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Int",
            "default": current_year,
        },
    ]


def _build_conditions(filters):
    conditions = ["ss.docstatus = 1"]
    values = {}

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("month"):
        try:
            month_val = int(filters["month"])
        except (ValueError, TypeError):
            month_val = None
        if month_val:
            conditions.append("MONTH(ss.start_date) = %(month)s")
            values["month"] = month_val

    if filters.get("year"):
        try:
            year_val = int(filters["year"])
        except (ValueError, TypeError):
            year_val = None
        if year_val:
            conditions.append("YEAR(ss.start_date) = %(year)s")
            values["year"] = year_val

    where = "WHERE " + " AND ".join(conditions)
    return where, values


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    emp_names = list(_EIS_EMPLOYEE_COMPONENTS)
    emr_names = list(_EIS_EMPLOYER_COMPONENTS)

    emp_placeholders = ", ".join([f"%(eis_emp_{i})s" for i in range(len(emp_names))])
    emr_placeholders = ", ".join([f"%(eis_emr_{i})s" for i in range(len(emr_names))])

    for i, n in enumerate(emp_names):
        values[f"eis_emp_{i}"] = n
    for i, n in enumerate(emr_names):
        values[f"eis_emr_{i}"] = n

    sql = """
        SELECT
            ss.name                                          AS salary_slip,
            ss.employee                                      AS employee,
            ss.employee_name                                 AS employee_name,
            COALESCE(e.custom_id_value, '')                 AS nric,
            ss.gross_pay                                     AS wages,
            COALESCE(e.date_of_birth, NULL)                 AS date_of_birth,
            COALESCE(e.custom_is_foreign_worker, 0)         AS is_foreign,
            COALESCE(SUM(CASE
                WHEN sd.salary_component IN ({emp_placeholders})
                     AND sd.parentfield = 'deductions'
                THEN sd.amount ELSE 0 END), 0)              AS eis_employee,
            COALESCE(SUM(CASE
                WHEN sd.salary_component IN ({emr_placeholders})
                THEN sd.amount ELSE 0 END), 0)              AS eis_employer
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e
            ON e.name = ss.employee
        LEFT JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parenttype = 'Salary Slip'
        {where}
        GROUP BY ss.name
        HAVING (eis_employee > 0 OR eis_employer > 0)
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(
        emp_placeholders=emp_placeholders,
        emr_placeholders=emr_placeholders,
        where=where,
    )

    rows = frappe.db.sql(sql, values, as_dict=True)

    for row in rows:
        row["total_eis"] = (row.get("eis_employee") or 0) + (row.get("eis_employer") or 0)
        row["eis_contribution_warning"] = get_eis_contribution_warning(
            wages=row.get("wages", 0),
            date_of_birth=row.get("date_of_birth"),
            is_foreign=row.get("is_foreign", 0),
            actual_employee=row.get("eis_employee", 0),
            actual_employer=row.get("eis_employer", 0),
        )

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
