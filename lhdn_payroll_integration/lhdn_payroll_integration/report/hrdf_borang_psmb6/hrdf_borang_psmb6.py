"""HRDF Borang PSMB/6 Annual Return — Script Report.

Borang PSMB/6 is the annual HRDF (Human Resources Development Fund /
Pembangunan Sumber Manusia Berhad) employer return filed each January.
It summarises the total number of employees, total wages paid, and total
HRDF levy remitted for the year.

Columns: Month, Total Employees, Total Wages (MYR), Total Levy Paid (MYR)
Filters: Company (required), Year (required)

The levy total is derived by aggregating HRDF deduction components across
all submitted Salary Slips for the selected company and year.  This must
equal the sum of the monthly HRDF Monthly Levy report for every month in
the same year.
"""
import frappe
from frappe.utils import flt

# Component names that represent the HRDF levy deduction
_HRDF_COMPONENTS = {"HRDF", "HRDF Levy", "HRDF - Employer", "HRDF Employer"}

MONTH_LABELS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def get_columns():
    return [
        {
            "label": "Month",
            "fieldname": "month_label",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": "Total Employees",
            "fieldname": "total_employees",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": "Total Wages (MYR)",
            "fieldname": "total_wages",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Total Levy Paid (MYR)",
            "fieldname": "total_levy",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
    ]


def get_filters():
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
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Int",
            "default": current_year,
            "reqd": 1,
        },
    ]


def _build_conditions(filters):
    conditions = ["ss.docstatus = 1"]
    values = {}

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

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


def _get_levy_for_slips(slip_names):
    """Sum HRDF levy deduction components across a list of salary slip names."""
    if not slip_names:
        return 0.0

    placeholders = ", ".join(["%s"] * len(slip_names))
    component_placeholders = ", ".join(["%s"] * len(_HRDF_COMPONENTS))

    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        WHERE sd.parent IN ({placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sd.salary_component IN ({component_placeholders})
        """,
        list(slip_names) + list(_HRDF_COMPONENTS),
    )
    return float(rows[0][0]) if rows else 0.0


def get_data(filters=None):
    """Return one row per month showing employee count, total wages, total levy."""
    if filters is None:
        filters = frappe._dict()

    if not filters.get("company") or not filters.get("year"):
        return []

    where, values = _build_conditions(filters)

    sql = """
        SELECT
            MONTH(ss.start_date)    AS month_num,
            COUNT(DISTINCT ss.employee) AS total_employees,
            SUM(ss.gross_pay)       AS total_wages,
            GROUP_CONCAT(ss.name)   AS slip_names
        FROM `tabSalary Slip` ss
        {where}
        GROUP BY MONTH(ss.start_date)
        ORDER BY MONTH(ss.start_date)
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)

    result = []
    for row in rows:
        slip_names = [s for s in (row.get("slip_names") or "").split(",") if s]
        total_levy = _get_levy_for_slips(slip_names)

        result.append(
            frappe._dict(
                {
                    "month_label": MONTH_LABELS.get(int(row.month_num), str(row.month_num)),
                    "total_employees": int(row.total_employees or 0),
                    "total_wages": flt(row.total_wages, 2),
                    "total_levy": flt(total_levy, 2),
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
