"""HRDF Monthly Levy Script Report.

Generates the monthly HRDF (Pembangunan Sumber Manusia Berhad) levy
liability schedule listing each employee's wages and calculated HRDF
levy based on the Company's custom_hrdf_levy_rate setting.

Columns: Employee, Employee Name, Wages, HRDF Rate, HRDF Levy Amount, Salary Slip, Warning
Sources: Submitted Salary Slips (docstatus=1) for the selected month/year.

US-072: Updated to reflect HRD Corp regulations (HRD Act 2001 amended 2021).
  - 1.0% mandatory for ALL employers with 10+ Malaysian employees in mandatory sectors.
  - 0.5% voluntary only for companies with 5-9 employees.
"""
import frappe
from frappe.utils import flt

_HRDF_COMPONENTS = {"HRDF", "HRDF Levy", "HRDF - Employer", "HRDF Employer"}

# Rate map handles both legacy option strings ("0.5%", "1.0%") and
# descriptive option strings introduced in US-072.
RATE_MAP = {
    "0.5%": 0.005,
    "1.0%": 0.01,
    "0.5% (Voluntary - 5-9 employees)": 0.005,
    "1.0% (Mandatory - 10+ employees)": 0.01,
}

# Thresholds per HRD Act 2001 (amended 2021)
MANDATORY_HEADCOUNT_THRESHOLD = 10
MANDATORY_RATE = 0.01
VOLUNTARY_RATE = 0.005


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
        {
            "label": "Rate Warning",
            "fieldname": "rate_warning",
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
    rate_str = frappe.db.get_value("Company", company, "custom_hrdf_levy_rate") or ""
    # Support both old and new option string formats via prefix match
    for key, rate in RATE_MAP.items():
        if rate_str == key or rate_str.startswith(key + " "):
            return rate
    return RATE_MAP.get(rate_str, 0)


def get_rate_mismatch_warning(rate_str, is_mandatory_sector, employee_count):
    """Return a warning string if HRDF rate does not match statutory expectation.

    Per HRD Act 2001 (amended 2021):
    - Companies with 10+ employees in mandatory sectors must use 1.0%.
    - Companies with 5-9 employees may use 0.5% (voluntary).
    - Companies below 5 employees are exempt.

    Args:
        rate_str: The current custom_hrdf_levy_rate option string.
        is_mandatory_sector: Boolean, True if company is in a mandatory sector.
        employee_count: Number of Malaysian employees at the company.

    Returns:
        Warning string, or empty string if rate is correct.
    """
    # Resolve numeric rate from option string
    actual_rate = None
    for key, val in RATE_MAP.items():
        if rate_str == key or (rate_str and rate_str.startswith(key + " ")):
            actual_rate = val
            break

    if actual_rate is None:
        return "HRDF levy rate not configured. Set via Company > HRDF Levy Rate."

    # Check if mandatory rate applies
    if is_mandatory_sector and employee_count >= MANDATORY_HEADCOUNT_THRESHOLD:
        if abs(actual_rate - MANDATORY_RATE) > 1e-9:
            return (
                f"Rate mismatch: mandatory sector with {employee_count} employees "
                f"requires 1.0% HRDF levy per HRD Act 2001 (amended 2021). "
                f"Currently set to '{rate_str}' ({actual_rate * 100:.1f}%)."
            )
    elif employee_count < MANDATORY_HEADCOUNT_THRESHOLD and is_mandatory_sector:
        # Below threshold — voluntary 0.5% is acceptable
        if abs(actual_rate - MANDATORY_RATE) < 1e-9:
            return (
                f"Note: company has {employee_count} employees (below mandatory threshold of "
                f"{MANDATORY_HEADCOUNT_THRESHOLD}). 0.5% voluntary rate applies; "
                f"1.0% may be overpaying unless voluntarily registered at mandatory rate."
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

    if not filters.get("company"):
        return []

    rate = _get_levy_rate(filters["company"])
    rate_label = filters.get("_rate_label", "")
    if not rate_label:
        rate_str = frappe.db.get_value(
            "Company", filters["company"], "custom_hrdf_levy_rate"
        )
        rate_label = rate_str or "Not Set"
    else:
        rate_str = rate_label

    # Get mandatory sector flag and employee count for rate warning
    company_doc = frappe.db.get_value(
        "Company",
        filters["company"],
        ["custom_hrdf_mandatory_sector"],
        as_dict=True,
    ) or {}
    is_mandatory_sector = bool(company_doc.get("custom_hrdf_mandatory_sector"))
    employee_count = filters.get("_employee_count", 0)

    warning = get_rate_mismatch_warning(rate_str, is_mandatory_sector, employee_count)

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
        row["rate_warning"] = warning

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
