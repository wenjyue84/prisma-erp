"""EPF Borang A Monthly Contribution Schedule Script Report.

Generates the monthly EPF (KWSP) contribution schedule (Borang A)
listing each employee's wages, employee contribution, employer contribution
and total EPF for a given month/year.

CSV export is compatible with EPF i-Akaun upload format.

Columns: Employee Name, NRIC, EPF Member Number, Wages,
         Employee EPF, Employer EPF, Total Contribution, EPF Rate Warning
Sources: Submitted Salary Slips (docstatus=1) with EPF deduction/earning lines.

US-073: Added employer EPF rate validation against statutory rates.
  - 13% for employees earning <= RM5,000/month
  - 12% for employees earning > RM5,000/month
"""
import frappe
from frappe.utils import flt

from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
    calculate_epf_employer_rate,
    EPF_LOWER_SALARY_THRESHOLD,
)

# Salary component names used for EPF
_EPF_EMPLOYEE_COMPONENTS = {"EPF", "EPF Employee", "KWSP", "KWSP Employee"}
_EPF_EMPLOYER_COMPONENTS = {"EPF - Employer", "KWSP - Employer", "EPF Employer", "KWSP Employer"}

# Tolerance for employer EPF rate deviation (5%)
EPF_RATE_TOLERANCE = 0.05


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
            "label": "EPF Member Number",
            "fieldname": "epf_member_number",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Wages (MYR)",
            "fieldname": "wages",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "Employee EPF (MYR)",
            "fieldname": "employee_epf",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Employer EPF (MYR)",
            "fieldname": "employer_epf",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Total EPF (MYR)",
            "fieldname": "total_epf",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "Period",
            "fieldname": "period",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Salary Slip",
            "fieldname": "salary_slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 160,
        },
        {
            "label": "EPF Rate Warning",
            "fieldname": "epf_rate_warning",
            "fieldtype": "Data",
            "width": 300,
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


def get_epf_employer_rate_warning(wages, employer_epf):
    """Return warning if employer EPF deviates >5% from statutory rate.

    Args:
        wages: Monthly gross wages in MYR.
        employer_epf: Actual employer EPF amount contributed.

    Returns:
        Warning string, or empty string if within tolerance.
    """
    wages = flt(wages)
    employer_epf = flt(employer_epf)

    if wages <= 0:
        return ""

    expected_rate = calculate_epf_employer_rate(wages)
    expected_amount = flt(wages * expected_rate, 2)

    if expected_amount <= 0:
        return ""

    deviation = abs(employer_epf - expected_amount) / expected_amount
    if deviation > EPF_RATE_TOLERANCE:
        rate_pct = int(expected_rate * 100)
        threshold_note = (
            f"<= RM{EPF_LOWER_SALARY_THRESHOLD:,.0f}" if wages <= EPF_LOWER_SALARY_THRESHOLD
            else f"> RM{EPF_LOWER_SALARY_THRESHOLD:,.0f}"
        )
        return (
            f"EPF employer rate mismatch: wages RM{wages:,.2f} ({threshold_note}) "
            f"requires {rate_pct}% employer (RM{expected_amount:,.2f}); "
            f"actual RM{employer_epf:,.2f} ({deviation * 100:.1f}% deviation)."
        )
    return ""


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

    # Build IN clause for EPF component names
    emp_names = list(_EPF_EMPLOYEE_COMPONENTS)
    emr_names = list(_EPF_EMPLOYER_COMPONENTS)

    emp_placeholders = ", ".join([f"%(emp_comp_{i})s" for i in range(len(emp_names))])
    emr_placeholders = ", ".join([f"%(emr_comp_{i})s" for i in range(len(emr_names))])

    for i, n in enumerate(emp_names):
        values[f"emp_comp_{i}"] = n
    for i, n in enumerate(emr_names):
        values[f"emr_comp_{i}"] = n

    sql = """
        SELECT
            ss.name                                          AS salary_slip,
            ss.employee                                      AS employee,
            ss.employee_name                                 AS employee_name,
            COALESCE(e.custom_id_value, '')                 AS nric,
            COALESCE(e.custom_epf_member_number, '')        AS epf_member_number,
            ss.gross_pay                                     AS wages,
            COALESCE(SUM(CASE
                WHEN sd.salary_component IN ({emp_placeholders})
                     AND sd.parentfield = 'deductions'
                THEN sd.amount ELSE 0 END), 0)              AS employee_epf,
            COALESCE(SUM(CASE
                WHEN sd.salary_component IN ({emr_placeholders})
                THEN sd.amount ELSE 0 END), 0)              AS employer_epf,
            CONCAT(
                DATE_FORMAT(ss.start_date, '%%Y-%%m'),
                ' (', ss.start_date, ' - ', ss.end_date, ')'
            )                                                AS period
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e
            ON e.name = ss.employee
        LEFT JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parenttype = 'Salary Slip'
        {where}
        GROUP BY ss.name
        HAVING (employee_epf > 0 OR employer_epf > 0)
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(
        emp_placeholders=emp_placeholders,
        emr_placeholders=emr_placeholders,
        where=where,
    )

    rows = frappe.db.sql(sql, values, as_dict=True)

    for row in rows:
        row["total_epf"] = (row.get("employee_epf") or 0) + (row.get("employer_epf") or 0)
        row["epf_rate_warning"] = get_epf_employer_rate_warning(
            row.get("wages", 0),
            row.get("employer_epf", 0),
        )

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
