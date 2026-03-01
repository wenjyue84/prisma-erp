"""EPF Borang A Monthly Contribution Schedule Script Report.

Generates the monthly EPF (KWSP) contribution schedule (Borang A)
listing each employee's wages, employee contribution, employer contribution
and total EPF for a given month/year.

Also provides generate_iakaun_file() for KWSP i-Akaun electronic upload format.

Columns: Employee Name, NRIC, EPF Member Number, Wages,
         Employee EPF, Employer EPF, Total Contribution, EPF Rate Warning
Sources: Submitted Salary Slips (docstatus=1) with EPF deduction/earning lines.

US-073: Added employer EPF rate validation against statutory rates.
  - 13% for employees earning <= RM5,000/month
  - 12% for employees earning > RM5,000/month

US-067: Added EPF i-Akaun electronic upload file generation.
  - generate_iakaun_file(filters) returns pipe-delimited .txt content
  - Company custom_epf_employer_registration used in file header

US-131: Added citizen type code to i-Akaun detail lines.
  - '1' for Malaysian citizens/PR (custom_is_foreign_worker = 0)
  - '2' for non-Malaysian foreign workers (custom_is_foreign_worker = 1)
  - get_citizen_type_code(is_foreign) helper exported for reuse
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


def get_citizen_type_code(is_foreign):
    """Return KWSP i-Akaun citizen type code.

    Args:
        is_foreign: Truthy value if employee is a non-Malaysian foreign worker.

    Returns:
        '1' for Malaysian citizen/PR, '2' for non-Malaysian (foreign worker).
    """
    return "2" if is_foreign else "1"


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
            "label": "Total Contribution (MYR)",
            "fieldname": "total_contribution",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
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
            COALESCE(e.custom_is_domestic_servant, 0)        AS is_domestic_servant,
            COALESCE(e.custom_is_foreign_worker, 0)          AS is_foreign_worker,
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
        row["total_contribution"] = (row.get("employee_epf") or 0) + (row.get("employer_epf") or 0)
        row["epf_rate_warning"] = get_epf_employer_rate_warning(
            row.get("wages", 0),
            row.get("employer_epf", 0),
        )

    return rows


def generate_iakaun_file(filters=None):
    """Generate KWSP i-Akaun electronic upload file content.

    Returns pipe-delimited text with:
      - Header: H|EPF_EMPLOYER_REG|YEAR_MONTH|TOTAL_EMPLOYEES
      - Detail rows: D|SEQ|NRIC_NO_HYPHENS|EPF_MEMBER_NO|EMPLOYEE_NAME|WAGES|EE_EPF|ER_EPF|CITIZEN_TYPE
      - Trailer: T|TOTAL_ROWS|TOTAL_EE_EPF|TOTAL_ER_EPF

    Citizen type codes (US-131):
      '1' = Malaysian citizen / permanent resident
      '2' = Non-Malaysian foreign worker

    Args:
        filters: frappe._dict with company, month, year keys.

    Returns:
        str: Pipe-delimited file content suitable for .txt upload.
    """
    if filters is None:
        filters = frappe._dict()

    # Get employer EPF registration number from Company
    epf_reg_no = ""
    company = filters.get("company")
    if company:
        epf_reg_no = frappe.db.get_value(
            "Company", company, "custom_epf_employer_registration"
        ) or ""

    # Determine period string YYYYMM
    year = filters.get("year") or frappe.utils.getdate().year
    month = filters.get("month") or str(frappe.utils.getdate().month).zfill(2)
    period = f"{year}{str(month).zfill(2)}"

    # US-130: exclude foreign domestic servants (EPF exempt per KWSP Oct 2025 circular)
    rows = [r for r in get_data(filters) if not r.get("is_domestic_servant")]

    lines = []
    # Header line (domestic servant rows already excluded)
    lines.append(f"H|{epf_reg_no}|{period}|{len(rows)}")

    # Detail lines (1-indexed sequence)
    for seq, row in enumerate(rows, start=1):
        # NRIC: strip hyphens and spaces
        nric = (row.get("nric") or "").replace("-", "").replace(" ", "")
        epf_member = row.get("epf_member_number") or ""
        name = (row.get("employee_name") or "").upper()
        wages = f"{flt(row.get('wages'), 2):.2f}"
        ee_epf = f"{flt(row.get('employee_epf'), 2):.2f}"
        er_epf = f"{flt(row.get('employer_epf'), 2):.2f}"
        # US-131: citizen type code — '1' Malaysian, '2' foreign worker
        citizen_type = get_citizen_type_code(row.get("is_foreign_worker", 0))
        lines.append(f"D|{seq}|{nric}|{epf_member}|{name}|{wages}|{ee_epf}|{er_epf}|{citizen_type}")

    # Trailer line with totals
    total_ee = flt(sum(row.get("employee_epf") or 0 for row in rows), 2)
    total_er = flt(sum(row.get("employer_epf") or 0 for row in rows), 2)
    lines.append(f"T|{len(rows)}|{total_ee:.2f}|{total_er:.2f}")

    return "\n".join(lines)


def validate_account_split(total, accounts, tolerance=0.02):
    """Validate that three-account split amounts sum to the total contribution.

    Used by US-165 to ensure the 75/15/10 EPF account split doesn't drift
    due to rounding on individual contributions.

    Args:
        total (float): Expected total EPF contribution.
        accounts (list[dict]): Each dict must have an ``amount`` key (float).
        tolerance (float): Allowable rounding difference in RM (default 0.02).

    Returns:
        str: Empty string if valid; a warning message string if the split
             sum deviates from *total* by more than *tolerance*.
    """
    if not accounts:
        return ""

    split_sum = sum(a.get("amount", 0.0) for a in accounts)
    diff = abs(split_sum - total)
    if diff > tolerance:
        return (
            f"Account split sum {split_sum:.2f} differs from total {total:.2f} "
            f"by RM {diff:.2f} (tolerance RM {tolerance:.2f})"
        )
    return ""


def execute(filters=None):
    return get_columns(), get_data(filters)
