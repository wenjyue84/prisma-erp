"""CP39 PCB Monthly Remittance Script Report.

Generates the monthly PCB (Potongan Cukai Berjadual) remittance file
compatible with LHDN's e-PCB portal.

Columns: Employee TIN, IC/Passport Number, Employee Name, PCB Category,
         Gross Salary, PCB Amount, Zakat Amount, Period
Sources: Submitted Salary Slips (docstatus=1) with PCB deductions > 0.
"""
import frappe


def get_columns():
    return [
        {
            "label": "Employee TIN",
            "fieldname": "employee_tin",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "IC/Passport Number",
            "fieldname": "id_number",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "PCB Category",
            "fieldname": "pcb_category",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120,
        },
        {
            "label": "Gross Salary (MYR)",
            "fieldname": "gross_salary",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "PCB Amount (MYR)",
            "fieldname": "pcb_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "Zakat Amount (MYR)",
            "fieldname": "zakat_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
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

    sql = """
        SELECT
            ss.name                                          AS salary_slip,
            ss.employee                                      AS employee,
            ss.employee_name                                 AS employee_name,
            COALESCE(e.custom_lhdn_tin, '')                 AS employee_tin,
            COALESCE(e.custom_id_value, '')                 AS id_number,
            COALESCE(e.custom_pcb_category, '1')            AS pcb_category,
            ss.gross_pay                                     AS gross_salary,
            SUM(sd.amount)                                   AS pcb_amount,
            COALESCE(e.custom_annual_zakat / 12, 0)         AS zakat_amount,
            CONCAT(
                DATE_FORMAT(ss.start_date, '%%Y-%%m'),
                ' (', ss.start_date, ' - ', ss.end_date, ')'
            )                                                AS period
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e
            ON e.name = ss.employee
        JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parenttype = 'Salary Slip'
            AND sd.parentfield = 'deductions'
        JOIN `tabSalary Component` sc
            ON sc.name = sd.salary_component
            AND sc.custom_is_pcb_component = 1
        {where}
        GROUP BY ss.name
        HAVING pcb_amount > 0
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)
    return rows


def execute(filters=None):
    return get_columns(), get_data(filters)
