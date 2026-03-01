"""CP500 Bi-Monthly Advance Tax Installment Tracker Service (US-233).

Provides advisory tracking for directors and sole proprietors who hold
CP500 obligations from LHDN.  CP500 is paid directly by the individual
to LHDN (not deducted via payroll) so this module is **read-only /
advisory** — it never auto-deducts anything.

Key concepts:
- CP500 has 6 bi-monthly installments: Mar, May, Jul, Sep, Nov, Jan
- First revision deadline: 30 June of assessment year
- Second revision deadline: 31 October of assessment year
- `cp500_payer` flag and `cp500_annual_installment_amount` on Employee record
- Child-table style tracker with due dates and payment references
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CP500_INSTALLMENT_MONTHS = [3, 5, 7, 9, 11, 1]  # Mar, May, Jul, Sep, Nov, Jan

CP500_INSTALLMENT_MONTH_NAMES = [
    "March", "May", "July", "September", "November", "January",
]

CP500_INSTALLMENT_COUNT = 6

CP500_DUE_DAY = 15  # Installments are due by the 15th of the month

FIRST_REVISION_DEADLINE_MONTH = 6   # 30 June
FIRST_REVISION_DEADLINE_DAY = 30

SECOND_REVISION_DEADLINE_MONTH = 10  # 31 October
SECOND_REVISION_DEADLINE_DAY = 31

UPCOMING_WINDOW_DAYS = 30  # Dashboard widget: "within next 30 days"

ADVISORY_NOTE = (
    "Employee has CP500 obligations \u2014 confirm PCB deduction "
    "does not exceed actual tax liability"
)


# ---------------------------------------------------------------------------
# Employee flag helpers
# ---------------------------------------------------------------------------

def is_cp500_payer(employee_record):
    """Return True if the employee/director record has cp500_payer set."""
    return bool(employee_record.get("cp500_payer"))


def get_annual_installment_amount(employee_record):
    """Return the CP500 annual installment amount, defaulting to 0."""
    return float(employee_record.get("cp500_annual_installment_amount") or 0)


def get_per_installment_amount(employee_record):
    """Annual amount divided equally across 6 bi-monthly installments."""
    annual = get_annual_installment_amount(employee_record)
    if annual <= 0:
        return 0.0
    return round(annual / CP500_INSTALLMENT_COUNT, 2)


# ---------------------------------------------------------------------------
# Installment schedule generation
# ---------------------------------------------------------------------------

def generate_installment_schedule(assessment_year):
    """Return a list of 6 dicts with installment month, due_date for a given
    assessment year.

    The January installment belongs to the *next* calendar year.
    E.g. for AY 2026: Mar-Nov 2026 + Jan 2027.
    """
    schedule = []
    for month in CP500_INSTALLMENT_MONTHS:
        if month == 1:
            cal_year = assessment_year + 1
        else:
            cal_year = assessment_year
        due = date(cal_year, month, CP500_DUE_DAY)
        schedule.append({
            "installment_month": month,
            "installment_month_name": CP500_INSTALLMENT_MONTH_NAMES[
                CP500_INSTALLMENT_MONTHS.index(month)
            ],
            "due_date": due,
            "assessment_year": assessment_year,
        })
    return schedule


def get_next_due_date(reference_date, assessment_year):
    """Return the next upcoming CP500 due date on or after *reference_date*
    within the given assessment year schedule.  Returns None if all
    installments for that AY have passed.
    """
    schedule = generate_installment_schedule(assessment_year)
    for entry in schedule:
        if entry["due_date"] >= reference_date:
            return entry["due_date"]
    return None


def get_days_until_next_installment(reference_date, assessment_year):
    """Days until the next CP500 installment due date.  Returns None when
    no future installment exists in the AY.
    """
    next_due = get_next_due_date(reference_date, assessment_year)
    if next_due is None:
        return None
    return (next_due - reference_date).days


# ---------------------------------------------------------------------------
# Installment record helpers
# ---------------------------------------------------------------------------

def create_installment_record(installment_month, due_date, assessment_year,
                               payment_ref=None, paid_date=None, amount=0):
    """Build a dict representing one CP500 installment tracker row."""
    return {
        "installment_month": installment_month,
        "due_date": due_date,
        "assessment_year": assessment_year,
        "payment_ref": payment_ref or "",
        "paid_date": paid_date,
        "amount": float(amount),
        "status": "Paid" if paid_date else "Unpaid",
    }


def mark_installment_paid(record, payment_ref, paid_date, amount=None):
    """Update an installment record as paid."""
    record["payment_ref"] = payment_ref
    record["paid_date"] = paid_date
    if amount is not None:
        record["amount"] = float(amount)
    record["status"] = "Paid"
    return record


def is_installment_overdue(record, reference_date):
    """True if installment is unpaid and due_date has passed."""
    if record.get("status") == "Paid":
        return False
    due = record.get("due_date")
    if due is None:
        return False
    if isinstance(due, str):
        due = date.fromisoformat(due)
    return reference_date > due


# ---------------------------------------------------------------------------
# Revision deadlines
# ---------------------------------------------------------------------------

def get_revision_deadlines(assessment_year):
    """Return first and second CP500 revision deadlines for an AY."""
    return {
        "first_revision": date(assessment_year, FIRST_REVISION_DEADLINE_MONTH,
                               FIRST_REVISION_DEADLINE_DAY),
        "second_revision": date(assessment_year, SECOND_REVISION_DEADLINE_MONTH,
                                SECOND_REVISION_DEADLINE_DAY),
    }


def can_revise_cp500(reference_date, assessment_year):
    """Whether a revision is still possible (before 31 Oct of AY)."""
    deadlines = get_revision_deadlines(assessment_year)
    return reference_date <= deadlines["second_revision"]


def get_next_revision_deadline(reference_date, assessment_year):
    """Return the next revision deadline on or after *reference_date*, or
    None if both have passed.
    """
    deadlines = get_revision_deadlines(assessment_year)
    if reference_date <= deadlines["first_revision"]:
        return deadlines["first_revision"]
    if reference_date <= deadlines["second_revision"]:
        return deadlines["second_revision"]
    return None


# ---------------------------------------------------------------------------
# Advisory note for payroll summary
# ---------------------------------------------------------------------------

def get_payroll_advisory(employee_record):
    """Return an advisory note string if the employee is a CP500 payer,
    otherwise return empty string.
    """
    if not is_cp500_payer(employee_record):
        return ""
    return ADVISORY_NOTE


# ---------------------------------------------------------------------------
# Dashboard: upcoming installments within N days
# ---------------------------------------------------------------------------

def get_upcoming_installments(installment_records, reference_date,
                               window_days=UPCOMING_WINDOW_DAYS):
    """Filter installment records to those due within *window_days* from
    *reference_date* that are still unpaid.
    """
    cutoff = reference_date + timedelta(days=window_days)
    results = []
    for rec in installment_records:
        if rec.get("status") == "Paid":
            continue
        due = rec.get("due_date")
        if due is None:
            continue
        if isinstance(due, str):
            due = date.fromisoformat(due)
        if reference_date <= due <= cutoff:
            results.append(rec)
    return results


def get_overdue_installments(installment_records, reference_date):
    """Return all unpaid installments whose due_date is before *reference_date*."""
    results = []
    for rec in installment_records:
        if is_installment_overdue(rec, reference_date):
            results.append(rec)
    return results


# ---------------------------------------------------------------------------
# Multi-director dashboard summary
# ---------------------------------------------------------------------------

def get_directors_with_upcoming_cp500(directors, reference_date,
                                      window_days=UPCOMING_WINDOW_DAYS):
    """Given a list of director dicts (each with 'employee', 'employee_name',
    'cp500_payer', 'installments'), return those with upcoming installments
    within the window.

    Each director dict should have:
        - employee: str (employee ID)
        - employee_name: str
        - cp500_payer: bool
        - installments: list of installment records
    """
    results = []
    for d in directors:
        if not d.get("cp500_payer"):
            continue
        upcoming = get_upcoming_installments(
            d.get("installments", []), reference_date, window_days
        )
        if upcoming:
            results.append({
                "employee": d["employee"],
                "employee_name": d.get("employee_name", ""),
                "upcoming_count": len(upcoming),
                "next_due_date": min(
                    (r["due_date"] for r in upcoming),
                    default=None,
                ),
                "upcoming_installments": upcoming,
            })
    return results


def get_dashboard_summary(directors, reference_date,
                           window_days=UPCOMING_WINDOW_DAYS):
    """High-level dashboard summary for the LHDN Payroll Workspace widget.

    Returns dict with:
        - total_cp500_payers: int
        - directors_with_upcoming: list (from get_directors_with_upcoming_cp500)
        - total_upcoming: int
        - total_overdue: int
        - overdue_directors: list of dicts with employee + overdue details
    """
    cp500_directors = [d for d in directors if d.get("cp500_payer")]

    upcoming_list = get_directors_with_upcoming_cp500(
        directors, reference_date, window_days
    )
    total_upcoming = sum(d["upcoming_count"] for d in upcoming_list)

    overdue_directors = []
    total_overdue = 0
    for d in cp500_directors:
        overdue = get_overdue_installments(
            d.get("installments", []), reference_date
        )
        if overdue:
            total_overdue += len(overdue)
            overdue_directors.append({
                "employee": d["employee"],
                "employee_name": d.get("employee_name", ""),
                "overdue_count": len(overdue),
                "overdue_installments": overdue,
            })

    return {
        "total_cp500_payers": len(cp500_directors),
        "directors_with_upcoming": upcoming_list,
        "total_upcoming": total_upcoming,
        "total_overdue": total_overdue,
        "overdue_directors": overdue_directors,
    }


# ---------------------------------------------------------------------------
# Validate CP500 configuration on employee
# ---------------------------------------------------------------------------

def validate_cp500_config(employee_record):
    """Return a list of validation issues (empty = valid)."""
    issues = []
    if not is_cp500_payer(employee_record):
        return issues  # nothing to validate

    amount = get_annual_installment_amount(employee_record)
    if amount <= 0:
        issues.append("CP500 annual installment amount must be > 0 for a CP500 payer")

    return issues
