"""Salary Advance Loan Service (US-101).

Employment Act 1955 S.22/24 compliance:
- Automatically adds advance repayment deduction line to Salary Slip.
- Enforces 50% deduction cap across all statutory deductions + advance repayment.
- Updates advance loan outstanding balance after deduction.

Hook: before_submit on Salary Slip.
"""
import frappe
from frappe.utils import formatdate, getdate


# ---------------------------------------------------------------------------
# Salary component name for advance repayment deductions
# ---------------------------------------------------------------------------
ADVANCE_REPAYMENT_COMPONENT = "Salary Advance Repayment"

# Names of statutory deduction components to include in 50% cap calculation
STATUTORY_DEDUCTION_COMPONENTS = {
    "EPF Employee",
    "SOCSO Employee",
    "EIS Employee",
    "Monthly Tax Deduction",
    "PCB",
}


def compute_advance_repayment_for_salary_slip(doc, method=None):
    """Before-submit hook on Salary Slip: apply advance repayment with 50% cap.

    Algorithm:
    1. Find all Active Salary Advance Loans for the employee.
    2. Compute total existing statutory deductions from the slip.
    3. Compute how much headroom remains under the 50% cap.
    4. For each active advance loan (oldest first), deduct as much as allowed.
    5. Inject deduction rows into the slip and mark the advance loan updated.

    Note: The slip's net_pay is NOT adjusted here — Frappe recalculates it
    automatically on submit based on earnings - deductions.
    """
    try:
        employee = doc.employee
        if not employee:
            return

        gross_pay = float(doc.gross_pay or 0)
        if gross_pay <= 0:
            return

        active_loans = _get_active_loans(employee)
        if not active_loans:
            return

        # 50% cap from EA S.24(2)
        max_deductions = gross_pay * 0.50

        # Sum of statutory deductions already on the slip
        existing_statutory = _sum_statutory_deductions(doc)

        # Remove any previously injected advance repayment rows (idempotency)
        _remove_advance_rows(doc)

        headroom = max(0.0, max_deductions - existing_statutory)
        if headroom <= 0:
            frappe.msgprint(
                f"50% deduction cap already reached for {employee}. "
                "No salary advance repayment deducted this period.",
                alert=True,
                indicator="orange",
            )
            return

        # Ensure the repayment salary component exists
        _ensure_advance_component_exists()

        slip_date = getdate(doc.end_date or doc.posting_date)
        period_label = formatdate(slip_date, "MMM YYYY") if slip_date else str(slip_date)

        for loan in active_loans:
            if headroom <= 0:
                break

            scheduled = float(loan.repayment_amount_per_period or 0)
            outstanding = float(loan.outstanding_balance or 0)
            # Deduct the lesser of: scheduled, outstanding, or remaining headroom
            actual_deducted = min(scheduled, outstanding, headroom)
            if actual_deducted <= 0:
                continue

            # Add deduction row to salary slip
            doc.append("deductions", {
                "salary_component": ADVANCE_REPAYMENT_COMPONENT,
                "amount": actual_deducted,
                "do_not_include_in_total": 0,
            })
            headroom -= actual_deducted

            # Record repayment on the loan (post-submit via queue to avoid lock issues)
            frappe.enqueue(
                "lhdn_payroll_integration.lhdn_payroll_integration.services.salary_advance_service._record_loan_repayment",
                loan_name=loan.name,
                actual_deducted=actual_deducted,
                salary_slip_name=doc.name,
                period_label=period_label,
                slip_date=str(slip_date),
                queue="short",
                is_async=True,
            )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Salary Advance Repayment Error")


def _record_loan_repayment(loan_name, actual_deducted, salary_slip_name, period_label, slip_date):
    """Called asynchronously after Salary Slip submit to update loan balance."""
    try:
        loan = frappe.get_doc("Salary Advance Loan", loan_name)
        loan.apply_repayment(
            actual_deducted=actual_deducted,
            salary_slip_name=salary_slip_name,
            period_label=period_label,
            deduction_date=slip_date,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Salary Advance Loan Balance Update Error")


def _get_active_loans(employee):
    """Return list of Active Salary Advance Loan docs for the employee, oldest first."""
    loan_names = frappe.get_all(
        "Salary Advance Loan",
        filters={"employee": employee, "status": "Active", "outstanding_balance": [">", 0]},
        fields=["name"],
        order_by="advance_date asc",
    )
    return [frappe.get_doc("Salary Advance Loan", ln["name"]) for ln in loan_names]


def _sum_statutory_deductions(doc):
    """Sum statutory deduction amounts on the Salary Slip (excluding advance repayments)."""
    total = 0.0
    for row in doc.get("deductions") or []:
        if row.salary_component in STATUTORY_DEDUCTION_COMPONENTS:
            total += float(row.amount or 0)
    return total


def _remove_advance_rows(doc):
    """Remove any existing advance repayment deduction rows (idempotent re-run)."""
    doc.deductions = [
        row for row in (doc.get("deductions") or [])
        if row.salary_component != ADVANCE_REPAYMENT_COMPONENT
    ]


def _ensure_advance_component_exists():
    """Create the 'Salary Advance Repayment' salary component if it does not exist."""
    if not frappe.db.exists("Salary Component", ADVANCE_REPAYMENT_COMPONENT):
        frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": ADVANCE_REPAYMENT_COMPONENT,
            "salary_component_abbr": "SAR",
            "type": "Deduction",
            "description": "Employment Act S.22/24 salary advance repayment deduction.",
        }).insert(ignore_permissions=True)
