"""PCB Under-Deduction Employer Liability Alert (Section 107A ITA 1967 — US-215).

Under Section 107A ITA 1967, employers are personally liable for any shortfall
in monthly PCB deductions — if an employee's PCB is under-deducted, LHDN can
assess the employer for the full uncollected tax plus penalties.

Detection rules:
1. PCB drops >50% vs prior month without a matching income/relief change event.
2. PCB is zero but estimated chargeable income exceeds the zero-tax threshold
   (RM 2,851/month after EPF and standard RM 9,000 individual relief).

Acknowledgement flow:
- ``before_submit`` hook calls ``check_under_deduction_before_submit(doc, method)``.
- If flagged and no acknowledgement exists -> ``frappe.throw()`` with instructions.
- Frontend calls whitelisted ``acknowledge_pcb_under_deduction(salary_slip, reason)``
  which creates a PCB Change Log entry with change_type='Under-Deduction Acknowledged'.
- Payroll admin can then re-submit the Salary Slip.
"""
import frappe
from frappe import _

# Zero-tax monthly chargeable income threshold (LHDN PCB tables).
# LHDN technical note specifies RM 2,851/month as the practical zero-tax boundary
# after standard RM 9,000 individual relief is applied annualised.
ZERO_TAX_MONTHLY_THRESHOLD = 2851.0  # RM/month

# Standard individual self-relief monthly equivalent (RM 9,000 annual / 12)
STANDARD_MONTHLY_RELIEF = 750.0  # RM

# EPF employee rate used when no EPF component is found in the slip
EPF_EMPLOYEE_RATE = 0.09

# PCB salary component names (mirrors pcb_change_log.py)
_PCB_COMPONENTS = frozenset({
    "Monthly Tax Deduction", "PCB", "Income Tax", "Tax Deduction",
    "MTD", "Potongan Cukai Berjadual",
})

# EPF employee contribution component names
_EPF_COMPONENTS = frozenset({
    "EPF", "Employee Provident Fund", "Kumpulan Wang Simpanan Pekerja",
    "EPF Employee", "Employee's EPF", "EPF Employee Contribution",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_pcb_amount(salary_slip_doc) -> float:
    """Return total PCB deduction from a Salary Slip document."""
    total = 0.0
    for d in getattr(salary_slip_doc, "deductions", []):
        if getattr(d, "salary_component", "") in _PCB_COMPONENTS:
            total += float(getattr(d, "amount", 0) or 0)
    return total


def _get_epf_amount(salary_slip_doc) -> float:
    """Return total EPF employee deduction from a Salary Slip document."""
    total = 0.0
    for d in getattr(salary_slip_doc, "deductions", []):
        if getattr(d, "salary_component", "") in _EPF_COMPONENTS:
            total += float(getattr(d, "amount", 0) or 0)
    return total


def _get_gross_pay(salary_slip_doc) -> float:
    """Return gross pay from the Salary Slip."""
    return float(getattr(salary_slip_doc, "gross_pay", 0) or 0)


def _get_payroll_period(salary_slip_doc) -> str:
    """Return 'YYYY-MM' period string from Salary Slip end_date or posting_date."""
    end_date = (
        getattr(salary_slip_doc, "end_date", None)
        or getattr(salary_slip_doc, "posting_date", None)
    )
    return str(end_date)[:7] if end_date else ""


def _get_prior_month_pcb(employee: str, current_period: str):
    """Look up the prior month's submitted Salary Slip PCB for this employee.

    Returns None if no prior submitted slip is found.
    """
    try:
        year, month = current_period.split("-")[:2]
        year, month = int(year), int(month)
    except Exception:
        return None

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    prev_period = f"{prev_year:04d}-{prev_month:02d}"

    rows = frappe.get_all(
        "Salary Slip",
        filters={"employee": employee, "docstatus": 1},
        fields=["name", "end_date"],
        order_by="end_date desc",
        limit=10,
    )

    for row in rows:
        slip_period = str(row.end_date)[:7] if row.end_date else ""
        if slip_period == prev_period:
            slip_doc = frappe.get_doc("Salary Slip", row.name)
            return _get_pcb_amount(slip_doc)

    return None


def _has_income_change_event(employee: str, payroll_period: str) -> bool:
    """Return True if a documented income/relief change exists for this period.

    Checks PCB Change Log for entries with change_type in the recognised
    income/relief change set.
    """
    rows = frappe.get_all(
        "PCB Change Log",
        filters={
            "employee": employee,
            "payroll_period": payroll_period,
            "change_type": ["in", [
                "TP1 Update", "CP38 Applied", "Category Change", "Manual Override",
            ]],
        },
        limit=1,
    )
    return bool(rows)


def _has_acknowledgement(salary_slip_name: str) -> bool:
    """Return True if an under-deduction acknowledgement exists for this slip."""
    rows = frappe.get_all(
        "PCB Change Log",
        filters={
            "salary_slip": salary_slip_name,
            "change_type": "Under-Deduction Acknowledged",
        },
        limit=1,
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_under_deduction(salary_slip_doc) -> list:
    """Detect PCB under-deduction issues on the given Salary Slip.

    Returns a list of issue dicts (empty = no issues).
    Each dict: ``{"rule": str, "message": str}``

    Rules applied:
    - ``PCB_DROP_50_PCT``: PCB fell >50% vs prior month with no change event.
    - ``ZERO_PCB_ABOVE_THRESHOLD``: PCB is zero but chargeable income > threshold.
    """
    issues = []
    current_pcb = _get_pcb_amount(salary_slip_doc)
    employee = getattr(salary_slip_doc, "employee", "")
    payroll_period = _get_payroll_period(salary_slip_doc)

    # Rule 1: >50% drop vs prior month
    prior_pcb = _get_prior_month_pcb(employee, payroll_period)
    if prior_pcb is not None and prior_pcb > 0:
        drop_pct = (prior_pcb - current_pcb) / prior_pcb
        if drop_pct > 0.50:
            if not _has_income_change_event(employee, payroll_period):
                issues.append({
                    "rule": "PCB_DROP_50_PCT",
                    "message": (
                        f"PCB dropped {drop_pct:.0%} (RM {prior_pcb:.2f} -> RM {current_pcb:.2f}) "
                        f"vs prior month without a documented income or relief change event. "
                        f"Employer liable under S.107A ITA 1967."
                    ),
                })

    # Rule 2: Zero PCB with chargeable income above threshold
    if current_pcb == 0:
        gross = _get_gross_pay(salary_slip_doc)
        epf = _get_epf_amount(salary_slip_doc)
        if epf == 0:
            epf = gross * EPF_EMPLOYEE_RATE  # estimate when not found
        chargeable = gross - epf - STANDARD_MONTHLY_RELIEF
        if chargeable > ZERO_TAX_MONTHLY_THRESHOLD:
            issues.append({
                "rule": "ZERO_PCB_ABOVE_THRESHOLD",
                "message": (
                    f"PCB is RM 0 but estimated chargeable income is "
                    f"RM {chargeable:.2f}/month (exceeds zero-tax threshold "
                    f"RM {ZERO_TAX_MONTHLY_THRESHOLD:.2f}). "
                    f"Employer liable under S.107A ITA 1967."
                ),
            })

    return issues


def check_under_deduction_before_submit(doc, method=None) -> None:
    """Salary Slip before_submit hook: block if under-deduction detected without ack.

    If under-deduction issues are detected and no acknowledgement exists in the
    PCB Change Log, raises ``frappe.ValidationError`` with instructions for the
    payroll admin to acknowledge via the 'Acknowledge PCB Alert' action.
    """
    try:
        issues = detect_under_deduction(doc)
        if not issues:
            return

        if _has_acknowledgement(doc.name):
            return

        issue_lines = "\n".join(f"* {i['message']}" for i in issues)
        frappe.throw(
            _(
                "PCB Under-Deduction Alert (Section 107A ITA 1967):\n\n"
                "{issues}\n\n"
                "You must acknowledge this alert and provide a written justification "
                "before submitting this Salary Slip. Use the "
                "'Acknowledge PCB Alert' button."
            ).format(issues=issue_lines),
            title=_("PCB Under-Deduction -- Employer Liability Alert"),
        )
    except frappe.ValidationError:
        raise
    except Exception as exc:
        # Never let this check block normal payroll processing for unexpected errors
        frappe.log_error(
            f"PCB under-deduction check error on {getattr(doc, 'name', '?')}: {exc}",
            "PCB Under-Deduction Alert",
        )


@frappe.whitelist()
def acknowledge_pcb_under_deduction(salary_slip: str, reason: str) -> dict:
    """Record a payroll admin acknowledgement of a PCB under-deduction alert.

    Creates a ``PCB Change Log`` entry with ``change_type = 'Under-Deduction
    Acknowledged'`` so that the ``before_submit`` hook allows the Salary Slip
    to proceed.

    Args:
        salary_slip: Name of the Salary Slip document.
        reason: Documented justification text from the payroll admin.

    Returns:
        dict: ``{"success": True, "log": <PCB Change Log name>}``
    """
    if not reason or not str(reason).strip():
        frappe.throw(_("Acknowledgement reason is required."))

    slip = frappe.get_doc("Salary Slip", salary_slip)

    payroll_period = _get_payroll_period(slip)
    current_pcb = _get_pcb_amount(slip)

    log = frappe.get_doc({
        "doctype": "PCB Change Log",
        "employee": slip.employee,
        "employee_name": getattr(slip, "employee_name", ""),
        "payroll_period": payroll_period,
        "company": getattr(slip, "company", ""),
        "salary_slip": salary_slip,
        "change_type": "Under-Deduction Acknowledged",
        "old_pcb_amount": current_pcb,
        "new_pcb_amount": current_pcb,
        "changed_by": frappe.session.user,
        "reason": str(reason).strip(),
    })
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "log": log.name}
