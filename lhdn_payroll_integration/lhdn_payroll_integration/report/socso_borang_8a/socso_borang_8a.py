"""SOCSO Borang 8A Monthly Contribution Schedule Script Report.

Generates the monthly SOCSO (PERKESO) contribution schedule (Borang 8A)
listing each employee's wages, employee SOCSO, employer SOCSO and total
for a given month/year.

Columns: Employee Name, NRIC, SOCSO Member Number, Wages,
         Employee SOCSO, Employer SOCSO, Total
Sources: Submitted Salary Slips (docstatus=1) with SOCSO deduction lines.
"""
import frappe

_SOCSO_EMPLOYEE_COMPONENTS = {"SOCSO", "SOCSO Employee", "PERKESO", "PERKESO Employee"}
_SOCSO_EMPLOYER_COMPONENTS = {
    "SOCSO - Employer",
    "SOCSO Employer",
    "PERKESO - Employer",
    "PERKESO Employer",
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
            "label": "NRIC",
            "fieldname": "nric",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": "SOCSO Number",
            "fieldname": "socso_member_number",
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
            "label": "Employee SOCSO (MYR)",
            "fieldname": "employee_socso",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "Employer SOCSO (MYR)",
            "fieldname": "employer_socso",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "Total SOCSO (MYR)",
            "fieldname": "total_socso",
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

    emp_names = list(_SOCSO_EMPLOYEE_COMPONENTS)
    emr_names = list(_SOCSO_EMPLOYER_COMPONENTS)

    emp_placeholders = ", ".join([f"%(socso_emp_{i})s" for i in range(len(emp_names))])
    emr_placeholders = ", ".join([f"%(socso_emr_{i})s" for i in range(len(emr_names))])

    for i, n in enumerate(emp_names):
        values[f"socso_emp_{i}"] = n
    for i, n in enumerate(emr_names):
        values[f"socso_emr_{i}"] = n

    sql = """
        SELECT
            ss.name                                           AS salary_slip,
            ss.employee                                       AS employee,
            ss.employee_name                                  AS employee_name,
            COALESCE(e.custom_id_value, '')                  AS nric,
            COALESCE(e.custom_socso_member_number, '')       AS socso_member_number,
            ss.gross_pay                                      AS wages,
            COALESCE(SUM(CASE
                WHEN sd.salary_component IN ({emp_placeholders})
                     AND sd.parentfield = 'deductions'
                THEN sd.amount ELSE 0 END), 0)               AS employee_socso,
            COALESCE(SUM(CASE
                WHEN sd.salary_component IN ({emr_placeholders})
                THEN sd.amount ELSE 0 END), 0)               AS employer_socso
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e
            ON e.name = ss.employee
        LEFT JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parenttype = 'Salary Slip'
        {where}
        GROUP BY ss.name
        HAVING (employee_socso > 0 OR employer_socso > 0)
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(
        emp_placeholders=emp_placeholders,
        emr_placeholders=emr_placeholders,
        where=where,
    )

    rows = frappe.db.sql(sql, values, as_dict=True)

    for row in rows:
        row["total_socso"] = (row.get("employee_socso") or 0) + (row.get("employer_socso") or 0)

    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
