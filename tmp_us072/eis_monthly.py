"""EIS Monthly Contribution Report Script Report.

Generates the monthly EIS (Sistem Insurans Pekerjaan) contribution schedule
listing each employee's wages, employee EIS, employer EIS and total
for a given month/year.

Columns: Employee Name, NRIC, Wages, EIS Employee, EIS Employer, Total, EIS Warning
Sources: Submitted Salary Slips (docstatus=1) with EIS deduction/earning lines.

US-075: Added EIS ceiling (RM6,000, October 2024) and age/foreign worker exemption validation.
  - 0.2% employee + 0.2% employer on wages capped at RM6,000
  - Foreign workers: not covered (EIS amount must be zero)
  - Age < 18 or >= 60: exempt (EIS amount must be zero)
"""
import frappe
from frappe.utils import flt

from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
    EIS_WAGE_CEILING,
    EIS_RATE,
)

_EIS_EMPLOYEE_COMPONENTS = {"EIS", "EIS Employee", "EIS - Employee"}
_EIS_EMPLOYER_COMPONENTS = {"EIS - Employer", "EIS Employer"}

EIS_VALIDATION_TOLERANCE = 0.05  # 5% tolerance


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
            "label": "Salary Slip",
            "fieldname": "salary_slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 160,
        },
        {
            "label": "EIS Warning",
            "fieldname": "eis_warning",
            "fieldtype": "Data",
            "width": 320,
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


def get_eis_validation_warning(wages, eis_employee, eis_employer, is_exempt, exempt_reason=""):
    """Return warning string for EIS amount deviations or incorrect exemptions.

    Args:
        wages: Monthly wages in MYR.
        eis_employee: Actual employee EIS deducted.
        eis_employer: Actual employer EIS contributed.
        is_exempt: True if employee is exempt (foreign/age).
        exempt_reason: Human-readable exemption reason.

    Returns:
        Warning string, or empty string if correct.
    """
    eis_employee = flt(eis_employee)
    eis_employer = flt(eis_employer)

    if is_exempt:
        # Exempt employees must have zero EIS
        if eis_employee > 0 or eis_employer > 0:
            return (
                f"EIS incorrectly charged: employee is exempt ({exempt_reason}) but "
                f"EIS deducted (employee: RM{eis_employee:.2f}, employer: RM{eis_employer:.2f}). "
                f"EIS should be RM0.00 for exempt employees."
            )
        return ""

    # Non-exempt: validate against ceiling and rate
    wages = flt(wages)
    if wages <= 0:
        return ""

    insured_wages = min(wages, EIS_WAGE_CEILING)
    expected_amount = flt(insured_wages * EIS_RATE, 2)

    warnings = []
    for label, actual in [("Employee EIS", eis_employee), ("Employer EIS", eis_employer)]:
        if expected_amount > 0:
            deviation = abs(actual - expected_amount) / expected_amount
            if deviation > EIS_VALIDATION_TOLERANCE:
                warnings.append(
                    f"{label}: expected RM{expected_amount:.2f} "
                    f"(wages capped at RM{insured_wages:,.0f} × {EIS_RATE * 100:.1f}%), "
                    f"actual RM{actual:.2f} ({deviation * 100:.1f}% deviation)"
                )

    return "; ".join(warnings)


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
            COALESCE(e.custom_is_non_resident, 0)           AS is_foreign,
            COALESCE(e.date_of_birth, NULL)                 AS date_of_birth,
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
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(
        emp_placeholders=emp_placeholders,
        emr_placeholders=emr_placeholders,
        where=where,
    )

    rows = frappe.db.sql(sql, values, as_dict=True)

    from datetime import date as _date
    today = _date.today()

    result = []
    for row in rows:
        row["total_eis"] = (row.get("eis_employee") or 0) + (row.get("eis_employer") or 0)

        # Determine exemption
        is_foreign = bool(row.get("is_foreign"))
        dob = row.get("date_of_birth")
        age = None
        if dob:
            age = (today - dob).days // 365

        is_exempt = False
        exempt_reason = ""
        if is_foreign:
            is_exempt = True
            exempt_reason = "foreign worker"
        elif age is not None and age < 18:
            is_exempt = True
            exempt_reason = f"age {age} (under 18)"
        elif age is not None and age >= 60:
            is_exempt = True
            exempt_reason = f"age {age} (60 or above)"

        row["eis_warning"] = get_eis_validation_warning(
            row.get("wages", 0),
            row.get("eis_employee", 0),
            row.get("eis_employer", 0),
            is_exempt=is_exempt,
            exempt_reason=exempt_reason,
        )

        # Only include rows with EIS or a warning to surface
        if row.get("eis_employee") or row.get("eis_employer") or row.get("eis_warning"):
            result.append(row)

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
