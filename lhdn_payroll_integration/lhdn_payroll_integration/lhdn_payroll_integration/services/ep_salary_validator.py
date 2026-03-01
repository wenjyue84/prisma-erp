"""Employment Pass Minimum Salary Threshold Validator (US-142).

Malaysia's Expatriate Services Division (ESD) revised Employment Pass (EP)
minimum salary thresholds effective 1 June 2026 (Cabinet approval 17 Oct 2025):

  Cat I:   RM20,000/month (was RM10,000)
  Cat II:  RM10,000–RM19,999 (was RM5,000–RM9,999)
  Cat III: RM5,000–RM9,999  (was RM3,000–RM4,999)

EP holders paid below the category minimum risk renewal rejection and
immigration penalties. This service blocks Salary Slip submission when the
employee's gross salary falls below the applicable threshold.

Override: HR may provide a justification on the Salary Slip
(custom_ep_override_justification), which logs to audit trail and allows
submission.

References:
- ESD Announcement 266: EP Salary Policy 2026
- Immigration Act 1959/63 s.9 (employment pass conditions)
"""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today


# Threshold effective date for June 2026 revised EP policy
EP_POLICY_EFFECTIVE_DATE = "2026-06-01"

# EP category option values matching custom_employment_pass_category field
EP_CATEGORIES = {"Cat I", "Cat II", "Cat III"}


def get_ep_threshold(category: str, as_of_date: str | None = None) -> float | None:
    """Return the applicable minimum gross salary (RM) for an EP category.

    Looks up the EP Salary Threshold DocType for the given category. Returns
    the minimum salary for the threshold record with the latest effective_date
    that is <= as_of_date.

    Args:
        category: EP category string ("Cat I", "Cat II", or "Cat III").
        as_of_date: ISO date string (YYYY-MM-DD). Defaults to today.

    Returns:
        float minimum salary if a threshold record exists; None if not configured.
    """
    if not as_of_date:
        as_of_date = today()

    thresholds = frappe.get_all(
        "EP Salary Threshold",
        filters={"category": category, "effective_date": ["<=", as_of_date]},
        fields=["minimum_salary_rm", "effective_date"],
        order_by="effective_date desc",
        limit=1,
    )
    if not thresholds:
        return None
    return float(thresholds[0]["minimum_salary_rm"] or 0)


def get_ep_holder_compliance(as_of_date: str | None = None) -> list[dict]:
    """Return EP compliance data for all active EP holders.

    Used by the Expatriate EP Salary Compliance report and dashboard.

    Returns:
        list of dicts with keys: employee, employee_name, ep_category,
        ep_number, ep_expiry_date, latest_gross, minimum_required,
        compliant, days_to_expiry.
    """
    if not as_of_date:
        as_of_date = today()

    employees = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            e.employee_name,
            e.custom_employment_pass_category AS ep_category,
            e.custom_ep_number AS ep_number,
            e.custom_ep_expiry_date AS ep_expiry_date
        FROM
            `tabEmployee` e
        WHERE
            e.status = 'Active'
            AND e.custom_employment_pass_category IN ('Cat I', 'Cat II', 'Cat III')
        ORDER BY e.employee_name
        """,
        as_dict=True,
    )

    today_date = getdate(as_of_date)
    result = []
    for emp in employees:
        threshold = get_ep_threshold(emp.ep_category, as_of_date)

        # Latest gross pay from most recent submitted Salary Slip
        latest_slip = frappe.db.sql(
            """
            SELECT gross_pay
            FROM `tabSalary Slip`
            WHERE employee = %s AND docstatus = 1
            ORDER BY period_end DESC
            LIMIT 1
            """,
            emp.employee,
            as_dict=True,
        )
        latest_gross = float(latest_slip[0]["gross_pay"]) if latest_slip else None

        compliant = None
        if threshold is not None and latest_gross is not None:
            compliant = latest_gross >= threshold

        days_to_expiry = None
        if emp.ep_expiry_date:
            expiry = getdate(emp.ep_expiry_date)
            days_to_expiry = (expiry - today_date).days

        result.append(
            {
                "employee": emp.employee,
                "employee_name": emp.employee_name,
                "ep_category": emp.ep_category,
                "ep_number": emp.ep_number or "",
                "ep_expiry_date": emp.ep_expiry_date,
                "latest_gross": latest_gross,
                "minimum_required": threshold,
                "compliant": compliant,
                "days_to_expiry": days_to_expiry,
            }
        )

    return result


def validate_ep_salary_before_submit(doc, method=None):
    """Before-submit hook for Salary Slip.

    Blocks submission when the employee is an EP holder and gross_pay is below
    the applicable category minimum, unless a justification is provided.

    Logs an audit comment when an override is used.
    """
    employee_name = doc.employee
    if not employee_name:
        return

    # Fetch EP category
    ep_category = frappe.db.get_value(
        "Employee", employee_name, "custom_employment_pass_category"
    )
    if not ep_category or ep_category not in EP_CATEGORIES:
        return  # Not an EP holder

    # Only check if period ends on or after policy effective date
    period_end = str(doc.get("end_date") or doc.get("period_end") or "")
    if not period_end or period_end < EP_POLICY_EFFECTIVE_DATE:
        return  # Policy not yet in effect for this period

    threshold = get_ep_threshold(ep_category, period_end)
    if threshold is None:
        return  # No threshold configured — skip validation

    gross_pay = float(doc.gross_pay or 0)
    if gross_pay >= threshold:
        return  # Compliant — no action needed

    # Below threshold — check for override justification
    override_justification = (
        doc.get("custom_ep_override_justification") or ""
    ).strip()

    if not override_justification:
        frappe.throw(
            _(
                "Salary Slip cannot be submitted: Employee {0} ({1}) holds an {2} Employment Pass "
                "but gross pay RM {3} is below the ESD minimum of RM {4} "
                "(effective {5}). Provide an override justification in 'EP Salary Override "
                "Justification' to proceed."
            ).format(
                doc.employee_name or employee_name,
                employee_name,
                ep_category,
                f"{gross_pay:,.2f}",
                f"{threshold:,.2f}",
                EP_POLICY_EFFECTIVE_DATE,
            ),
            title=_("EP Salary Below Threshold"),
        )

    # Override accepted — log to audit trail
    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "Salary Slip",
            "reference_name": doc.name,
            "content": _(
                "<b>EP Salary Override:</b> {0} ({1}) gross pay RM {2:,.2f} is below "
                "{3} EP minimum RM {4:,.2f}. Override justification: <i>{5}</i>"
            ).format(
                doc.employee_name or employee_name,
                employee_name,
                gross_pay,
                ep_category,
                threshold,
                override_justification,
            ),
        }
    ).insert(ignore_permissions=True)
