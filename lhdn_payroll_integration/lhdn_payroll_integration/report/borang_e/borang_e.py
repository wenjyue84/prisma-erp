"""Borang E (Form E) Script Report.

Employer's Annual Return to LHDN (Income Tax Act 1967, Section 83).
Due 31 March each year. Non-compliance: penalty under Section 120.

US-062: Added mandatory header fields (Employer E-Number, Branch Code),
PCB category breakdown (Category 1/2/3 headcount), total Zakat,
and Section B director remuneration segregation.
"""
import frappe

from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import (
    get_data as get_ea_data,
)


def get_columns():
    return [
        {
            "label": "Row Type",
            "fieldname": "row_type",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": "Company",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 180,
        },
        {
            "label": "Year",
            "fieldname": "year",
            "fieldtype": "Data",
            "width": 80,
        },
        # US-062: mandatory header fields
        {
            "label": "Employer E-Number",
            "fieldname": "employer_e_number",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "LHDN Branch Code",
            "fieldname": "lhdn_branch_code",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 140,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Total Employees",
            "fieldname": "total_employees",
            "fieldtype": "Int",
            "width": 130,
        },
        # US-062: category breakdown
        {
            "label": "Cat 1 Employees",
            "fieldname": "cat1_employees",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Cat 2 Employees",
            "fieldname": "cat2_employees",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Cat 3 Employees",
            "fieldname": "cat3_employees",
            "fieldtype": "Int",
            "width": 130,
        },
        {
            "label": "Total Gross Remuneration (MYR)",
            "fieldname": "total_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 230,
        },
        {
            "label": "EPF Employer (MYR)",
            "fieldname": "epf_employer",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "SOCSO Employer (MYR)",
            "fieldname": "socso_employer",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Total PCB Withheld (MYR)",
            "fieldname": "total_pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        },
        {
            "label": "Total CP38 Deducted (MYR)",
            "fieldname": "total_cp38",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        },
        # US-062: Zakat
        {
            "label": "Total Zakat (MYR)",
            "fieldname": "total_zakat",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "PCB Category",
            "fieldname": "pcb_category",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Worker Type",
            "fieldname": "worker_type",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_filters():
    current_year = frappe.utils.nowdate()[:4]
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
            "default": int(current_year),
            "reqd": 1,
        },
    ]


def _get_employer_component_total(filters, component_name):
    """Sum a salary component (employer-side) across all submitted slips for company/year."""
    conditions = ["ss.docstatus = 1"]
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    company = filters.get("company")
    if company:
        conditions.append("ss.company = %(company)s")
        values["company"] = company

    where = "WHERE " + " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        INNER JOIN `tabSalary Slip` ss ON sd.parent = ss.name
        {where}
          AND sd.parenttype = 'Salary Slip'
          AND sd.salary_component = %(component)s
        """,
        {**values, "component": component_name},
    )
    return float(rows[0][0]) if rows else 0.0


def _get_total_cp38_deducted(filters):
    """Sum CP38 additional deductions across all submitted slips for company/year."""
    conditions = ["ss.docstatus = 1"]
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    company = filters.get("company")
    if company:
        conditions.append("ss.company = %(company)s")
        values["company"] = company

    where = "WHERE " + " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(
            CASE
                WHEN e.custom_cp38_expiry IS NOT NULL
                     AND e.custom_cp38_expiry >= ss.start_date
                THEN COALESCE(e.custom_cp38_amount, 0)
                ELSE 0
            END
        ), 0) AS total_cp38
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        {where}
        """,
        values,
    )
    return float(rows[0][0]) if rows else 0.0


def _get_company_header_fields(company):
    """Fetch employer E-Number and LHDN branch code from Company doc (US-062)."""
    if not company:
        return "", ""
    try:
        doc = frappe.get_cached_doc("Company", company)
        e_number = getattr(doc, "custom_employer_e_number", None) or ""
        branch_code = getattr(doc, "custom_lhdn_branch_code", None) or ""
        return e_number, branch_code
    except Exception:
        return "", ""


def _get_category_counts(filters):
    """Return dict of PCB category → headcount for employees with submitted slips.

    US-062: Categories 1/2/3. Employees with no category default to '1'.
    """
    conditions = ["ss.docstatus = 1"]
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    company = filters.get("company")
    if company:
        conditions.append("ss.company = %(company)s")
        values["company"] = company

    where = "WHERE " + " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            COALESCE(e.custom_pcb_category, '1') AS pcb_category,
            COUNT(DISTINCT ss.employee) AS headcount
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        {where}
        GROUP BY COALESCE(e.custom_pcb_category, '1')
        """,
        values,
        as_dict=True,
    )

    counts = {"1": 0, "2": 0, "3": 0}
    for row in rows:
        cat = str(row.get("pcb_category") or "1").strip()
        # Normalise — value may be bare '1' or longer description starting with category digit
        for key in ("1", "2", "3"):
            if cat.startswith(key):
                counts[key] += int(row.get("headcount") or 0)
                break
        else:
            counts["1"] += int(row.get("headcount") or 0)

    return counts


def _get_employee_worker_types(employee_ids):
    """Return dict of {employee_id: custom_worker_type} for the given list.

    US-062 Section B: Director employees (custom_worker_type == 'Director')
    are segregated into 'Director CP8D' rows.
    """
    if not employee_ids:
        return {}

    rows = frappe.db.sql(
        """
        SELECT name, COALESCE(custom_worker_type, '') AS worker_type
        FROM `tabEmployee`
        WHERE name IN %(ids)s
        """,
        {"ids": employee_ids},
        as_dict=True,
    )
    return {r["name"]: r["worker_type"] for r in rows}


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    # Re-use EA Form aggregation for per-employee data
    ea_rows = get_ea_data(filters)

    if not ea_rows:
        return []

    company = filters.get("company", "")
    year = filters.get("year", "")

    # Company-level totals
    total_employees = len(ea_rows)
    total_gross = sum(float(r.get("total_gross") or 0) for r in ea_rows)
    total_pcb = sum(float(r.get("pcb_total") or 0) for r in ea_rows)
    total_zakat = sum(float(r.get("annual_zakat") or 0) for r in ea_rows)

    # Employer statutory contributions
    epf_employer = _get_employer_component_total(filters, "EPF Employer")
    socso_employer = _get_employer_component_total(filters, "SOCSO Employer")

    # CP38 additional deductions
    total_cp38 = _get_total_cp38_deducted(filters)

    # US-062: Company header fields
    employer_e_number, lhdn_branch_code = _get_company_header_fields(company)

    # US-062: PCB category breakdown
    cat_counts = _get_category_counts(filters)

    # US-062 Section B: worker type lookup for director segregation
    employee_ids = tuple(r.get("employee") for r in ea_rows if r.get("employee"))
    worker_type_map = _get_employee_worker_types(employee_ids)

    # Row 0: Borang E company-level summary
    summary_row = frappe._dict(
        {
            "row_type": "Summary",
            "company": company,
            "year": str(year),
            "employer_e_number": employer_e_number,
            "lhdn_branch_code": lhdn_branch_code,
            "employee": None,
            "employee_name": None,
            "total_employees": total_employees,
            "cat1_employees": cat_counts.get("1", 0),
            "cat2_employees": cat_counts.get("2", 0),
            "cat3_employees": cat_counts.get("3", 0),
            "total_gross": total_gross,
            "epf_employer": epf_employer,
            "socso_employer": socso_employer,
            "total_pcb": total_pcb,
            "total_cp38": total_cp38,
            "total_zakat": total_zakat,
            "pcb_category": None,
            "worker_type": None,
        }
    )

    # Rows 1+: CP8D per-employee breakdown
    # US-062 Section B: directors get row_type == 'Director CP8D'
    detail_rows = []
    for r in ea_rows:
        emp_id = r.get("employee")
        worker_type = worker_type_map.get(emp_id, "") if emp_id else ""
        is_director = str(worker_type).strip().lower() == "director"
        row_type = "Director CP8D" if is_director else "CP8D"

        detail_rows.append(
            frappe._dict(
                {
                    "row_type": row_type,
                    "company": company,
                    "year": str(r.get("year", year)),
                    "employer_e_number": None,
                    "lhdn_branch_code": None,
                    "employee": emp_id,
                    "employee_name": r.get("employee_name"),
                    "total_employees": None,
                    "cat1_employees": None,
                    "cat2_employees": None,
                    "cat3_employees": None,
                    "total_gross": float(r.get("total_gross") or 0),
                    "epf_employer": None,
                    "socso_employer": None,
                    "total_pcb": float(r.get("pcb_total") or 0),
                    "total_cp38": None,
                    "total_zakat": float(r.get("annual_zakat") or 0),
                    "pcb_category": r.get("pcb_category"),
                    "worker_type": worker_type,
                }
            )
        )

    return [summary_row] + detail_rows


def execute(filters=None):
    return get_columns(), get_data(filters)
