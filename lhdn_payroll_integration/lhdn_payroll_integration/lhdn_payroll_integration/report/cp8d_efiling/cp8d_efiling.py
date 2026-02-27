"""CP8D e-Filing — Standalone Script Report.

Generates the LHDN CP8D annual employee remuneration list in the exact
column specification required for LHDN e-Filing CSV submission.

Published LHDN CP8D e-Filing column specification:
  No. | Name | NRIC/Passport | TIN | Gross Income | EPF | PCB

CSV download is enabled via add_to_report_cache_for_download in the JSON.
"""
import frappe


def get_columns():
    """Return columns matching the LHDN CP8D e-Filing specification exactly."""
    return [
        {
            "label": "No.",
            "fieldname": "no",
            "fieldtype": "Int",
            "width": 60,
        },
        {
            "label": "Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "NRIC/Passport",
            "fieldname": "nric_passport",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "TIN",
            "fieldname": "tin",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Gross Income",
            "fieldname": "gross_income",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "EPF",
            "fieldname": "epf",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "PCB",
            "fieldname": "pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
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


def _build_conditions(filters):
    conditions = ["ss.docstatus = 1"]
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

    return "WHERE " + " AND ".join(conditions), values


def _get_deduction_total(slip_names, component_name):
    if not slip_names:
        return 0.0
    placeholders = ", ".join(["%s"] * len(slip_names))
    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0)
        FROM `tabSalary Detail` sd
        WHERE sd.parent IN ({placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sd.salary_component = %s
        """,
        slip_names + [component_name],
    )
    return float(rows[0][0]) if rows else 0.0


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    rows = frappe.db.sql(
        f"""
        SELECT
            ss.employee          AS employee,
            ss.employee_name     AS employee_name,
            SUM(ss.gross_pay)    AS annual_gross,
            GROUP_CONCAT(ss.name) AS slip_names
        FROM `tabSalary Slip` ss
        {where}
        GROUP BY ss.employee, ss.employee_name
        ORDER BY ss.employee_name ASC
        """,
        values,
        as_dict=True,
    )

    employee_ids = [r.employee for r in rows]
    emp_meta = {}
    if employee_ids:
        placeholders = ", ".join(["%s"] * len(employee_ids))
        for emp in frappe.db.sql(
            f"""
            SELECT name, custom_lhdn_tin, custom_id_value
            FROM `tabEmployee`
            WHERE name IN ({placeholders})
            """,
            employee_ids,
            as_dict=True,
        ):
            emp_meta[emp.name] = emp

    result = []
    for idx, row in enumerate(rows, start=1):
        slips = [s for s in (row.slip_names or "").split(",") if s]
        emp = emp_meta.get(row.employee, frappe._dict())
        result.append(
            frappe._dict(
                {
                    "no": idx,
                    "employee_name": row.employee_name,
                    "nric_passport": emp.get("custom_id_value") or "",
                    "tin": emp.get("custom_lhdn_tin") or "",
                    "gross_income": float(row.annual_gross or 0),
                    "epf": _get_deduction_total(slips, "EPF"),
                    "pcb": _get_deduction_total(slips, "PCB"),
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
