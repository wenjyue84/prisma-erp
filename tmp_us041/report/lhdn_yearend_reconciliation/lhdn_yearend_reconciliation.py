"""LHDN Year-End Reconciliation Script Report.

Compares total PCB withheld per employee against LHDN-accepted submissions
for the full year. Used for Borang E and EA Form verification.

Columns: Employee, Annual Gross Income, Total PCB Withheld, Invoices Submitted,
         Invoices Valid, Discrepancy Flag.

Discrepancy is raised when:
  - submitted_count != valid_count (some invoices not accepted by LHDN), OR
  - pcb_withheld > 0 but valid_count == 0 (PCB deducted but nothing accepted).
"""
import frappe
from frappe.utils import flt


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
            "label": "Annual Gross Income (MYR)",
            "fieldname": "annual_gross_income",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Total PCB Withheld (MYR)",
            "fieldname": "total_pcb_withheld",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Invoices Submitted",
            "fieldname": "invoices_submitted",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": "Invoices Valid",
            "fieldname": "invoices_valid",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Discrepancy",
            "fieldname": "discrepancy_flag",
            "fieldtype": "Data",
            "width": 120,
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


def _get_salary_slip_aggregates(company, year):
    """Return per-employee annual aggregates from submitted Salary Slips."""
    sql = """
        SELECT
            ss.employee                     AS employee,
            ss.employee_name                AS employee_name,
            SUM(ss.gross_pay)               AS annual_gross_income,
            SUM(IFNULL(sd.amount, 0))       AS total_pcb_withheld,
            COUNT(ss.name)                  AS invoices_submitted,
            SUM(
                CASE WHEN IFNULL(ss.custom_lhdn_status, '') = 'Valid' THEN 1 ELSE 0 END
            )                               AS invoices_valid
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parentfield = 'deductions'
            AND sd.salary_component IN ('PCB', 'MTD', 'Tax Deduction', 'Income Tax')
        WHERE
            ss.docstatus = 1
            AND ss.company = %(company)s
            AND YEAR(ss.start_date) = %(year)s
        GROUP BY ss.employee, ss.employee_name
        ORDER BY ss.employee_name ASC
    """
    return frappe.db.sql(
        sql,
        {"company": company, "year": year},
        as_dict=True,
    )


def _has_discrepancy(row):
    """Return True when the row has a PCB vs LHDN mismatch."""
    submitted = int(row.get("invoices_submitted") or 0)
    valid = int(row.get("invoices_valid") or 0)
    pcb = flt(row.get("total_pcb_withheld") or 0)

    if submitted != valid:
        return True
    if pcb > 0 and valid == 0:
        return True
    return False


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    company = filters.get("company")
    year = filters.get("year")

    if not company or not year:
        return []

    try:
        year = int(year)
    except (ValueError, TypeError):
        return []

    rows = _get_salary_slip_aggregates(company, year)

    for row in rows:
        row["annual_gross_income"] = flt(row.get("annual_gross_income") or 0, 2)
        row["total_pcb_withheld"] = flt(row.get("total_pcb_withheld") or 0, 2)
        row["invoices_submitted"] = int(row.get("invoices_submitted") or 0)
        row["invoices_valid"] = int(row.get("invoices_valid") or 0)
        row["discrepancy_flag"] = "YES" if _has_discrepancy(row) else ""

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
