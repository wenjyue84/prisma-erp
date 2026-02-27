"""HRDF Monthly Levy Script Report.

Generates the monthly HRDF (Pembangunan Sumber Manusia Berhad) levy
liability schedule listing each employee's wages and calculated HRDF
levy based on the Company's custom_hrdf_levy_rate setting.

Columns: Employee, Employee Name, Wages, HRDF Rate, HRDF Levy Amount, Salary Slip
Sources: Submitted Salary Slips (docstatus=1) for the selected month/year.
"""
import frappe
from frappe.utils import flt

_HRDF_COMPONENTS = {"HRDF", "HRDF Levy", "HRDF - Employer", "HRDF Employer"}

RATE_MAP = {
    "0.5%": 0.005,
    "1.0%": 0.01,
}


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
            "label": "Wages (MYR)",
            "fieldname": "wages",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "HRDF Rate",
            "fieldname": "hrdf_rate",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "HRDF Levy (MYR)",
            "fieldname": "hrdf_levy",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
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
            "reqd": 1,
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


def _get_levy_rate(company):
    """Return the numeric HRDF levy rate for the given company."""
    rate_str = frappe.db.get_value("Company", company, "custom_hrdf_levy_rate")
    return RATE_MAP.get(rate_str, 0)


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

    if not filters.get("company"):
        return []

    rate = _get_levy_rate(filters["company"])
    rate_label = filters.get("_rate_label", "")
    if not rate_label:
        rate_str = frappe.db.get_value(
            "Company", filters["company"], "custom_hrdf_levy_rate"
        )
        rate_label = rate_str or "Not Set"

    where, values = _build_conditions(filters)

    sql = """
        SELECT
            ss.name       AS salary_slip,
            ss.employee   AS employee,
            ss.employee_name AS employee_name,
            ss.gross_pay  AS wages
        FROM `tabSalary Slip` ss
        {where}
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)

    for row in rows:
        row["hrdf_rate"] = rate_label
        row["hrdf_levy"] = flt(row["wages"] * rate, 2)

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
