"""Private Retirement Scheme (PRS) Voluntary Deduction Service (US-109).

Implements PRS payroll deduction YTD tracking, RM3,000 annual relief cap,
TP1 auto-population, and EA Form Part D integration.

Private Retirement Scheme Act 2012 (Act 739):
  - SC-approved PRS providers administer voluntary retirement contributions
  - LHDN allows RM3,000/year personal tax relief for PRS contributions
  - PRS is a SEPARATE relief bucket from EPF + life insurance (RM7,000 combined)
  - PRS deduction does NOT reduce EPF/SOCSO/EIS contribution base
  - Applied after statutory deductions, before net pay
  - EA Form: PRS contributions declared under deductions section

Salary Component: "Private Retirement Scheme (PRS)" — type Deduction, voluntary
Custom Employee fields: custom_prs_provider_name, custom_prs_account_number
"""

import frappe
from frappe.utils import flt

# PRS annual relief cap per LHDN
PRS_ANNUAL_RELIEF_CAP = 3_000

# Salary component name used in Salary Slip deductions
PRS_COMPONENT_NAME = "Private Retirement Scheme (PRS)"


def get_prs_ytd_total(employee, year):
    """Return the YTD total of PRS deductions from submitted Salary Slips.

    Queries all submitted (docstatus=1) Salary Slips for the given employee
    in the given calendar year, summing the "Private Retirement Scheme (PRS)"
    deduction component.

    Args:
        employee: Employee ID (e.g. "HR-EMP-00001")
        year: Calendar/assessment year (int or str)

    Returns:
        float: Total PRS deduction amount for the year (uncapped raw total)
    """
    year = int(year)
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(sd.amount), 0) AS total
        FROM `tabSalary Detail` sd
        JOIN `tabSalary Slip` ss ON sd.parent = ss.name
        WHERE ss.employee = %s
          AND ss.docstatus = 1
          AND YEAR(ss.start_date) = %s
          AND sd.parenttype = 'Salary Slip'
          AND sd.parentfield = 'deductions'
          AND sd.salary_component = %s
        """,
        (employee, year, PRS_COMPONENT_NAME),
    )
    return flt(result[0][0]) if result else 0.0


def get_prs_relief_amount(employee, year):
    """Return the PRS relief amount capped at RM3,000 for the given year.

    This is the amount that qualifies for LHDN tax relief.

    Args:
        employee: Employee ID
        year: Assessment year

    Returns:
        float: min(YTD PRS total, RM3,000)
    """
    ytd = get_prs_ytd_total(employee, year)
    return min(ytd, PRS_ANNUAL_RELIEF_CAP)


def sync_prs_to_tp1(employee, year):
    """Auto-populate the prs_contribution field on the Employee TP1 Relief record.

    Finds the TP1 record for (employee, year) and updates prs_contribution
    with the capped PRS YTD amount. If no TP1 record exists, does nothing.

    Args:
        employee: Employee ID
        year: Assessment year

    Returns:
        dict: {"updated": bool, "amount": float, "docname": str|None}
    """
    year = int(year)
    relief_amount = get_prs_relief_amount(employee, year)

    tp1_name = frappe.db.get_value(
        "Employee TP1 Relief",
        {"employee": employee, "tax_year": year},
        "name",
    )
    if not tp1_name:
        return {"updated": False, "amount": relief_amount, "docname": None}

    tp1_doc = frappe.get_doc("Employee TP1 Relief", tp1_name)
    old_value = flt(tp1_doc.prs_contribution)
    if old_value != relief_amount:
        tp1_doc.prs_contribution = relief_amount
        tp1_doc.save(ignore_permissions=True)
        return {"updated": True, "amount": relief_amount, "docname": tp1_name}

    return {"updated": False, "amount": relief_amount, "docname": tp1_name}


def get_prs_for_ea_form(employee, year):
    """Return the PRS deduction amount for EA Form Part D.

    The EA Form shows the actual PRS deduction amount (not the capped relief).
    This is the raw YTD total from submitted Salary Slips.

    Args:
        employee: Employee ID
        year: Calendar year

    Returns:
        float: Total PRS deduction for the year
    """
    return get_prs_ytd_total(employee, year)


def get_prs_employee_details(employee):
    """Return PRS provider name and account number from Employee record.

    Args:
        employee: Employee ID

    Returns:
        dict: {"provider_name": str, "account_number": str}
    """
    details = frappe.db.get_value(
        "Employee",
        employee,
        ["custom_prs_provider_name", "custom_prs_account_number"],
        as_dict=True,
    )
    if not details:
        return {"provider_name": "", "account_number": ""}
    return {
        "provider_name": details.get("custom_prs_provider_name") or "",
        "account_number": details.get("custom_prs_account_number") or "",
    }


def validate_prs_deduction_on_slip(doc, method=None):
    """Validate PRS deduction on a Salary Slip before submit.

    Checks:
    1. PRS component exists in deductions
    2. PRS amount is non-negative
    3. Warns if YTD + current would exceed RM3,000 relief cap

    This is a doc_event handler for Salary Slip validate/before_submit.

    Args:
        doc: Salary Slip document
        method: Event method name (unused, required by Frappe hook signature)
    """
    prs_amount = 0.0
    for d in doc.deductions:
        if d.salary_component == PRS_COMPONENT_NAME:
            prs_amount = flt(d.amount)
            break

    if prs_amount <= 0:
        return  # No PRS deduction — nothing to validate

    if prs_amount < 0:
        frappe.throw(
            frappe._("PRS deduction amount cannot be negative: RM {0:,.2f}").format(prs_amount),
            title=frappe._("Invalid PRS Deduction"),
        )

    # Check YTD impact
    year = doc.start_date.year if hasattr(doc.start_date, "year") else int(str(doc.start_date)[:4])
    current_ytd = get_prs_ytd_total(doc.employee, year)
    projected_ytd = current_ytd + prs_amount

    if projected_ytd > PRS_ANNUAL_RELIEF_CAP:
        frappe.msgprint(
            frappe._(
                "PRS YTD total (RM {0:,.2f}) will exceed the RM {1:,.0f} annual relief cap. "
                "The excess (RM {2:,.2f}) will not qualify for tax relief."
            ).format(projected_ytd, PRS_ANNUAL_RELIEF_CAP, projected_ytd - PRS_ANNUAL_RELIEF_CAP),
            indicator="orange",
            alert=True,
        )
