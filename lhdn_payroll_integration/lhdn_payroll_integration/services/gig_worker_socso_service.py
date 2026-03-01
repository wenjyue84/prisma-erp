"""Gig Worker SOCSO Deduction Engine — US-167.

Implements the Self-Employment Social Security (SEIA Act 789) contribution engine
for platform workers under the Gig Workers Act 2025 (Act 872).

Key rules:
- Worker-funded only: SEIA rate applies to the gig worker's earnings; employer/platform
  has ZERO employer-share contribution.
- Commencement date guard: deductions only activate after the official gazette date stored
  in LHDN Payroll Settings (``seia_commencement_date``).
- Domestic gig worker exemption: workers flagged ``custom_is_domestic_gig_exempt = 1``
  are excluded (home cleaning, babysitting platforms per SEIA exemption schedule).
- PERKESO ASSIST upload format for SEIA gig workers differs from the standard employer
  SOCSO bulk upload — generated as a separate monthly file.

SEIA Contribution Rate Schedule (SOCSO Self-Employment Scheme):
  Rate: 2.0% of the worker's chargeable earnings
  Minimum contribution: RM5.00 per month
  Maximum insurable earnings: RM5,000/month (ceiling per SEIA Act 789)

All rates/ceilings defined as module constants for easy future update.
"""

import csv
import io
import frappe
from frappe.utils import getdate, nowdate, get_first_day, get_last_day, formatdate


# ---------------------------------------------------------------------------
# Constants (SEIA Act 789 schedule — update as regulations change)
# ---------------------------------------------------------------------------

#: SEIA worker contribution rate (worker-funded only, no employer share)
SEIA_WORKER_RATE = 0.02  # 2.0%

#: Maximum insurable monthly earnings under SEIA
SEIA_EARNINGS_CEILING = 5000.00  # RM 5,000

#: Minimum monthly contribution floor
SEIA_MIN_CONTRIBUTION = 5.00  # RM 5.00

#: Employer share — always zero for SEIA (worker-funded scheme)
SEIA_EMPLOYER_RATE = 0.00

#: Employment type string used for gig/platform workers
GIG_WORKER_EMPLOYMENT_TYPE = "Gig / Platform Worker"

#: Domestic gig worker exclusion flag on Employee DocType
DOMESTIC_GIG_EXEMPT_FLAG = "custom_is_domestic_gig_exempt"

#: LHDN Payroll Settings field storing the gazette commencement date
SEIA_COMMENCEMENT_DATE_FIELD = "seia_commencement_date"


# ---------------------------------------------------------------------------
# Core deduction computation
# ---------------------------------------------------------------------------

def compute_seia_contribution(monthly_earnings: float) -> dict:
    """Compute the SEIA worker contribution for a given monthly earnings amount.

    Args:
        monthly_earnings: Gross monthly earnings (before deductions) for the
            gig worker on the platform.

    Returns:
        dict with keys:
            ``worker``  — SEIA deduction amount (worker-funded)
            ``employer``— always 0.00 (SEIA is worker-funded only)
            ``insurable_earnings`` — capped earnings used for calculation
            ``rate``    — SEIA worker rate (0.02)
    """
    insurable = min(float(monthly_earnings), SEIA_EARNINGS_CEILING)
    raw = insurable * SEIA_WORKER_RATE
    worker_amount = max(raw, SEIA_MIN_CONTRIBUTION) if insurable > 0 else 0.00

    return {
        "worker": round(worker_amount, 2),
        "employer": 0.00,
        "insurable_earnings": round(insurable, 2),
        "rate": SEIA_WORKER_RATE,
    }


# ---------------------------------------------------------------------------
# Eligibility checks
# ---------------------------------------------------------------------------

def is_seia_active(as_of_date=None) -> bool:
    """Return True if the SEIA commencement date has been set and passed.

    Reads ``seia_commencement_date`` from the "LHDN Payroll Settings" singleton.
    If the field is blank or not yet set, returns False (deductions remain dormant).

    Args:
        as_of_date: Date to compare against; defaults to today.
    """
    try:
        settings = frappe.get_single("LHDN Payroll Settings")
        commencement = settings.get(SEIA_COMMENCEMENT_DATE_FIELD)
    except Exception:
        return False

    if not commencement:
        return False

    check_date = getdate(as_of_date or nowdate())
    return check_date >= getdate(commencement)


def is_gig_worker(employee_doc) -> bool:
    """Return True if this Employee is a Gig/Platform Worker.

    Checks ``custom_employment_type == "Gig / Platform Worker"`` and
    the SEIA Self-Employment contribution flag ``custom_is_seia_worker = 1``.
    """
    emp_type = employee_doc.get("custom_employment_type") or ""
    seia_flag = employee_doc.get("custom_is_seia_worker")
    return emp_type == GIG_WORKER_EMPLOYMENT_TYPE and bool(seia_flag)


def is_domestic_gig_exempt(employee_doc) -> bool:
    """Return True if the gig worker is excluded under the SEIA exemption schedule.

    Domestic gig workers (home cleaning, babysitting, etc.) may be excluded
    per the SEIA Act 789 exemption schedule.
    """
    return bool(employee_doc.get(DOMESTIC_GIG_EXEMPT_FLAG))


def get_eligible_gig_workers(company=None):
    """Return list of Employee names that are eligible for SEIA deduction.

    Filters for:
    - custom_employment_type = "Gig / Platform Worker"
    - custom_is_seia_worker = 1
    - custom_is_domestic_gig_exempt = 0 or blank

    Args:
        company: Optional company filter.

    Returns:
        List of Employee names (strings).
    """
    filters = {
        "custom_employment_type": GIG_WORKER_EMPLOYMENT_TYPE,
        "custom_is_seia_worker": 1,
        "custom_is_domestic_gig_exempt": 0,
        "status": "Active",
    }
    if company:
        filters["company"] = company

    records = frappe.get_all("Employee", filters=filters, pluck="name")
    return records


# ---------------------------------------------------------------------------
# PERKESO remittance file generation
# ---------------------------------------------------------------------------

def generate_seia_remittance_file(company: str, year: int, month: int) -> str:
    """Generate the monthly PERKESO ASSIST SEIA remittance file (CSV).

    The SEIA gig worker upload is a separate file from the standard employer
    SOCSO Borang 8A. Each row contains:
        NRIC | Employee Name | Gross Earnings | Insurable Earnings | SEIA Amount

    Args:
        company: Company name to filter Salary Slips.
        year:    Payroll year (e.g. 2026).
        month:   Payroll month (1–12).

    Returns:
        CSV string ready for upload to PERKESO ASSIST portal.
    """
    from frappe.utils import get_first_day, get_last_day
    import datetime

    period_start = get_first_day(f"{year}-{month:02d}-01")
    period_end = get_last_day(f"{year}-{month:02d}-01")

    # Fetch submitted Salary Slips for gig workers in the period
    slips = frappe.db.sql(
        """
        SELECT
            ss.name AS slip_name,
            ss.employee,
            ss.employee_name,
            ss.gross_pay,
            e.custom_icpassport_number,
            e.custom_is_domestic_gig_exempt
        FROM `tabSalary Slip` ss
        INNER JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE ss.company = %(company)s
          AND ss.docstatus = 1
          AND ss.start_date >= %(start)s
          AND ss.end_date <= %(end)s
          AND e.custom_employment_type = %(emp_type)s
          AND e.custom_is_seia_worker = 1
        ORDER BY ss.employee
        """,
        {
            "company": company,
            "start": str(period_start),
            "end": str(period_end),
            "emp_type": GIG_WORKER_EMPLOYMENT_TYPE,
        },
        as_dict=True,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "NRIC/Passport",
        "Employee Name",
        "Gross Earnings (RM)",
        "Insurable Earnings (RM)",
        "SEIA Contribution (RM)",
        "Employer Share (RM)",
        "Excluded (Domestic Exempt)",
    ])

    total_seia = 0.0
    for row in slips:
        exempt = bool(row.get("custom_is_domestic_gig_exempt"))
        gross = row.get("gross_pay") or 0
        contrib = compute_seia_contribution(gross) if not exempt else {"worker": 0.0, "employer": 0.0, "insurable_earnings": 0.0, "rate": 0.0}
        total_seia += contrib["worker"]
        writer.writerow([
            row.get("custom_icpassport_number") or "",
            row.get("employee_name") or "",
            f"{gross:.2f}",
            f"{contrib['insurable_earnings']:.2f}",
            f"{contrib['worker']:.2f}",
            f"{contrib['employer']:.2f}",
            "Yes" if exempt else "No",
        ])

    # Footer total
    writer.writerow([])
    writer.writerow(["TOTAL SEIA", "", "", "", f"{total_seia:.2f}", "0.00", ""])

    return output.getvalue()
