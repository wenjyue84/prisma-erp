"""Borang E (Form E) Script Report.

Employer's Annual Return to LHDN (Income Tax Act 1967, Section 83).
Due 31 March each year. Non-compliance: penalty under Section 120.

Company-level summary of all PCB, headcount, and total remuneration,
plus CP8D employee list (per-employee annual income + PCB).
"""
import frappe

from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import (
    get_data as get_ea_data,
)


def get_columns():
    return [
        {
            "label": "Row Type",
            "fieldname": "row_type",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 180,
        },
        {
            "label": "Year",
            "fieldname": "year",
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 140,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Total Employees",
            "fieldname": "total_employees",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Total Gross Remuneration (MYR)",
            "fieldname": "total_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 230,
        },
        {
            "label": "EPF Employer (MYR)",
            "fieldname": "epf_employer",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "SOCSO Employer (MYR)",
            "fieldname": "socso_employer",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Total PCB Withheld (MYR)",
            "fieldname": "total_pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        },
        {
            "label": "Total CP38 Deducted (MYR)",
            "fieldname": "total_cp38",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        },
    ]


def get_filters():
    current_year = frappe.utils.nowdate()[:4]
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
            "default": int(current_year),
            "reqd": 1,
        },
    ]


def _get_employer_component_total(filters, component_name):
    """Sum a salary component (employer-side) across all submitted slips for company/year.

    Searches both 'earnings' and 'deductions' parentfields so it works
    regardless of how the payroll is configured.
    """
    conditions = ["ss.docstatus = 1"]
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    company = filters.get("company")
    if company:
        conditions.append("ss.company = %(company)s")
        values["company"] = company

    where = "WHERE " + " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        INNER JOIN `tabSalary Slip` ss ON sd.parent = ss.name
        {where}
          AND sd.parenttype = 'Salary Slip'
          AND sd.salary_component = %(component)s
        """,
        {**values, "component": component_name},
    )
    return float(rows[0][0]) if rows else 0.0


def _get_total_cp38_deducted(filters):
    """Sum CP38 additional deductions across all submitted slips for company/year.

    CP38 is an additional employer obligation (ITA s.107(1)(b)). The total is
    reported as a separate line in Borang E to distinguish from regular PCB.
    """
    conditions = ["ss.docstatus = 1"]
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    company = filters.get("company")
    if company:
        conditions.append("ss.company = %(company)s")
        values["company"] = company

    where = "WHERE " + " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(
            CASE
                WHEN e.custom_cp38_expiry IS NOT NULL
                     AND e.custom_cp38_expiry >= ss.start_date
                THEN COALESCE(e.custom_cp38_amount, 0)
                ELSE 0
            END
        ), 0) AS total_cp38
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        {where}
        """,
        values,
    )
    return float(rows[0][0]) if rows else 0.0


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    # Re-use EA Form aggregation for per-employee data
    ea_rows = get_ea_data(filters)

    if not ea_rows:
        return []

    company = filters.get("company", "")
    year = filters.get("year", "")

    # Company-level totals
    total_employees = len(ea_rows)
    total_gross = sum(float(r.get("total_gross") or 0) for r in ea_rows)
    total_pcb = sum(float(r.get("pcb_total") or 0) for r in ea_rows)

    # Employer statutory contributions
    epf_employer = _get_employer_component_total(filters, "EPF Employer")
    socso_employer = _get_employer_component_total(filters, "SOCSO Employer")

    # CP38 additional deductions (separate from regular PCB per ITA s.107(1)(b))
    total_cp38 = _get_total_cp38_deducted(filters)

    # Row 0: Borang E company-level summary
    summary_row = frappe._dict(
        {
            "row_type": "Summary",
            "company": company,
            "year": str(year),
            "employee": None,
            "employee_name": None,
            "total_employees": total_employees,
            "total_gross": total_gross,
            "epf_employer": epf_employer,
            "socso_employer": socso_employer,
            "total_pcb": total_pcb,
            "total_cp38": total_cp38,
        }
    )

    # Rows 1+: CP8D per-employee breakdown
    detail_rows = []
    for r in ea_rows:
        detail_rows.append(
            frappe._dict(
                {
                    "row_type": "CP8D",
                    "company": company,
                    "year": str(r.get("year", year)),
                    "employee": r.get("employee"),
                    "employee_name": r.get("employee_name"),
                    "total_employees": None,
                    "total_gross": float(r.get("total_gross") or 0),
                    "epf_employer": None,
                    "socso_employer": None,
                    "total_pcb": float(r.get("pcb_total") or 0),
                    "total_cp38": None,
                }
            )
        )

    return [summary_row] + detail_rows


def execute(filters=None):
    return get_columns(), get_data(filters)
