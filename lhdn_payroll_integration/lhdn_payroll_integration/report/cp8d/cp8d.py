"""CP8D Annual Employee Remuneration Return — Script Report.

CP8D is the annual return of private employees' remuneration submitted
alongside Borang E for LHDN e-Filing. It is a machine-readable employee
income list used for LHDN's employer annual return.

Columns match the LHDN e-Filing CP8D column specification:
  Employee TIN, NRIC/ID, Name, Annual Gross Income, Total PCB, EPF Employee.
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
            "label": "NRIC / ID Number",
            "fieldname": "id_number",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Annual Gross Income (MYR)",
            "fieldname": "annual_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        },
        {
            "label": "Total PCB (MYR)",
            "fieldname": "total_pcb",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "EPF Employee (MYR)",
            "fieldname": "epf_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
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

    # Only submitted slips
    conditions.append("ss.docstatus = 1")

    where = "WHERE " + " AND ".join(conditions)
    return where, values


def _get_deduction_total(employee_slips, component_name):
    """Sum a salary deduction component across submitted slips for an employee."""
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

    # Fetch Employee TIN and ID fields in one query
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
    for row in rows:
        slip_names = row.get("slip_names", "") or ""
        slips = [s for s in slip_names.split(",") if s]

        pcb = _get_deduction_total(slips, "PCB")
        epf = _get_deduction_total(slips, "EPF")

        emp = emp_meta.get(row.employee, frappe._dict())

        result.append(
            frappe._dict(
                {
                    "employee_tin": emp.get("custom_lhdn_tin") or "",
                    "id_number": emp.get("custom_id_value") or "",
                    "employee_name": row.employee_name,
                    "annual_gross": float(row.annual_gross or 0),
                    "total_pcb": pcb,
                    "epf_employee": epf,
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
