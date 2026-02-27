"""CP8D Annual Employee Remuneration Return Script Report.

CP8D is the annual return of private employees' remuneration submitted alongside
Borang E for LHDN e-Filing. Provides a machine-readable employee income list.

Columns per LHDN e-Filing CP8D specification:
- Employee TIN, NRIC, Name, Annual Gross Income, Total PCB, EPF Employee
"""
import frappe


def get_columns():
    return [
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
            "label": "Employee TIN",
            "fieldname": "employee_tin",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": "NRIC",
            "fieldname": "nric",
            "fieldtype": "Data",
            "width": 160,
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
            "width": 160,
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


def _get_deduction_total(slip_names, component_names):
    """Sum salary deduction components across slips for an employee."""
    if not slip_names or not component_names:
        return 0.0

    slip_placeholders = ", ".join(["%s"] * len(slip_names))
    comp_placeholders = ", ".join(["%s"] * len(component_names))

    rows = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        WHERE sd.parent IN ({slip_placeholders})
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sd.salary_component IN ({comp_placeholders})
        """,
        slip_names + component_names,
    )
    return float(rows[0][0]) if rows else 0.0


PCB_COMPONENTS = ["PCB", "Monthly Tax Deduction", "Income Tax"]
EPF_COMPONENTS = ["EPF"]


def get_data(filters=None):
    if filters is None:
        filters = frappe._dict()

    where, values = _build_conditions(filters)

    sql = f"""
        SELECT
            ss.employee                    AS employee,
            ss.employee_name               AS employee_name,
            SUM(ss.gross_pay)              AS annual_gross,
            GROUP_CONCAT(ss.name)          AS slip_names,
            emp.custom_lhdn_tin            AS employee_tin,
            emp.custom_id_value            AS nric
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` emp ON emp.name = ss.employee
        {where}
        GROUP BY ss.employee, ss.employee_name, emp.custom_lhdn_tin, emp.custom_id_value
        ORDER BY ss.employee_name ASC
    """

    rows = frappe.db.sql(sql, values, as_dict=True)

    result = []
    for row in rows:
        slip_names_str = row.get("slip_names", "") or ""
        slips = [s for s in slip_names_str.split(",") if s]

        total_pcb = _get_deduction_total(slips, PCB_COMPONENTS)
        epf_employee = _get_deduction_total(slips, EPF_COMPONENTS)

        result.append(
            frappe._dict(
                {
                    "employee": row.employee,
                    "employee_name": row.employee_name,
                    "employee_tin": row.employee_tin or "",
                    "nric": row.nric or "",
                    "annual_gross": float(row.annual_gross or 0),
                    "total_pcb": total_pcb,
                    "epf_employee": epf_employee,
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
