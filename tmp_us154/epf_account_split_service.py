"""EPF Akaun Fleksibel Three-Account Contribution Split Service (US-154).

Effective 11 May 2024, EPF contributions are automatically split across three accounts:
  - Akaun Persaraan (Retirement):  75%
  - Akaun Sejahtera (Well-being):  15%
  - Akaun Fleksibel (Flexible):    10%

This service computes the per-account split from a total EPF contribution amount.

For employees above age 55 who have not joined the three-account restructuring,
the legacy two-account split applies:
  - Akaun 1 (Retirement):  70%
  - Akaun 2 (Well-being):  30%

Reference:
  KWSP New Account Structure circular, effective 11 May 2024.
  All contributions after 11 May 2024 follow the three-account structure.
  The 75/15/10 split ratio is fixed by EPF policy — no customisation permitted.
"""

import frappe
from datetime import date as _date
from frappe.utils import flt, getdate

# Three-account structure (effective 11 May 2024)
EPF_THREE_ACCOUNT_START = _date(2024, 5, 11)

AKAUN_PERSARAAN_RATE = 0.75   # 75%
AKAUN_SEJAHTERA_RATE = 0.15   # 15%
AKAUN_FLEKSIBEL_RATE = 0.10   # 10%

# Legacy two-account structure (employees above 55 who have not transitioned)
AKAUN_1_LEGACY_RATE = 0.70   # 70%
AKAUN_2_LEGACY_RATE = 0.30   # 30%

# Age threshold above which legacy two-account structure applies
LEGACY_AGE_THRESHOLD = 55


def is_three_account_applicable(payroll_date=None):
    """Return True if the three-account structure is applicable for the given payroll date.

    The three-account structure applies to all contributions on or after 11 May 2024.

    Args:
        payroll_date: datetime.date or str — the salary slip posting/end date.

    Returns:
        bool
    """
    ref_date = payroll_date or _date.today()
    if isinstance(ref_date, str):
        ref_date = getdate(ref_date)
    return ref_date >= EPF_THREE_ACCOUNT_START


def compute_epf_account_split(total_epf_amount, employee_doc=None, payroll_date=None):
    """Compute the EPF account split for the given total contribution amount.

    Args:
        total_epf_amount: float — total EPF employee or employer contribution in MYR.
        employee_doc: Frappe Employee doc (or None). Used to check age for legacy split.
        payroll_date: datetime.date — payroll period end/posting date.

    Returns:
        dict with keys:
            use_legacy (bool): True if two-account legacy split applies.
            accounts (list of dict): each dict has:
                name (str): account name
                rate (float): fraction (e.g. 0.75)
                amount (float): computed MYR amount
    """
    amount = flt(total_epf_amount)
    ref_date = payroll_date or _date.today()
    if isinstance(ref_date, str):
        ref_date = getdate(ref_date)

    use_legacy = _should_use_legacy_split(employee_doc, ref_date)

    if use_legacy:
        return {
            "use_legacy": True,
            "accounts": [
                {
                    "name": "Akaun 1 (Persaraan)",
                    "rate": AKAUN_1_LEGACY_RATE,
                    "amount": round(amount * AKAUN_1_LEGACY_RATE, 2),
                },
                {
                    "name": "Akaun 2 (Kesejahteraan)",
                    "rate": AKAUN_2_LEGACY_RATE,
                    "amount": round(amount * AKAUN_2_LEGACY_RATE, 2),
                },
            ],
        }

    # Three-account structure
    persaraan = round(amount * AKAUN_PERSARAAN_RATE, 2)
    sejahtera = round(amount * AKAUN_SEJAHTERA_RATE, 2)
    # Fleksibel gets the remainder to avoid rounding gaps
    fleksibel = round(amount - persaraan - sejahtera, 2)

    return {
        "use_legacy": False,
        "accounts": [
            {
                "name": "Akaun Persaraan (Retirement)",
                "rate": AKAUN_PERSARAAN_RATE,
                "amount": persaraan,
            },
            {
                "name": "Akaun Sejahtera (Well-being)",
                "rate": AKAUN_SEJAHTERA_RATE,
                "amount": sejahtera,
            },
            {
                "name": "Akaun Fleksibel (Flexible)",
                "rate": AKAUN_FLEKSIBEL_RATE,
                "amount": fleksibel,
            },
        ],
    }


def get_epf_split_for_salary_slip(salary_slip_doc):
    """Return EPF account split context for rendering on a payslip.

    Extracts employee EPF and employer EPF amounts from the Salary Slip
    deductions/earnings tables, then applies the three-account (or legacy) split.

    Args:
        salary_slip_doc: Frappe Salary Slip document.

    Returns:
        dict with:
            employee_epf_total (float)
            employer_epf_total (float)
            employee_split (dict from compute_epf_account_split)
            employer_split (dict from compute_epf_account_split)
            use_legacy (bool)
    """
    # Extract EPF amounts from the salary slip
    employee_epf_total = 0.0
    employer_epf_total = 0.0

    for row in (salary_slip_doc.get("deductions") or []):
        comp = (row.salary_component or "").upper()
        if "EPF" in comp and "EMPLOYEE" in comp:
            employee_epf_total += flt(row.amount)

    for row in (salary_slip_doc.get("earnings") or []):
        comp = (row.salary_component or "").upper()
        if "EPF" in comp and "EMPLOYER" in comp:
            employer_epf_total += flt(row.amount)

    # Load employee doc for age check
    employee_doc = None
    try:
        employee_doc = frappe.get_doc("Employee", salary_slip_doc.employee)
    except Exception:
        pass

    payroll_date = None
    try:
        payroll_date = getdate(salary_slip_doc.end_date or salary_slip_doc.posting_date)
    except Exception:
        pass

    employee_split = compute_epf_account_split(employee_epf_total, employee_doc, payroll_date)
    employer_split = compute_epf_account_split(employer_epf_total, employee_doc, payroll_date)

    return {
        "employee_epf_total": employee_epf_total,
        "employer_epf_total": employer_epf_total,
        "employee_split": employee_split,
        "employer_split": employer_split,
        "use_legacy": employee_split["use_legacy"],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_employee_age(employee_doc, ref_date):
    """Return employee age in years at ref_date, or None if DOB unavailable."""
    if employee_doc is None:
        return None
    dob = getattr(employee_doc, "date_of_birth", None)
    if dob is None:
        return None
    if isinstance(dob, str):
        dob = getdate(dob)
    try:
        age = (
            ref_date.year - dob.year
            - ((ref_date.month, ref_date.day) < (dob.month, dob.day))
        )
        return age
    except Exception:
        return None


def _should_use_legacy_split(employee_doc, ref_date):
    """Return True if the legacy two-account split should be used.

    Legacy applies when:
    - payroll_date is before the three-account effective date (11 May 2024), OR
    - employee is above 55 AND does not have the three-account flag set.

    In practice from 11 May 2024 KWSP enrolled all active members, so the
    'above 55 legacy' flag is a fallback for edge cases.
    """
    if not is_three_account_applicable(ref_date):
        return True  # Before 11 May 2024 — always legacy

    # After 11 May 2024: check employee flag
    if employee_doc is not None:
        use_three_account = getattr(employee_doc, "custom_epf_three_account", None)
        # If field explicitly set to 0 (False) for above-55 legacy members
        if use_three_account is not None and not use_three_account:
            age = _get_employee_age(employee_doc, ref_date)
            if age is not None and age > LEGACY_AGE_THRESHOLD:
                return True

    return False
