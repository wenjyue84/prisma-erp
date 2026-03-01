"""LINDUNG 24/7 Non-Occupational Accident Scheme — US-310.

Implements the Employee Second-Category Contribution Deduction Engine for
PERKESO's LINDUNG 24/7 scheme introduced by the Employees' Social Security
(Amendment) Bill 2025 (passed 2 December 2025).

Key facts:
- Parliament passed amendment on 2 December 2025.
- Contribution rates and gazette date are PENDING announcement (expected Q1/Q2 2026).
- BOTH employer AND employee must contribute to Second Category under the new scheme.
- Previously, only employers contributed to Second Category (Invalidity Scheme).

The deduction engine is dormant until:
  1. The gazette rate is entered in LHDN Payroll Settings.
  2. ``lindung_24_7_pending_gazette`` is cleared (set to 0).
  3. The gazette activation date is set AND reached.

Fields on LHDN Payroll Settings (singleton):
  - lindung_24_7_pending_gazette  (Check) — 1 = rates not yet gazetted (dormant)
  - lindung_24_7_employee_rate    (Float) — Employee contribution rate (e.g. 0.005 for 0.5%)
  - lindung_24_7_employer_rate    (Float) — Employer contribution rate
  - lindung_24_7_activation_date  (Date)  — Gazette effective date

Reference: perkeso.gov.my/en/rate-of-contribution.html
"""

import frappe
from frappe.utils import flt, getdate, nowdate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: LHDN Payroll Settings field — gazette pending flag (1 = pending, 0 = gazetted)
LINDUNG_PENDING_GAZETTE_FIELD = "lindung_24_7_pending_gazette"

#: LHDN Payroll Settings field — employee contribution rate (float, e.g. 0.005)
LINDUNG_EMPLOYEE_RATE_FIELD = "lindung_24_7_employee_rate"

#: LHDN Payroll Settings field — employer contribution rate (float, e.g. 0.005)
LINDUNG_EMPLOYER_RATE_FIELD = "lindung_24_7_employer_rate"

#: LHDN Payroll Settings field — gazette effective date (Date string)
LINDUNG_ACTIVATION_DATE_FIELD = "lindung_24_7_activation_date"

#: Payslip deduction label for the employee-side LINDUNG 24/7 contribution
LINDUNG_EMPLOYEE_DEDUCTION_LABEL = "LINDUNG 24/7 (Employee)"

#: Employer cost label for LINDUNG 24/7 employer share
LINDUNG_EMPLOYER_COST_LABEL = "LINDUNG 24/7 (Employer)"

#: Compliance warning shown on payslip when gazette rates are not yet published
PRE_GAZETTE_WARNING = (
    "LINDUNG 24/7 rates not yet gazetted \u2014 deduction not applied"
)

#: PERKESO ASSIST e-Caruman CSV column label for employee contribution
PERKESO_ASSIST_COLUMN = "LINDUNG 24/7 Employee (RM)"

#: PERKESO ASSIST e-Caruman CSV column label for employer contribution
PERKESO_ASSIST_EMPLOYER_COLUMN = "LINDUNG 24/7 Employer (RM)"


# ---------------------------------------------------------------------------
# Gazette status helpers
# ---------------------------------------------------------------------------

def is_lindung_gazette_active(as_of_date=None) -> bool:
    """Return True if the LINDUNG 24/7 gazette rate is set and the activation date reached.

    Conditions for active (all must be true):
      1. ``lindung_24_7_pending_gazette`` is falsy (gazette has been published).
      2. ``lindung_24_7_employee_rate`` > 0 (rate has been entered).
      3. ``lindung_24_7_activation_date`` is set AND <= ``as_of_date``.

    Args:
        as_of_date: Date to check against; defaults to today.

    Returns:
        bool — True if deductions should be applied for the given payroll date.
    """
    try:
        settings = frappe.get_single("LHDN Payroll Settings")
    except Exception:
        return False

    pending = settings.get(LINDUNG_PENDING_GAZETTE_FIELD)
    if pending:
        return False  # Gazette not yet published

    rate = flt(settings.get(LINDUNG_EMPLOYEE_RATE_FIELD))
    if rate <= 0:
        return False  # No rate configured

    activation_date = settings.get(LINDUNG_ACTIVATION_DATE_FIELD)
    if not activation_date:
        return False  # No activation date set

    check_date = getdate(as_of_date or nowdate())
    return check_date >= getdate(activation_date)


def get_pre_gazette_warning() -> str:
    """Return the compliance warning when LINDUNG 24/7 rates have not been gazetted.

    Returns:
        str — Warning text to display on payslip or payroll run output.
    """
    return PRE_GAZETTE_WARNING


def is_pending_gazette() -> bool:
    """Return True if the LINDUNG 24/7 gazette is still pending (rates not gazetted yet).

    Returns:
        bool — True if gazette pending flag is set or settings unavailable.
    """
    try:
        settings = frappe.get_single("LHDN Payroll Settings")
        pending = settings.get(LINDUNG_PENDING_GAZETTE_FIELD)
        return bool(pending)
    except Exception:
        return True  # Default to pending if settings unavailable


# ---------------------------------------------------------------------------
# Contribution computation
# ---------------------------------------------------------------------------

def compute_lindung_employee_contribution(gross_pay: float, as_of_date=None) -> dict:
    """Compute the LINDUNG 24/7 employee contribution for a given gross pay.

    Returns zero contribution with a pre-gazette warning when gazette is pending
    or the gazette activation date has not yet been reached.

    When active, reads ``lindung_24_7_employee_rate`` from LHDN Payroll Settings
    and applies it to gross_pay.

    Args:
        gross_pay:   Employee's gross monthly pay in MYR.
        as_of_date:  Payroll date for gazette activation check; defaults to today.

    Returns:
        dict with keys:
            ``amount``   — Employee LINDUNG 24/7 deduction amount (RM).
            ``rate``     — Applied rate (0.0 if not yet active).
            ``active``   — True if deduction was applied.
            ``warning``  — Pre-gazette warning string (empty string if active).
            ``label``    — Payslip deduction label.
    """
    if not is_lindung_gazette_active(as_of_date):
        return {
            "amount": 0.00,
            "rate": 0.00,
            "active": False,
            "warning": PRE_GAZETTE_WARNING,
            "label": LINDUNG_EMPLOYEE_DEDUCTION_LABEL,
        }

    try:
        settings = frappe.get_single("LHDN Payroll Settings")
        rate = flt(settings.get(LINDUNG_EMPLOYEE_RATE_FIELD))
    except Exception:
        rate = 0.00

    amount = round(flt(gross_pay) * rate, 2)
    return {
        "amount": amount,
        "rate": rate,
        "active": True,
        "warning": "",
        "label": LINDUNG_EMPLOYEE_DEDUCTION_LABEL,
    }


def compute_lindung_employer_contribution(gross_pay: float, as_of_date=None) -> dict:
    """Compute the LINDUNG 24/7 employer contribution for a given gross pay.

    Mirrors ``compute_lindung_employee_contribution()`` but reads the employer rate
    from ``lindung_24_7_employer_rate`` in LHDN Payroll Settings.

    Args:
        gross_pay:   Employee's gross monthly pay in MYR.
        as_of_date:  Payroll date for gazette activation check; defaults to today.

    Returns:
        dict with keys:
            ``amount``   — Employer LINDUNG 24/7 cost amount (RM).
            ``rate``     — Applied rate (0.0 if not yet active).
            ``active``   — True if contribution was applied.
            ``label``    — Employer cost label.
    """
    if not is_lindung_gazette_active(as_of_date):
        return {
            "amount": 0.00,
            "rate": 0.00,
            "active": False,
            "label": LINDUNG_EMPLOYER_COST_LABEL,
        }

    try:
        settings = frappe.get_single("LHDN Payroll Settings")
        rate = flt(settings.get(LINDUNG_EMPLOYER_RATE_FIELD))
    except Exception:
        rate = 0.00

    amount = round(flt(gross_pay) * rate, 2)
    return {
        "amount": amount,
        "rate": rate,
        "active": True,
        "label": LINDUNG_EMPLOYER_COST_LABEL,
    }


# ---------------------------------------------------------------------------
# HR Manager alert
# ---------------------------------------------------------------------------

def get_gazette_alert_message(gazette_rate: float, activation_date: str) -> str:
    """Return the formatted gazette alert message for HR Managers.

    Called when the gazette rate is entered into LHDN Payroll Settings.
    HR Managers should be notified to recalculate payroll from the effective date.

    Args:
        gazette_rate:    Employee contribution rate (e.g. 0.005 for 0.5%).
        activation_date: Gazette effective date string (YYYY-MM-DD).

    Returns:
        str — Alert message text.
    """
    return (
        f"LINDUNG 24/7 gazette rate has been entered: {gazette_rate:.4%}. "
        f"The deduction will activate from {activation_date}. "
        f"Please recalculate payroll from the gazette effective date."
    )


def send_gazette_activation_alert(gazette_rate: float, activation_date: str) -> None:
    """Send a system alert to HR Managers when the gazette rate is entered.

    Publishes a real-time notification to all users with the HR Manager role
    prompting payroll recalculation from the gazette effective date.

    Args:
        gazette_rate:    The newly entered employee contribution rate.
        activation_date: The gazette effective date (string YYYY-MM-DD).
    """
    message = get_gazette_alert_message(gazette_rate, activation_date)
    try:
        hr_managers = frappe.get_all(
            "Has Role",
            filters={"role": "HR Manager", "parenttype": "User"},
            pluck="parent",
        )
        for user in hr_managers:
            frappe.publish_realtime(
                "msgprint",
                {
                    "message": message,
                    "title": "LINDUNG 24/7 Gazette Rate Activated",
                    "indicator": "orange",
                },
                user=user,
            )
        frappe.logger().info(
            f"LINDUNG 24/7 gazette activation alert sent to {len(hr_managers)} HR Manager(s). "
            f"Rate: {gazette_rate:.4%}, Effective: {activation_date}"
        )
    except Exception as e:
        frappe.log_error(
            title="LINDUNG 24/7 Alert Error",
            message=f"Failed to send gazette activation alert: {str(e)}",
        )


# ---------------------------------------------------------------------------
# PERKESO ASSIST e-Caruman integration
# ---------------------------------------------------------------------------

def get_perkeso_assist_lindung_amounts(gross_pay: float, as_of_date=None) -> dict:
    """Return LINDUNG 24/7 contribution amounts for a PERKESO ASSIST e-Caruman row.

    Provides both employee and employer LINDUNG 24/7 amounts in the format
    expected by the PERKESO ASSIST bulk upload CSV.

    When the gazette is pending, both amounts are 0.00 and ``active`` is False.

    Args:
        gross_pay:  Employee's gross pay in MYR.
        as_of_date: Payroll date for gazette activation check.

    Returns:
        dict with keys:
            ``employee_amount``    — Employee LINDUNG 24/7 contribution (RM).
            ``employer_amount``    — Employer LINDUNG 24/7 contribution (RM).
            ``active``             — True if gazette is active and amounts applied.
            ``column_label_ee``    — CSV column label for employee amount.
            ``column_label_er``    — CSV column label for employer amount.
    """
    emp_result = compute_lindung_employee_contribution(gross_pay, as_of_date)
    er_result = compute_lindung_employer_contribution(gross_pay, as_of_date)

    return {
        "employee_amount": emp_result["amount"],
        "employer_amount": er_result["amount"],
        "active": emp_result["active"],
        "column_label_ee": PERKESO_ASSIST_COLUMN,
        "column_label_er": PERKESO_ASSIST_EMPLOYER_COLUMN,
    }
