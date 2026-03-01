"""CP39 PCB Monthly Remittance Script Report.

Generates the monthly PCB (Potongan Cukai Berjadual) remittance file
compatible with LHDN's e-PCB Plus portal (replaced legacy e-PCB in 2024).

Mandatory column order (e-PCB Plus):
  Employer E-Number, Month/Year, Employee TIN, Employee NRIC, Employee Name,
  PCB Category, Gross Remuneration, EPF Employee, Zakat Amount,
  CP38 Additional, Total PCB.

Currency amounts are numeric (formatted to 2 d.p. in CSV export).
CSV export uses UTF-8 encoding.
"""
import io
import csv

import frappe


def get_columns():
    return [
        {
            "label": "Employer E-Number",
            "fieldname": "employer_e_number",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Month/Year",
            "fieldname": "month_year",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": "Employee TIN",
            "fieldname": "employee_tin",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Employee NRIC",
            "fieldname": "employee_nric",
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
            "width": 100,
        },
        {
            "label": "Gross Remuneration (MYR)",
            "fieldname": "gross_remuneration",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EPF Employee (MYR)",
            "fieldname": "epf_employee",
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
            "label": "CP38 Additional (MYR)",
            "fieldname": "cp38_amount",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "Total PCB (MYR)",
            "fieldname": "total_pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
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


def _get_employer_e_number(company):
    """Safely retrieve custom_employer_e_number from Company."""
    if not company:
        return ""
    try:
        val = frappe.db.get_value("Company", company, "custom_employer_e_number")
        return val or ""
    except Exception:
        return ""


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    # Determine employer E-Number for the filtered company
    company = filters.get("company")
    employer_e_number = _get_employer_e_number(company)

    sql = """
        SELECT
            ss.name                                          AS salary_slip,
            ss.employee                                      AS employee,
            ss.employee_name                                 AS employee_name,
            COALESCE(NULLIF(e.custom_employee_tin, ''), e.custom_lhdn_tin, '') AS employee_tin,
            COALESCE(e.custom_id_value, '')                 AS employee_nric,
            COALESCE(e.custom_pcb_category, '1')            AS pcb_category,
            ss.company                                       AS company,
            COALESCE(NULLIF(ss.custom_gross_myr, 0), ss.gross_pay) AS gross_remuneration,
            DATE_FORMAT(ss.start_date, '%%m/%%Y')           AS month_year,
            SUM(
                CASE WHEN sc.custom_is_pcb_component = 1
                     THEN sd.amount ELSE 0 END
            )                                                AS total_pcb,
            SUM(
                CASE WHEN sd.salary_component = 'EPF'
                     THEN sd.amount ELSE 0 END
            )                                                AS epf_employee,
            COALESCE(e.custom_annual_zakat / 12, 0)         AS zakat_amount,
            COALESCE(
                CASE
                    WHEN e.custom_cp38_expiry IS NOT NULL
                         AND e.custom_cp38_expiry >= CURDATE()
                    THEN e.custom_cp38_amount
                    ELSE 0
                END,
                0
            )                                                AS cp38_amount
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e
            ON e.name = ss.employee
        JOIN `tabSalary Detail` sd
            ON sd.parent = ss.name
            AND sd.parenttype = 'Salary Slip'
            AND sd.parentfield = 'deductions'
        LEFT JOIN `tabSalary Component` sc
            ON sc.name = sd.salary_component
        {where}
        GROUP BY ss.name
        HAVING total_pcb > 0
        ORDER BY ss.employee_name ASC, ss.start_date ASC
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)

    # If no company filter, resolve per-row e-number from the slip's company
    result = []
    for row in rows:
        if company:
            row_e_number = employer_e_number
        else:
            row_e_number = _get_employer_e_number(row.get("company"))
        row["employer_e_number"] = row_e_number
        result.append(row)

    return result


def get_csv_data(filters=None):
    """Return UTF-8 CSV string of CP39 data in e-PCB Plus format.

    Amounts are formatted to 2 decimal places as required by LHDN.
    """
    rows = get_data(filters)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "Employer E-Number",
        "Month/Year",
        "Employee TIN",
        "Employee NRIC",
        "Employee Name",
        "PCB Category",
        "Gross Remuneration",
        "EPF Employee",
        "Zakat Amount",
        "CP38 Additional",
        "Total PCB",
    ])

    for row in rows:
        writer.writerow([
            row.get("employer_e_number", ""),
            row.get("month_year", ""),
            row.get("employee_tin", ""),
            row.get("employee_nric", ""),
            row.get("employee_name", ""),
            row.get("pcb_category", ""),
            "{:.2f}".format(float(row.get("gross_remuneration") or 0)),
            "{:.2f}".format(float(row.get("epf_employee") or 0)),
            "{:.2f}".format(float(row.get("zakat_amount") or 0)),
            "{:.2f}".format(float(row.get("cp38_amount") or 0)),
            "{:.2f}".format(float(row.get("total_pcb") or 0)),
        ])

    return output.getvalue()


def execute(filters=None):
    return get_columns(), get_data(filters)
