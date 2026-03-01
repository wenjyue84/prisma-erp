"""EIS Employer-Share Cross-Recovery Prevention Service.

US-247: EIS (Amendment) Bill 2025 — Payroll Validation:
Prohibit Employer EIS Contribution Recovery from Employee Wages.

Only the employee share of EIS (0.2% capped at RM6,000) may appear as
a deduction on payslips. The employer's 0.4% EIS share is a company cost
and must never be charged to employees.

Regulatory basis: EIS (Employment Insurance System) (Amendment) Bill 2025;
EIS Act 2017 s. 18(2).
"""
import frappe

EIS_WAGE_CEILING = 6000.0
EIS_EMPLOYER_RATE = 0.004   # 0.4%
EIS_EMPLOYEE_RATE = 0.002   # 0.2%

EIS_EMPLOYER_RECOVERY_ERROR = (
    "EIS (Amendment) Bill 2025 Violation: Salary component '{component}' is marked as "
    "both an EIS deduction and an employer contribution. Employer EIS (0.4%) is a "
    "company cost and cannot be recovered from employee wages. "
    "Remove the employer EIS component from this payslip before submission."
)


def validate_no_employer_eis_deduction(doc, method=None):
    """Raise ValidationError if any Salary Slip deduction recovers the employer EIS share.

    Checks every deductions row: if a component has custom_is_eis_component=1 AND
    is_employer_contribution=1, it is an illegal cross-recovery under the EIS
    (Amendment) Bill 2025.

    Args:
        doc: Salary Slip document.
        method: Frappe doc event method name (unused).

    Raises:
        frappe.ValidationError: If an employer EIS deduction component is found.
    """
    deductions = doc.get("deductions") or []
    for component in deductions:
        component_name = (
            component.get("salary_component")
            or component.get("abbr")
            or "(unknown)"
        )
        is_eis = int(component.get("custom_is_eis_component") or 0)
        is_employer = int(component.get("is_employer_contribution") or 0)
        if is_eis and is_employer:
            frappe.throw(
                EIS_EMPLOYER_RECOVERY_ERROR.format(component=component_name),
                exc=frappe.ValidationError,
                title="EIS Employer Cross-Recovery Prohibited — EIS Amendment 2025",
            )


def get_eis_compliance_rows(filters=None):
    """Return EIS compliance rows for the LHDN Payroll Compliance Report.

    Each row represents a submitted Salary Slip with employer and employee EIS
    breakdowns and whether each portion is recoverable from employee wages.

    Args:
        filters: frappe._dict with optional keys: company, month, year.

    Returns:
        list of dicts with keys:
            salary_slip, employee, employee_name, period, wages,
            eis_employer_rate, eis_employer_amount,
            eis_employee_rate, eis_employee_amount,
            employer_recoverable, employee_recoverable
    """
    if filters is None:
        filters = frappe._dict()

    conditions = ["ss.docstatus = 1"]
    values = {}

    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("month"):
        try:
            conditions.append("MONTH(ss.start_date) = %(month)s")
            values["month"] = int(filters["month"])
        except (ValueError, TypeError):
            pass

    if filters.get("year"):
        try:
            conditions.append("YEAR(ss.start_date) = %(year)s")
            values["year"] = int(filters["year"])
        except (ValueError, TypeError):
            pass

    where = "WHERE " + " AND ".join(conditions)

    sql = """
        SELECT
            ss.name          AS salary_slip,
            ss.employee      AS employee,
            ss.employee_name AS employee_name,
            CONCAT(ss.start_date, ' to ', ss.end_date) AS period,
            ss.gross_pay     AS wages
        FROM `tabSalary Slip` ss
        {where}
        ORDER BY ss.employee_name ASC
    """.format(where=where)

    rows = frappe.db.sql(sql, values, as_dict=True)

    result = []
    for row in rows:
        wages = float(row.get("wages") or 0)
        capped_wages = min(wages, EIS_WAGE_CEILING)
        eis_employer_amount = round(capped_wages * EIS_EMPLOYER_RATE, 2)
        eis_employee_amount = round(capped_wages * EIS_EMPLOYEE_RATE, 2)
        result.append({
            "salary_slip": row["salary_slip"],
            "employee": row["employee"],
            "employee_name": row["employee_name"],
            "period": row["period"],
            "wages": wages,
            "eis_employer_rate": "0.40%",
            "eis_employer_amount": eis_employer_amount,
            "eis_employee_rate": "0.20%",
            "eis_employee_amount": eis_employee_amount,
            "employer_recoverable": "No",
            "employee_recoverable": "Yes",
        })

    return result


def get_employer_eis_violation_salary_structures():
    """Pre-migration report: list Salary Structures with illegal employer EIS deductions.

    Scans all Salary Structure Detail rows where the linked Salary Component
    has custom_is_eis_component=1 AND is_employer_contribution=1.

    Returns:
        list of dicts: {salary_structure, company, salary_component, abbr}
    """
    sql = """
        SELECT
            ssd.parent            AS salary_structure,
            ss.company            AS company,
            ssd.salary_component  AS salary_component,
            ssd.abbr              AS abbr
        FROM `tabSalary Detail` ssd
        INNER JOIN `tabSalary Structure` ss ON ss.name = ssd.parent
        INNER JOIN `tabSalary Component` sc ON sc.name = ssd.salary_component
        WHERE
            ssd.parenttype = 'Salary Structure'
            AND ssd.parentfield = 'deductions'
            AND sc.custom_is_eis_component = 1
            AND sc.is_employer_contribution = 1
        ORDER BY ssd.parent ASC
    """
    try:
        rows = frappe.db.sql(sql, as_dict=True)
    except Exception:
        rows = []
    return rows
