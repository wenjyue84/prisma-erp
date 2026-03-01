"""OKU Double Deduction Summary Script Report (US-194).

Malaysia Income Tax Act 1967: Section 34(6)(n) — additional employer deduction
on remuneration paid to employees holding a valid Kad OKU (Disability Card).

Budget 2026 extended the double deduction for hiring OKU employees to YA2030.

Generates annual summary of OKU employees with total and eligible remuneration,
and computed double deduction amount for attachment to Form C (corporate income tax).
"""
import frappe
from lhdn_payroll_integration.lhdn_payroll_integration.services.oku_service import (
    get_oku_employees_for_company,
    get_eligible_ya_range,
    ELIGIBLE_YA_START,
    ELIGIBLE_YA_END,
    OKU_ANNUAL_CAP,
    OKU_MONTHLY_CAP,
)


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
            "label": "Department",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 150,
        },
        {
            "label": "Kad OKU Number",
            "fieldname": "kad_oku_number",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": "Kad OKU Expiry",
            "fieldname": "kad_oku_expiry_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Total Annual Remuneration (MYR)",
            "fieldname": "total_annual_remuneration",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 220,
        },
        {
            "label": "Eligible Remuneration (≤RM4,000/mth)",
            "fieldname": "eligible_remuneration",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 240,
        },
        {
            "label": "Additional Deduction (S.34(6)(n)) (MYR)",
            "fieldname": "double_deduction",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 260,
        },
        {
            "label": "Months ≤RM4,000",
            "fieldname": "months_with_eligible_salary",
            "fieldtype": "Int",
            "width": 140,
        },
        {
            "label": "All Months Eligible",
            "fieldname": "all_months_eligible",
            "fieldtype": "Check",
            "width": 140,
        },
    ]


def get_filters():
    ya_options = "\n".join(str(y) for y in range(ELIGIBLE_YA_START, ELIGIBLE_YA_END + 1))
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1,
        },
        {
            "fieldname": "year_of_assessment",
            "label": "Year of Assessment",
            "fieldtype": "Select",
            "options": ya_options,
            "default": str(ELIGIBLE_YA_START),
            "reqd": 1,
        },
        {
            "fieldname": "department",
            "label": "Department",
            "fieldtype": "Link",
            "options": "Department",
        },
    ]


def get_data(filters):
    company = filters.get("company")
    year = int(filters.get("year_of_assessment", ELIGIBLE_YA_START))
    department_filter = filters.get("department")

    rows = get_oku_employees_for_company(company, year)

    if department_filter:
        rows = [r for r in rows if r.get("department") == department_filter]

    return rows


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)

    # Build report message noting Budget 2026 extension
    message = (
        f"<b>Note:</b> Double deduction for OKU employee remuneration under "
        f"ITA 1967 Section 34(6)(n) has been extended to YA{ELIGIBLE_YA_END} "
        f"per Budget 2026. Monthly remuneration cap: RM{OKU_MONTHLY_CAP:,.0f}. "
        f"Annual cap per OKU employee: RM{OKU_ANNUAL_CAP:,.0f}."
    )

    return columns, data, None, None, message
