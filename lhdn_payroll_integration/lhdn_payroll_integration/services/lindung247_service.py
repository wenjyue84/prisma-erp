"""PERKESO LINDUNG 24/7 — Second-Category Employee Contribution Deduction Engine.

US-310: Employees' Social Security (Amendment) Bill 2025 — LINDUNG 24/7 Scheme.

Parliament passed the amendment on 2 December 2025 introducing the LINDUNG 24/7
Non-Occupational Accident Scheme under Second Category. A fundamental structural
change: BOTH employers AND employees must now contribute (previously only employers
contributed to Second Category / Invalidity Scheme).

CRITICAL: Contribution rates are PENDING gazette announcement (expected Q1/Q2 2026).
Payroll deductions MUST NOT be applied until:
  1. The gazette rate is entered in LHDN Payroll Settings, AND
  2. The activation date is reached.

If rates are not yet gazetted, a compliance warning is shown on payslips and
payroll runs — deduction is NOT applied.

Configuration fields on LHDN Payroll Settings (Single DocType):
  - lindung247_gazette_status       : Select "Pending Gazette" | "Active"
  - lindung247_activation_date      : Date (gazette effective date)
  - lindung247_employee_rate        : Float (e.g. 0.005 = 0.5%)
  - lindung247_employer_rate        : Float (e.g. 0.005 = 0.5%)
  - lindung247_wage_ceiling         : Currency (RM ceiling for contribution calculation)

Reference: perkeso.gov.my/en/rate-of-contribution.html
"""

import csv
import io
import frappe
from frappe.utils import getdate, nowdate, today


# ---------------------------------------------------------------------------
# Module Constants
# ---------------------------------------------------------------------------

#: Gazette status values
LINDUNG247_STATUS_PENDING = "Pending Gazette"
LINDUNG247_STATUS_ACTIVE = "Active"

#: Default contribution rates (placeholder — MUST be confirmed via gazette)
#: Set to 0.0 until official gazette announcement
LINDUNG247_DEFAULT_EMPLOYEE_RATE = 0.0  # TBD via PERKESO gazette
LINDUNG247_DEFAULT_EMPLOYER_RATE = 0.0  # TBD via PERKESO gazette

#: Default wage ceiling (RM) — to be confirmed by gazette
LINDUNG247_DEFAULT_WAGE_CEILING = 6000.00  # assumes same ceiling as SOCSO First Category

#: Payslip line item label for the new employee deduction
LINDUNG247_PAYSLIP_LABEL = "LINDUNG 24/7 (Employee)"

#: Payslip line item label for employer cost
LINDUNG247_EMPLOYER_LABEL = "LINDUNG 24/7 (Employer)"

#: Compliance warning shown on payslips when rates are not yet gazetted
LINDUNG247_COMPLIANCE_WARNING = (
    "LINDUNG 24/7 rates not yet gazetted \u2014 deduction not applied"
)

#: LHDN Payroll Settings field names
SETTINGS_DOCTYPE = "LHDN Payroll Settings"
FIELD_GAZETTE_STATUS = "lindung247_gazette_status"
FIELD_ACTIVATION_DATE = "lindung247_activation_date"
FIELD_EMPLOYEE_RATE = "lindung247_employee_rate"
FIELD_EMPLOYER_RATE = "lindung247_employer_rate"
FIELD_WAGE_CEILING = "lindung247_wage_ceiling"


# ---------------------------------------------------------------------------
# Settings Access
# ---------------------------------------------------------------------------

def get_lindung247_settings() -> dict:
    """Read LINDUNG 24/7 configuration from LHDN Payroll Settings.

    Returns:
        dict with keys: gazette_status, activation_date, employee_rate,
        employer_rate, wage_ceiling.
    """
    try:
        settings = frappe.get_single(SETTINGS_DOCTYPE)
        return {
            "gazette_status": settings.get(FIELD_GAZETTE_STATUS) or LINDUNG247_STATUS_PENDING,
            "activation_date": settings.get(FIELD_ACTIVATION_DATE),
            "employee_rate": float(settings.get(FIELD_EMPLOYEE_RATE) or 0.0),
            "employer_rate": float(settings.get(FIELD_EMPLOYER_RATE) or 0.0),
            "wage_ceiling": float(settings.get(FIELD_WAGE_CEILING) or LINDUNG247_DEFAULT_WAGE_CEILING),
        }
    except Exception:
        return {
            "gazette_status": LINDUNG247_STATUS_PENDING,
            "activation_date": None,
            "employee_rate": LINDUNG247_DEFAULT_EMPLOYEE_RATE,
            "employer_rate": LINDUNG247_DEFAULT_EMPLOYER_RATE,
            "wage_ceiling": LINDUNG247_DEFAULT_WAGE_CEILING,
        }


# ---------------------------------------------------------------------------
# Activation Guard
# ---------------------------------------------------------------------------

def is_lindung247_active(as_of_date=None) -> bool:
    """Return True if LINDUNG 24/7 deductions are fully active.

    Both conditions must be met:
      1. gazette_status == "Active" (rate has been officially gazetted)
      2. activation_date is set and on or before as_of_date

    Pre-gazette payroll runs must return False so the compliance warning
    is displayed instead of applying a deduction.

    Args:
        as_of_date: Date to evaluate against; defaults to today.

    Returns:
        True if LINDUNG 24/7 is active and rates apply, False otherwise.
    """
    cfg = get_lindung247_settings()

    if cfg["gazette_status"] != LINDUNG247_STATUS_ACTIVE:
        return False

    if not cfg["activation_date"]:
        return False

    check_date = getdate(as_of_date or nowdate())
    return check_date >= getdate(cfg["activation_date"])


# ---------------------------------------------------------------------------
# Core Computation
# ---------------------------------------------------------------------------

def compute_lindung247_contribution(gross_pay: float, employee_rate: float,
                                    employer_rate: float, wage_ceiling: float) -> dict:
    """Compute LINDUNG 24/7 employee and employer contribution amounts.

    Both employer and employee contribute under Second Category per
    the Employees' Social Security (Amendment) Bill 2025.

    Args:
        gross_pay:     Monthly gross pay in RM.
        employee_rate: Employee contribution rate (e.g. 0.005 = 0.5%).
        employer_rate: Employer contribution rate (e.g. 0.005 = 0.5%).
        wage_ceiling:  Maximum insurable earnings ceiling in RM.

    Returns:
        dict with keys:
            ``employee``          — Employee deduction amount (RM)
            ``employer``          — Employer contribution amount (RM)
            ``insurable_earnings``— Capped gross pay used for calculation
            ``employee_rate``     — Rate used for employee
            ``employer_rate``     — Rate used for employer
    """
    insurable = min(float(gross_pay), float(wage_ceiling))

    employee_amount = round(insurable * float(employee_rate), 2)
    employer_amount = round(insurable * float(employer_rate), 2)

    return {
        "employee": employee_amount,
        "employer": employer_amount,
        "insurable_earnings": round(insurable, 2),
        "employee_rate": employee_rate,
        "employer_rate": employer_rate,
    }


# ---------------------------------------------------------------------------
# Payslip Integration
# ---------------------------------------------------------------------------

def get_lindung247_payslip_line(gross_pay: float, as_of_date=None) -> dict:
    """Return the LINDUNG 24/7 payslip deduction line item.

    If the scheme is not yet active (pre-gazette), returns a zero-amount entry
    with the compliance warning attached.

    Args:
        gross_pay:   Monthly gross pay in RM.
        as_of_date:  Payroll period date; defaults to today.

    Returns:
        dict with keys:
            ``label``      — Display label for payslip
            ``amount``     — Deduction amount (0.0 if pre-gazette)
            ``is_active``  — True if deduction is being applied
            ``warning``    — Compliance warning string (empty if active)
    """
    if not is_lindung247_active(as_of_date):
        return {
            "label": LINDUNG247_PAYSLIP_LABEL,
            "amount": 0.0,
            "is_active": False,
            "warning": LINDUNG247_COMPLIANCE_WARNING,
        }

    cfg = get_lindung247_settings()
    contrib = compute_lindung247_contribution(
        gross_pay,
        cfg["employee_rate"],
        cfg["employer_rate"],
        cfg["wage_ceiling"],
    )

    return {
        "label": LINDUNG247_PAYSLIP_LABEL,
        "amount": contrib["employee"],
        "is_active": True,
        "warning": "",
    }


def get_lindung247_employer_cost(gross_pay: float, as_of_date=None) -> dict:
    """Return the employer LINDUNG 24/7 contribution cost.

    Args:
        gross_pay:  Monthly gross pay in RM.
        as_of_date: Payroll period date; defaults to today.

    Returns:
        dict with keys:
            ``label``     — Display label
            ``amount``    — Employer contribution amount (0.0 if pre-gazette)
            ``is_active`` — True if contribution is being applied
            ``warning``   — Compliance warning string (empty if active)
    """
    if not is_lindung247_active(as_of_date):
        return {
            "label": LINDUNG247_EMPLOYER_LABEL,
            "amount": 0.0,
            "is_active": False,
            "warning": LINDUNG247_COMPLIANCE_WARNING,
        }

    cfg = get_lindung247_settings()
    contrib = compute_lindung247_contribution(
        gross_pay,
        cfg["employee_rate"],
        cfg["employer_rate"],
        cfg["wage_ceiling"],
    )

    return {
        "label": LINDUNG247_EMPLOYER_LABEL,
        "amount": contrib["employer"],
        "is_active": True,
        "warning": "",
    }


# ---------------------------------------------------------------------------
# Compliance Warning
# ---------------------------------------------------------------------------

def get_lindung247_compliance_warning() -> str:
    """Return the compliance warning string if LINDUNG 24/7 is not yet active.

    Returns:
        The compliance warning string if not gazetted/active, or empty string
        if the scheme is active and deductions are being applied.
    """
    if is_lindung247_active():
        return ""
    return LINDUNG247_COMPLIANCE_WARNING


# ---------------------------------------------------------------------------
# HR Manager Alert
# ---------------------------------------------------------------------------

def alert_hr_gazette_rate_entered(doc, method=None):
    """Send system alert to HR Manager when gazette rate is entered.

    Triggered as a doc_event on LHDN Payroll Settings (on_update).
    Fires only when gazette_status changes to 'Active' and
    lindung247_activation_date is set.

    Args:
        doc:    The LHDN Payroll Settings document.
        method: Frappe event method name (unused).
    """
    gazette_status = doc.get(FIELD_GAZETTE_STATUS) or ""
    activation_date = doc.get(FIELD_ACTIVATION_DATE)
    employee_rate = doc.get(FIELD_EMPLOYEE_RATE)
    employer_rate = doc.get(FIELD_EMPLOYER_RATE)

    if gazette_status != LINDUNG247_STATUS_ACTIVE:
        return

    if not activation_date or not employee_rate:
        return

    # Find HR Manager users to notify
    hr_managers = frappe.get_all(
        "User",
        filters={"enabled": 1},
        fields=["name", "email"],
    )

    message = (
        f"LINDUNG 24/7 gazette rate has been entered. "
        f"Employee rate: {float(employee_rate or 0) * 100:.2f}%, "
        f"Employer rate: {float(employer_rate or 0) * 100:.2f}%. "
        f"Effective from: {activation_date}. "
        f"Please recalculate payroll from the gazette effective date."
    )

    for user in hr_managers:
        frappe.publish_realtime(
            "lindung247_gazette_alert",
            {"message": message, "activation_date": str(activation_date)},
            user=user["name"],
        )

    frappe.log_error(
        title="LINDUNG 24/7 Gazette Rate Entered",
        message=message,
    )


# ---------------------------------------------------------------------------
# PERKESO ASSIST e-Caruman Integration
# ---------------------------------------------------------------------------

def generate_eccaruman_lindung247_rows(company: str, year: int, month: int) -> list:
    """Generate LINDUNG 24/7 data rows for PERKESO ASSIST e-Caruman upload.

    Returns a list of dicts, one per employee, with LINDUNG 24/7 employer
    and employee contribution amounts. These are appended to or included in
    the monthly e-Caruman submission.

    If LINDUNG 24/7 is not yet active (pre-gazette), returns an empty list
    (no contribution rows to submit).

    Args:
        company: Company name filter.
        year:    Payroll year (e.g. 2026).
        month:   Payroll month (1-12).

    Returns:
        List of dicts with keys:
            ``employee``            — Employee name/ID
            ``employee_name``       — Employee display name
            ``nric``                — NRIC/Passport number
            ``gross_pay``           — Gross pay for the period
            ``insurable_earnings``  — Capped insurable earnings
            ``lindung247_employee`` — Employee contribution amount
            ``lindung247_employer`` — Employer contribution amount
    """
    if not is_lindung247_active():
        return []

    cfg = get_lindung247_settings()
    from frappe.utils import get_first_day, get_last_day

    period_start = get_first_day(f"{year}-{month:02d}-01")
    period_end = get_last_day(f"{year}-{month:02d}-01")

    slips = frappe.db.sql(
        """
        SELECT
            ss.employee,
            ss.employee_name,
            ss.gross_pay,
            e.custom_icpassport_number AS nric
        FROM `tabSalary Slip` ss
        INNER JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE ss.company = %(company)s
          AND ss.docstatus = 1
          AND ss.start_date >= %(start)s
          AND ss.end_date <= %(end)s
        ORDER BY ss.employee
        """,
        {
            "company": company,
            "start": str(period_start),
            "end": str(period_end),
        },
        as_dict=True,
    )

    rows = []
    for row in slips:
        gross = float(row.get("gross_pay") or 0)
        contrib = compute_lindung247_contribution(
            gross,
            cfg["employee_rate"],
            cfg["employer_rate"],
            cfg["wage_ceiling"],
        )
        rows.append({
            "employee": row["employee"],
            "employee_name": row.get("employee_name") or "",
            "nric": row.get("nric") or "",
            "gross_pay": gross,
            "insurable_earnings": contrib["insurable_earnings"],
            "lindung247_employee": contrib["employee"],
            "lindung247_employer": contrib["employer"],
        })

    return rows


def generate_eccaruman_lindung247_csv(company: str, year: int, month: int) -> str:
    """Generate CSV string of LINDUNG 24/7 e-Caruman data.

    Args:
        company: Company name.
        year:    Year.
        month:   Month (1–12).

    Returns:
        CSV string ready for PERKESO ASSIST portal upload,
        or empty string if LINDUNG 24/7 is not yet active.
    """
    rows = generate_eccaruman_lindung247_rows(company, year, month)

    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "NRIC/Passport",
        "Employee Name",
        "Gross Pay (RM)",
        "Insurable Earnings (RM)",
        "LINDUNG 24/7 Employee (RM)",
        "LINDUNG 24/7 Employer (RM)",
    ])

    total_emp = 0.0
    total_er = 0.0
    for row in rows:
        writer.writerow([
            row["nric"],
            row["employee_name"],
            f"{row['gross_pay']:.2f}",
            f"{row['insurable_earnings']:.2f}",
            f"{row['lindung247_employee']:.2f}",
            f"{row['lindung247_employer']:.2f}",
        ])
        total_emp += row["lindung247_employee"]
        total_er += row["lindung247_employer"]

    writer.writerow([])
    writer.writerow([
        "TOTAL", "", "", "",
        f"{total_emp:.2f}",
        f"{total_er:.2f}",
    ])

    return output.getvalue()
