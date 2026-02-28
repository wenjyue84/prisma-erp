"""CP8D e-Filing Standalone Report — LHDN e-Filing Column Specification.

Standalone Script Report matching the LHDN e-Filing CP8D 2024 column specification
precisely (separate from the Borang E embedded CP8D). CSV export enabled.

LHDN CP8D e-Filing 2024 columns (in order):
  No., Name, NRIC/Passport, TIN, Gross Income, Gross Bonus/Commission,
  Gross Gratuity, Other Income, EPF, PCB
"""
import frappe


def get_columns():
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
            "label": "NRIC / Passport",
            "fieldname": "id_number",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "TIN",
            "fieldname": "employee_tin",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Gross Income (MYR)",
            "fieldname": "annual_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Gross Bonus / Commission (MYR)",
            "fieldname": "gross_bonus_commission",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 210,
        },
        {
            "label": "Gross Gratuity (MYR)",
            "fieldname": "gross_gratuity",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "Other Income (MYR)",
            "fieldname": "other_income",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EPF (MYR)",
            "fieldname": "epf_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 140,
        },
        {
            "label": "PCB (MYR)",
            "fieldname": "total_pcb",
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
    conditions = []
    values = {}

    year = filters.get("year")
    if year:
        conditions.append("YEAR(ss.start_date) = %(year)s")
        values["year"] = int(year)

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

    conditions.append("ss.docstatus = 1")

    where = "WHERE " + " AND ".join(conditions)
    return where, values


def _get_deduction_total(employee_slips, component_name):
    if not employee_slips:
        return 0.0

    placeholders = ", ".join(["%s"] * len(employee_slips))
    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        WHERE sd.parent IN ({placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sd.salary_component = %s
        """,
        employee_slips + [component_name],
    )
    return float(rows[0][0]) if rows else 0.0


def _get_ea_section_totals(employee_slips):
    """Sum earnings by EA section for income type breakdown (CP8D 2024 spec)."""
    if not employee_slips:
        return {"gross_bonus_commission": 0.0, "gross_gratuity": 0.0, "other_income": 0.0}

    placeholders = ", ".join(["%s"] * len(employee_slips))
    rows = frappe.db.sql(
        f"""
        SELECT sc.custom_ea_section AS ea_section, COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        JOIN `tabSalary Component` sc ON sc.name = sd.salary_component
        WHERE sd.parent IN ({placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'earnings'
          AND sc.custom_ea_section IN (
              'B3 Commission', 'B4 Bonus', 'B5 Gratuity', 'B9 Other Gains'
          )
        GROUP BY sc.custom_ea_section
        """,
        employee_slips,
        as_dict=True,
    )

    totals = {"gross_bonus_commission": 0.0, "gross_gratuity": 0.0, "other_income": 0.0}
    for row in rows:
        ea = row.ea_section or ""
        if ea in ("B3 Commission", "B4 Bonus"):
            totals["gross_bonus_commission"] += float(row.total or 0)
        elif ea == "B5 Gratuity":
            totals["gross_gratuity"] += float(row.total or 0)
        elif ea == "B9 Other Gains":
            totals["other_income"] += float(row.total or 0)
    return totals


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    sql = f"""
        SELECT
            ss.employee                    AS employee,
            ss.employee_name               AS employee_name,
            YEAR(ss.start_date)            AS year,
            SUM(ss.gross_pay)              AS annual_gross,
            GROUP_CONCAT(ss.name)          AS slip_names
        FROM `tabSalary Slip` ss
        {where}
        GROUP BY ss.employee, ss.employee_name, YEAR(ss.start_date)
        ORDER BY ss.employee_name ASC
    """

    rows = frappe.db.sql(sql, values, as_dict=True)

    employee_ids = [row.employee for row in rows]
    emp_meta = {}
    if employee_ids:
        placeholders = ", ".join(["%s"] * len(employee_ids))
        emp_rows = frappe.db.sql(
            f"""
            SELECT name, custom_lhdn_tin, custom_id_type, custom_id_value
            FROM `tabEmployee`
            WHERE name IN ({placeholders})
            """,
            employee_ids,
            as_dict=True,
        )
        for emp in emp_rows:
            emp_meta[emp.name] = emp

    result = []
    for idx, row in enumerate(rows, start=1):
        slip_names = row.get("slip_names", "") or ""
        slips = [s for s in slip_names.split(",") if s]

        pcb = _get_deduction_total(slips, "PCB")
        epf = _get_deduction_total(slips, "EPF")
        breakdown = _get_ea_section_totals(slips)

        emp = emp_meta.get(row.employee, frappe._dict())

        result.append(
            frappe._dict(
                {
                    "no": idx,
                    "employee_name": row.employee_name,
                    "id_number": emp.get("custom_id_value") or "",
                    "employee_tin": emp.get("custom_lhdn_tin") or "",
                    "annual_gross": float(row.annual_gross or 0),
                    "gross_bonus_commission": breakdown["gross_bonus_commission"],
                    "gross_gratuity": breakdown["gross_gratuity"],
                    "other_income": breakdown["other_income"],
                    "epf_employee": epf,
                    "total_pcb": pcb,
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
