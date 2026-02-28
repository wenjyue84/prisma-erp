"""SOCSO and EIS e-Caruman Upload File Generator.

US-068: Generate PERKESO ASSIST Portal combined SOCSO+EIS e-Caruman upload file.

Regulatory basis: SOCSO Act 1969; EIS Act 2017.

The combined file includes:
  - Employer SOCSO Number (custom_socso_employer_number on Company)
  - Employee NRIC
  - SOCSO Member Number (custom_socso_member_number on Employee)
  - Monthly Wages
  - Employee SOCSO (bracketed table lookup — US-074)
  - Employer SOCSO (bracketed table lookup — US-074)
  - Employee EIS (0.2% capped at RM6,000 ceiling — US-075)
  - Employer EIS (0.2% capped at RM6,000 ceiling — US-075)

The file is a pipe-delimited (|) text file as accepted by PERKESO ASSIST
e-Caruman portal for bulk employer monthly uploads.
"""
import io

import frappe
from frappe.utils import flt

from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
    SOCSO_WAGE_CEILING,
    EIS_WAGE_CEILING,
    calculate_socso_contribution,
    calculate_eis_contribution,
)

# Column delimiter used by PERKESO ASSIST e-Caruman upload
ECARUMAN_DELIMITER = "|"

# Header columns (PERKESO ASSIST portal specification)
ECARUMAN_HEADERS = [
    "Employer SOCSO No",
    "Employee NRIC",
    "SOCSO No",
    "Monthly Wages",
    "Employee SOCSO",
    "Employer SOCSO",
    "Employee EIS",
    "Employer EIS",
]

_SOCSO_EMPLOYEE_COMPONENTS = {"SOCSO", "SOCSO Employee", "PERKESO", "PERKESO Employee"}
_SOCSO_EMPLOYER_COMPONENTS = {
    "SOCSO - Employer",
    "SOCSO Employer",
    "PERKESO - Employer",
    "PERKESO Employer",
}
_EIS_EMPLOYEE_COMPONENTS = {"EIS", "EIS Employee", "EIS - Employee"}
_EIS_EMPLOYER_COMPONENTS = {"EIS - Employer", "EIS Employer"}


def _get_employer_socso_number(company):
    """Return the SOCSO employer registration number for the company."""
    if not company:
        return ""
    return frappe.db.get_value("Company", company, "custom_socso_employer_number") or ""


def get_ecaruman_data(filters=None):
    """Return list of dicts with combined SOCSO+EIS data for upload.

    Each row has the SOCSO and EIS amounts recalculated from the statutory
    rates tables (not taken from salary slip components) to ensure the
    upload file reflects the correct scheduled amounts.

    Args:
        filters: frappe._dict with keys: company, month, year.

    Returns:
        list of dicts, each with keys matching ECARUMAN_HEADERS.
    """
    if filters is None:
        filters = frappe._dict()

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

    sql = """
        SELECT
            ss.name                                           AS salary_slip,
            ss.company                                        AS company,
            ss.employee                                       AS employee,
            ss.employee_name                                  AS employee_name,
            COALESCE(e.custom_id_value, '')                  AS nric,
            COALESCE(e.custom_socso_member_number, '')       AS socso_member_number,
            ss.gross_pay                                      AS wages,
            COALESCE(e.date_of_birth, NULL)                  AS date_of_birth,
            COALESCE(e.custom_is_foreign_worker, 0)          AS is_foreign,
            ss.start_date                                     AS payroll_date
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        {where}
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)

    from datetime import date as _date
    from frappe.utils import getdate

    result = []
    for row in rows:
        wages = flt(row.get("wages") or 0)

        # SOCSO: bracketed table lookup (US-074), ceiling RM6,000
        socso = calculate_socso_contribution(wages)
        socso_employee = socso["employee"]
        socso_employer = socso["employer"]

        # EIS: 0.2% each, ceiling RM6,000 (US-075), with exemptions
        dob = row.get("date_of_birth")
        is_foreign = bool(row.get("is_foreign"))
        payroll_date_raw = row.get("payroll_date")

        if dob is not None and not isinstance(dob, _date):
            try:
                dob = getdate(dob)
            except Exception:
                dob = None

        if payroll_date_raw is not None and not isinstance(payroll_date_raw, _date):
            try:
                payroll_date_raw = getdate(payroll_date_raw)
            except Exception:
                payroll_date_raw = None

        if dob is not None:
            eis = calculate_eis_contribution(
                wages, dob, is_foreign, payroll_date=payroll_date_raw
            )
        else:
            eis = {"employee": 0.0, "employer": 0.0}

        employer_socso_no = _get_employer_socso_number(row.get("company"))

        result.append({
            "employer_socso_no": employer_socso_no,
            "nric": row.get("nric") or "",
            "socso_member_number": row.get("socso_member_number") or "",
            "wages": wages,
            "socso_employee": socso_employee,
            "socso_employer": socso_employer,
            "eis_employee": eis["employee"],
            "eis_employer": eis["employer"],
            # Extra context fields (not written to upload file)
            "employee": row.get("employee") or "",
            "employee_name": row.get("employee_name") or "",
            "salary_slip": row.get("salary_slip") or "",
        })

    return result


def generate_ecaruman_file(filters=None):
    """Generate the PERKESO ASSIST e-Caruman pipe-delimited upload file.

    Returns:
        str: Pipe-delimited text content ready for upload to PERKESO ASSIST.

    The file format follows PERKESO ASSIST portal specification:
    - Line 1: header row (pipe-delimited)
    - Subsequent lines: one employee contribution per line
    - Amounts formatted to 2 decimal places
    - No trailing pipe on each line
    """
    rows = get_ecaruman_data(filters)

    output = io.StringIO()

    # Header
    output.write(ECARUMAN_DELIMITER.join(ECARUMAN_HEADERS) + "\n")

    for row in rows:
        line_fields = [
            row.get("employer_socso_no") or "",
            row.get("nric") or "",
            row.get("socso_member_number") or "",
            "{:.2f}".format(float(row.get("wages") or 0)),
            "{:.2f}".format(float(row.get("socso_employee") or 0)),
            "{:.2f}".format(float(row.get("socso_employer") or 0)),
            "{:.2f}".format(float(row.get("eis_employee") or 0)),
            "{:.2f}".format(float(row.get("eis_employer") or 0)),
        ]
        output.write(ECARUMAN_DELIMITER.join(line_fields) + "\n")

    return output.getvalue()
