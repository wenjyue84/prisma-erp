"""Senior Citizen Deduction Script Report (US-187).

Malaysia Budget 2026: Additional employer income tax deduction for hiring
senior citizens (aged 60+) extended to YA2030.

Generates annual summary of senior citizen employees with total wages paid
per year of assessment for attachment to Form C/CE (corporate income tax).

Breakdown by department and entity.
"""
import frappe
from lhdn_payroll_integration.lhdn_payroll_integration.services.senior_citizen_service import (
    get_senior_citizens_for_company,
    get_eligible_ya_range,
    ELIGIBLE_YA_START,
    ELIGIBLE_YA_END,
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
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 150,
        },
        {
            "label": "Date of Birth",
            "fieldname": "date_of_birth",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": "Age (at 1 Jan YA)",
            "fieldname": "age_at_ya_start",
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "label": "Turns 60 Date",
            "fieldname": "turns_60_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Date of Joining",
            "fieldname": "date_of_joining",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": "Contract End Date",
            "fieldname": "contract_end_date",
            "fieldtype": "Date",
            "width": 130,
        },
        {
            "label": "Months Employed as SC",
            "fieldname": "months_employed_as_sc",
            "fieldtype": "Int",
            "width": 160,
        },
        {
            "label": "Total Wages (MYR)",
            "fieldname": "total_wages",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
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

    rows = get_senior_citizens_for_company(company, year)

    if department_filter:
        rows = [r for r in rows if r.get("department") == department_filter]

    # Sort by department, then employee name
    rows.sort(key=lambda r: (r.get("department") or "", r.get("employee_name") or ""))

    return rows


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data
