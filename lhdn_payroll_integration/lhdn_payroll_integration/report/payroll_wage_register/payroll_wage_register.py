"""Payroll Wage Register Script Report — US-107.

Employment Act 1955 Section 61 and Income Tax Act 1967 Section 82 require employers
to maintain wage records for a minimum of 6 and 7 years respectively.

During LHDN or MOHR (Department of Labour) audits, employers must produce a wage
register covering all employees for the audit period. This report generates:
- Per-employee, per-period salary slip rows
- Gross pay, statutory deductions (EPF, SOCSO, EIS, PCB), net pay
- LHDN submission status for each slip
- Date range filter for any audit window

Export to PDF (print view) and XLSX via Frappe's native export functionality.
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
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 150,
        },
        {
            "label": "Period From",
            "fieldname": "start_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Period To",
            "fieldname": "end_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Posting Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Gross Pay (MYR)",
            "fieldname": "gross_pay",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "EPF Employee (MYR)",
            "fieldname": "epf_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "SOCSO Employee (MYR)",
            "fieldname": "socso_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 170,
        },
        {
            "label": "EIS Employee (MYR)",
            "fieldname": "eis_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "PCB / MTD (MYR)",
            "fieldname": "pcb_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "Total Deductions (MYR)",
            "fieldname": "total_deductions",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 170,
        },
        {
            "label": "Net Pay (MYR)",
            "fieldname": "net_pay",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 150,
        },
        {
            "label": "LHDN Status",
            "fieldname": "lhdn_status",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_filters():
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 1,
        },
        {
            "fieldname": "from_date",
            "label": "From Date",
            "fieldtype": "Date",
            "reqd": 1,
        },
        {
            "fieldname": "to_date",
            "label": "To Date",
            "fieldtype": "Date",
            "reqd": 1,
        },
        {
            "fieldname": "employee",
            "label": "Employee",
            "fieldtype": "Link",
            "options": "Employee",
        },
    ]


def get_data(filters=None):
    """Return wage register rows for the given filters.

    Returns one row per submitted Salary Slip, with statutory deduction
    amounts computed via conditional aggregation in a single SQL query.

    Args:
        filters (dict): keys — company, from_date, to_date, employee (optional)

    Returns:
        list[dict]: one dict per Salary Slip row
    """
    if not filters:
        filters = {}

    company = filters.get("company")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    employee = filters.get("employee")

    if not company or not from_date or not to_date:
        return []

    conditions = "ss.docstatus = 1 AND ss.company = %(company)s"
    params = {
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
    }

    conditions += " AND ss.start_date >= %(from_date)s"
    conditions += " AND ss.end_date <= %(to_date)s"

    if employee:
        conditions += " AND ss.employee = %(employee)s"
        params["employee"] = employee

    rows = frappe.db.sql(
        f"""
        SELECT
            ss.employee                                  AS employee,
            ss.employee_name                             AS employee_name,
            ss.company                                   AS company,
            ss.start_date                                AS start_date,
            ss.end_date                                  AS end_date,
            ss.posting_date                              AS posting_date,
            ss.gross_pay                                 AS gross_pay,
            ss.total_deduction                           AS total_deductions,
            ss.net_pay                                   AS net_pay,
            IFNULL(ss.custom_lhdn_status, '')            AS lhdn_status,
            SUM(CASE WHEN sd.salary_component IN (
                    'EPF Employee', 'EPF - Employee', 'Employees Provident Fund'
                ) THEN IFNULL(sd.amount, 0) ELSE 0 END) AS epf_employee,
            SUM(CASE WHEN sd.salary_component IN (
                    'SOCSO Employee', 'SOCSO - Employee', 'Social Security'
                ) THEN IFNULL(sd.amount, 0) ELSE 0 END) AS socso_employee,
            SUM(CASE WHEN sd.salary_component IN (
                    'EIS Employee', 'EIS - Employee', 'Employment Insurance System'
                ) THEN IFNULL(sd.amount, 0) ELSE 0 END) AS eis_employee,
            SUM(CASE WHEN sd.salary_component IN (
                    'PCB', 'MTD', 'Monthly Tax Deduction', 'Tax Deduction', 'Income Tax'
                ) THEN IFNULL(sd.amount, 0) ELSE 0 END) AS pcb_amount
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parentfield = 'deductions'
        WHERE {conditions}
        GROUP BY
            ss.name,
            ss.employee,
            ss.employee_name,
            ss.company,
            ss.start_date,
            ss.end_date,
            ss.posting_date,
            ss.gross_pay,
            ss.total_deduction,
            ss.net_pay,
            ss.custom_lhdn_status
        ORDER BY ss.employee_name ASC, ss.start_date ASC
        """,
        params,
        as_dict=True,
    )

    result = []
    for row in rows:
        result.append(
            {
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name"),
                "company": row.get("company"),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "posting_date": row.get("posting_date"),
                "gross_pay": flt(row.get("gross_pay") or 0, 2),
                "epf_employee": flt(row.get("epf_employee") or 0, 2),
                "socso_employee": flt(row.get("socso_employee") or 0, 2),
                "eis_employee": flt(row.get("eis_employee") or 0, 2),
                "pcb_amount": flt(row.get("pcb_amount") or 0, 2),
                "total_deductions": flt(row.get("total_deductions") or 0, 2),
                "net_pay": flt(row.get("net_pay") or 0, 2),
                "lhdn_status": row.get("lhdn_status") or "",
            }
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
