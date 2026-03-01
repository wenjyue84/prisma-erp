"""Gig Workers Act 2025 — SKSPS Per-Transaction Contribution Calculation
and PERKESO Monthly Aggregate Remittance (US-182).

Under the Gig Workers Act 2025, platform providers must deduct SKSPS
contributions from each completed gig transaction (ride, delivery, freelance
job) and remit the monthly aggregate to PERKESO.  Unlike standard SOCSO
(monthly salary-based) or SEIA (monthly earnings-based at 2%), SKSPS is
computed per-transaction at 1.25% and the full amount is borne by the
platform provider.

Key rules (Self-Employment Social Security Act 2017 — Act 789,
Gig Workers Act 2025 — Act 872):
  - SKSPS rate: 1.25% per completed gig transaction value.
  - Full amount borne by platform provider (not split with worker).
  - Failed, cancelled, or refunded transactions are EXCLUDED.
  - Monthly aggregate per gig worker is computed and held for PERKESO
    remittance.
  - Remittance due by the 15th of the following month (consistent with
    SOCSO payment cycle).
  - Remittance file includes worker-level breakdown: NRIC/passport,
    SKSPS number, monthly aggregate amount.
"""

import csv
import io
from datetime import date
from calendar import monthrange

import frappe
from frappe.utils import getdate, nowdate, get_first_day, get_last_day


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: SKSPS per-transaction contribution rate (platform provider bears full cost)
SKSPS_CONTRIBUTION_RATE = 0.0125  # 1.25%

#: Transaction statuses that are EXCLUDED from the SKSPS contribution base
EXCLUDED_TRANSACTION_STATUSES = frozenset({
    "Failed",
    "Cancelled",
    "Refunded",
})

#: Transaction statuses that qualify for SKSPS deduction
ELIGIBLE_TRANSACTION_STATUSES = frozenset({
    "Completed",
})

#: Remittance deadline day-of-month (15th of following month)
REMITTANCE_DEADLINE_DAY = 15

#: Employment type for gig/platform workers
GIG_WORKER_EMPLOYMENT_TYPE = "Gig / Platform Worker"

#: Minimum transaction value for SKSPS to apply (RM 0 — any positive value)
MIN_TRANSACTION_VALUE = 0.00

#: PERKESO remittance CSV columns
REMITTANCE_CSV_COLUMNS = [
    "NRIC/Passport",
    "Employee Name",
    "SKSPS Reference No",
    "Total Transactions",
    "Total Transaction Value (RM)",
    "SKSPS Contribution (RM)",
]


# ---------------------------------------------------------------------------
# Per-transaction SKSPS computation
# ---------------------------------------------------------------------------

def compute_transaction_sksps(transaction_value: float) -> dict:
    """Compute the SKSPS contribution for a single gig transaction.

    Args:
        transaction_value: Gross value of the completed gig transaction (RM).

    Returns:
        dict with keys:
            ``sksps_amount``       — SKSPS contribution (RM, rounded to 2 dp)
            ``transaction_value``  — Original transaction value
            ``rate``               — Applied rate (0.0125)
            ``eligible``           — True if transaction value is positive
    """
    value = float(transaction_value)
    if value <= MIN_TRANSACTION_VALUE:
        return {
            "sksps_amount": 0.00,
            "transaction_value": round(value, 2),
            "rate": SKSPS_CONTRIBUTION_RATE,
            "eligible": False,
        }

    sksps = round(value * SKSPS_CONTRIBUTION_RATE, 2)
    return {
        "sksps_amount": sksps,
        "transaction_value": round(value, 2),
        "rate": SKSPS_CONTRIBUTION_RATE,
        "eligible": True,
    }


def is_transaction_eligible(transaction_status: str) -> bool:
    """Check if a transaction qualifies for SKSPS contribution.

    Only 'Completed' transactions are eligible.  Failed, Cancelled, and
    Refunded transactions are excluded from the SKSPS contribution base.

    Args:
        transaction_status: Status string of the gig transaction.

    Returns:
        True if the transaction is eligible for SKSPS deduction.
    """
    status = (transaction_status or "").strip()
    if status in EXCLUDED_TRANSACTION_STATUSES:
        return False
    if status in ELIGIBLE_TRANSACTION_STATUSES:
        return True
    # Unknown status — treat as ineligible
    return False


# ---------------------------------------------------------------------------
# Monthly aggregation
# ---------------------------------------------------------------------------

def aggregate_monthly_sksps(transactions: list) -> dict:
    """Aggregate per-transaction SKSPS into a monthly total for one gig worker.

    Filters out ineligible transactions (failed/cancelled/refunded) and
    computes the 1.25% contribution on each eligible transaction, then sums.

    Args:
        transactions: List of dicts, each with at least:
            ``value``  — transaction amount (RM)
            ``status`` — transaction status string

    Returns:
        dict with keys:
            ``total_sksps``            — Monthly aggregate SKSPS amount (RM)
            ``total_transaction_value``— Sum of eligible transaction values
            ``eligible_count``         — Number of eligible transactions
            ``excluded_count``         — Number of excluded transactions
            ``transactions``           — Per-transaction breakdown (list of dicts)
    """
    total_sksps = 0.00
    total_value = 0.00
    eligible_count = 0
    excluded_count = 0
    breakdown = []

    for txn in transactions:
        txn_value = float(txn.get("value", 0))
        txn_status = txn.get("status", "")

        if not is_transaction_eligible(txn_status):
            excluded_count += 1
            breakdown.append({
                "value": round(txn_value, 2),
                "status": txn_status,
                "eligible": False,
                "sksps_amount": 0.00,
            })
            continue

        result = compute_transaction_sksps(txn_value)
        eligible_count += 1
        total_sksps += result["sksps_amount"]
        total_value += result["transaction_value"]
        breakdown.append({
            "value": round(txn_value, 2),
            "status": txn_status,
            "eligible": True,
            "sksps_amount": result["sksps_amount"],
        })

    return {
        "total_sksps": round(total_sksps, 2),
        "total_transaction_value": round(total_value, 2),
        "eligible_count": eligible_count,
        "excluded_count": excluded_count,
        "transactions": breakdown,
    }


# ---------------------------------------------------------------------------
# Remittance deadline
# ---------------------------------------------------------------------------

def get_remittance_deadline(year: int, month: int) -> date:
    """Return the PERKESO SKSPS remittance deadline for a payroll period.

    Remittance is due by the 15th of the month following the payroll period.
    E.g. for January 2026 payroll → deadline is 15 February 2026.

    Args:
        year:  Payroll year.
        month: Payroll month (1–12).

    Returns:
        datetime.date of the remittance deadline.
    """
    # Move to following month
    if month == 12:
        deadline_year = year + 1
        deadline_month = 1
    else:
        deadline_year = year
        deadline_month = month + 1

    return date(deadline_year, deadline_month, REMITTANCE_DEADLINE_DAY)


def is_remittance_overdue(year: int, month: int, as_of_date=None) -> dict:
    """Check if the PERKESO SKSPS remittance for a period is overdue.

    Args:
        year:  Payroll year.
        month: Payroll month (1–12).
        as_of_date: Date to check against; defaults to today.

    Returns:
        dict with keys:
            ``overdue``  — True if past the deadline
            ``deadline`` — The deadline date
            ``days_overdue`` — Number of days past deadline (0 if not overdue)
    """
    deadline = get_remittance_deadline(year, month)
    check = getdate(as_of_date or nowdate())

    if check > deadline:
        days = (check - deadline).days
        return {"overdue": True, "deadline": deadline, "days_overdue": days}

    return {"overdue": False, "deadline": deadline, "days_overdue": 0}


# ---------------------------------------------------------------------------
# Worker transaction summary (for payslip display)
# ---------------------------------------------------------------------------

def get_worker_transaction_summary(
    employee_name: str, year: int, month: int
) -> dict:
    """Get the SKSPS transaction summary for a gig worker for a payroll month.

    Reads from the ``Gig Transaction`` child table (if available on the
    Salary Slip or a custom DocType) or falls back to aggregated custom
    fields on the Salary Slip.

    For now, this reads custom fields on the Salary Slip:
      - ``custom_sksps_total_transactions``
      - ``custom_sksps_eligible_transactions``
      - ``custom_sksps_total_value``
      - ``custom_sksps_contribution``

    Args:
        employee_name: Employee name/ID.
        year:  Payroll year.
        month: Payroll month (1–12).

    Returns:
        dict with SKSPS summary fields, or empty dict if no data.
    """
    period_start = get_first_day(f"{year}-{month:02d}-01")
    period_end = get_last_day(f"{year}-{month:02d}-01")

    try:
        slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee_name,
                "docstatus": 1,
                "start_date": [">=", str(period_start)],
                "end_date": ["<=", str(period_end)],
            },
            fields=[
                "name",
                "custom_sksps_total_transactions",
                "custom_sksps_eligible_transactions",
                "custom_sksps_total_value",
                "custom_sksps_contribution",
            ],
            limit_page_length=1,
        )
    except Exception:
        return {}

    if not slips:
        return {}

    slip = slips[0]
    return {
        "salary_slip": slip.get("name", ""),
        "total_transactions": slip.get("custom_sksps_total_transactions") or 0,
        "eligible_transactions": slip.get("custom_sksps_eligible_transactions") or 0,
        "total_value": float(slip.get("custom_sksps_total_value") or 0),
        "sksps_contribution": float(slip.get("custom_sksps_contribution") or 0),
    }


# ---------------------------------------------------------------------------
# PERKESO monthly remittance file generation
# ---------------------------------------------------------------------------

def generate_perkeso_remittance_file(company: str, year: int, month: int) -> str:
    """Generate the monthly PERKESO SKSPS remittance CSV file.

    Each row contains a gig worker's monthly aggregate SKSPS contribution
    with worker-level breakdown (NRIC/passport, SKSPS number, amount).

    Args:
        company: Company name to filter Salary Slips.
        year:    Payroll year.
        month:   Payroll month (1–12).

    Returns:
        CSV string ready for upload to PERKESO ASSIST portal.
    """
    period_start = get_first_day(f"{year}-{month:02d}-01")
    period_end = get_last_day(f"{year}-{month:02d}-01")

    slips = frappe.db.sql(
        """
        SELECT
            ss.employee,
            ss.employee_name,
            e.custom_icpassport_number,
            e.custom_sksps_reference_number,
            ss.custom_sksps_total_transactions,
            ss.custom_sksps_eligible_transactions,
            ss.custom_sksps_total_value,
            ss.custom_sksps_contribution
        FROM `tabSalary Slip` ss
        INNER JOIN `tabEmployee` e ON e.name = ss.employee
        WHERE ss.company = %(company)s
          AND ss.docstatus = 1
          AND ss.start_date >= %(start)s
          AND ss.end_date <= %(end)s
          AND e.custom_employment_type = %(emp_type)s
          AND e.custom_is_seia_worker = 1
          AND IFNULL(ss.custom_sksps_contribution, 0) > 0
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
    writer.writerow(REMITTANCE_CSV_COLUMNS)

    total_sksps = 0.00
    total_workers = 0

    for row in slips:
        sksps_amount = float(row.get("custom_sksps_contribution") or 0)
        total_value = float(row.get("custom_sksps_total_value") or 0)
        txn_count = int(row.get("custom_sksps_eligible_transactions") or 0)
        total_sksps += sksps_amount
        total_workers += 1

        writer.writerow([
            row.get("custom_icpassport_number") or "",
            row.get("employee_name") or "",
            row.get("custom_sksps_reference_number") or "",
            txn_count,
            f"{total_value:.2f}",
            f"{sksps_amount:.2f}",
        ])

    # Footer
    writer.writerow([])
    writer.writerow([
        "TOTAL",
        f"{total_workers} workers",
        "",
        "",
        "",
        f"{total_sksps:.2f}",
    ])

    # Metadata row
    writer.writerow([])
    writer.writerow([
        f"Company: {company}",
        f"Period: {year}-{month:02d}",
        f"Deadline: {get_remittance_deadline(year, month).isoformat()}",
        "",
        "",
        "",
    ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Batch compute SKSPS for all gig workers in a period
# ---------------------------------------------------------------------------

def batch_compute_sksps_for_period(
    company: str, year: int, month: int, transactions_by_employee: dict
) -> dict:
    """Compute and record SKSPS contributions for all gig workers in a period.

    Takes a dict mapping employee names to their list of transactions for
    the month, computes per-transaction SKSPS, and returns aggregated results.

    Args:
        company: Company name.
        year:  Payroll year.
        month: Payroll month (1–12).
        transactions_by_employee: Dict mapping employee name → list of
            transaction dicts, each with ``value`` and ``status``.

    Returns:
        dict with keys:
            ``total_sksps``    — Grand total SKSPS for all workers
            ``total_workers``  — Number of workers processed
            ``deadline``       — Remittance deadline date
            ``workers``        — Per-worker summary list
    """
    deadline = get_remittance_deadline(year, month)
    total_sksps = 0.00
    workers = []

    for employee_name, txns in transactions_by_employee.items():
        agg = aggregate_monthly_sksps(txns)
        total_sksps += agg["total_sksps"]
        workers.append({
            "employee": employee_name,
            "total_sksps": agg["total_sksps"],
            "total_transaction_value": agg["total_transaction_value"],
            "eligible_count": agg["eligible_count"],
            "excluded_count": agg["excluded_count"],
        })

    return {
        "total_sksps": round(total_sksps, 2),
        "total_workers": len(workers),
        "deadline": deadline,
        "workers": workers,
    }
