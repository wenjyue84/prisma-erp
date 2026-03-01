"""e-PCB Plus Pre-flight Completeness Check (US-129).

LHDN advisory: e-PCB Plus will reject an entire CP39 batch if any employee
row is missing a valid TIN, IC type, or PCB category code.

This module provides:
  - run_epcb_preflight_check()  — whitelisted API; returns JSON list of non-compliant employees
  - get_employee_data_gaps()    — internal helper; queries Salary Slips for a payroll period

Usage from Dev Tools or any Frappe page:
    frappe.call({
        method: "lhdn_payroll_integration.lhdn_payroll_integration.api.epcb_preflight.run_epcb_preflight_check",
        args: { company: "Acme Sdn Bhd", month: "01", year: 2025 },
        callback: function(r) { ... }
    });
"""

import frappe
from frappe import _
from frappe.utils import now_datetime


def get_employee_data_gaps(company, month, year):
    """Return a list of non-compliant employee records for the given payroll period.

    Queries all submitted Salary Slips in the specified month/year for the
    given company and flags employees who are missing any of:
      - custom_lhdn_tin  (Employee TIN)
      - custom_pcb_category  (PCB category code: 1, 2 or 3)
      - custom_id_type  (IC type: NRIC / Passport / Army)

    Args:
        company (str): Company name (filters Salary Slips by company).
        month (str | int): Two-digit month ("01"–"12") or integer 1–12.
        year (int | str): Calendar year, e.g. 2025.

    Returns:
        list[dict]: Each dict contains:
            {
                "employee": str,
                "employee_name": str,
                "salary_slip": str,
                "missing_tin": bool,
                "missing_pcb_category": bool,
                "missing_id_type": bool,
                "issues": [str, ...]   # human-readable list of gap names
            }
        An empty list means all employees are compliant.
    """
    month_str = str(month).zfill(2)
    year_int = int(year)

    # Fetch all docsubmitted Salary Slips for the period (docstatus=1 means submitted)
    slips = frappe.db.sql(
        """
        SELECT
            ss.name                         AS salary_slip,
            ss.employee                     AS employee,
            ss.employee_name                AS employee_name,
            COALESCE(e.custom_lhdn_tin, '') AS tin,
            COALESCE(e.custom_pcb_category, '') AS pcb_category,
            COALESCE(e.custom_id_type, '')  AS id_type
        FROM
            `tabSalary Slip` ss
            LEFT JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE
            ss.company = %(company)s
            AND ss.docstatus = 1
            AND MONTH(ss.start_date) = %(month)s
            AND YEAR(ss.start_date)  = %(year)s
        ORDER BY ss.employee
        """,
        {"company": company, "month": int(month_str), "year": year_int},
        as_dict=True,
    )

    gaps = []
    for row in slips:
        missing_tin = not row.get("tin", "").strip()
        missing_pcb = not row.get("pcb_category", "").strip()
        missing_id = not row.get("id_type", "").strip()

        if missing_tin or missing_pcb or missing_id:
            issues = []
            if missing_tin:
                issues.append("TIN missing")
            if missing_pcb:
                issues.append("PCB Category missing")
            if missing_id:
                issues.append("IC/Passport type missing")

            gaps.append({
                "employee": row["employee"],
                "employee_name": row["employee_name"],
                "salary_slip": row["salary_slip"],
                "missing_tin": missing_tin,
                "missing_pcb_category": missing_pcb,
                "missing_id_type": missing_id,
                "issues": issues,
            })

    return gaps


@frappe.whitelist()
def run_epcb_preflight_check(company, month, year):
    """Whitelisted API: Run the e-PCB Plus pre-flight data completeness check.

    Only HR Managers or System Managers may invoke this API.

    Args:
        company (str): Company name.
        month (str | int): Month ("01"–"12").
        year (int | str): Year.

    Returns:
        dict: {
            "compliant": bool,
            "gap_count": int,
            "gaps": list[dict],  # see get_employee_data_gaps()
            "checked_at": str,   # ISO datetime
        }
    """
    frappe.only_for(("HR Manager", "System Manager"))

    gaps = get_employee_data_gaps(company, month, year)
    return {
        "compliant": len(gaps) == 0,
        "gap_count": len(gaps),
        "gaps": gaps,
        "checked_at": now_datetime().isoformat(),
    }
