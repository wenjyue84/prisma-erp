"""EA Form (Borang EA) Script Report.

Annual employee tax statement required by LHDN, to be provided to all employees
by 28 February each year.

Aggregates all submitted Salary Slips (docstatus=1) for the year per employee.
Output: Total Gross Remuneration, EPF Employee, SOCSO Employee, EIS Employee,
        PCB Total, Net Pay.
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
            "label": "Year",
            "fieldname": "year",
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "label": "Total Gross Remuneration (MYR)",
            "fieldname": "total_gross",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 200,
        },
        {
            "label": "EPF Employee (MYR)",
            "fieldname": "epf_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "SOCSO Employee (MYR)",
            "fieldname": "socso_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 180,
        },
        {
            "label": "EIS Employee (MYR)",
            "fieldname": "eis_employee",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "PCB Total (MYR)",
            "fieldname": "pcb_total",
            "fieldtype": "Currency",
            "options": "MYR",
            "width": 160,
        },
        {
            "label": "Net Pay (MYR)",
            "fieldname": "net_pay",
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
        {
            "fieldname": "employee",
            "label": "Employee",
            "fieldtype": "Link",
            "options": "Employee",
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

    if filters.get("employee"):
        conditions.append("ss.employee = %(employee)s")
        values["employee"] = filters["employee"]

    # Only submitted slips
    conditions.append("ss.docstatus = 1")

    where = "WHERE " + " AND ".join(conditions)
    return where, values


def _get_deduction_total(employee_slips, component_name):
    """Sum a salary deduction component across slips for an employee.

    employee_slips: list of salary slip names for that employee.
    """
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

    # Aggregate gross_pay and net_pay per employee
    sql = f"""
        SELECT
            ss.employee                    AS employee,
            ss.employee_name               AS employee_name,
            YEAR(ss.start_date)            AS year,
            SUM(ss.gross_pay)              AS total_gross,
            SUM(ss.net_pay)                AS net_pay,
            GROUP_CONCAT(ss.name)          AS slip_names
        FROM `tabSalary Slip` ss
        {where}
        GROUP BY ss.employee, ss.employee_name, YEAR(ss.start_date)
        ORDER BY ss.employee_name ASC
    """

    rows = frappe.db.sql(sql, values, as_dict=True)

    result = []
    for row in rows:
        slip_names = row.get("slip_names", "") or ""
        slips = [s for s in slip_names.split(",") if s]

        epf = _get_deduction_total(slips, "EPF")
        socso = _get_deduction_total(slips, "SOCSO")
        eis = _get_deduction_total(slips, "EIS")
        pcb = _get_deduction_total(slips, "PCB")

        result.append(
            frappe._dict(
                {
                    "employee": row.employee,
                    "employee_name": row.employee_name,
                    "year": row.year,
                    "total_gross": float(row.total_gross or 0),
                    "epf_employee": epf,
                    "socso_employee": socso,
                    "eis_employee": eis,
                    "pcb_total": pcb,
                    "net_pay": float(row.net_pay or 0),
                }
            )
        )

    return result


def execute(filters=None):
    return get_columns(), get_data(filters)
