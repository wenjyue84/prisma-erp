"""Section 107D ITA 1967 — WHT 2% Deduction and Monthly Remittance Service.

Section 107D of the Income Tax Act 1967 requires payers to deduct 2% withholding
tax (WHT) at source from monetary and non-monetary incentive payments to agents,
dealers, or distributors exceeding RM5,000 per year. The WHT must be remitted to
LHDN by the 15th of the following month.

Annual reporting: WHT amounts are reported on the CP58 statement issued to the
agent/dealer by 31 March of the following year (Section 83A ITA 1967).

Key rules:
  - WHT rate: 2% on amount exceeding RM5,000 annual threshold per recipient
  - Threshold: RM5,000 cumulative per calendar year per payee
  - Remittance deadline: 15th of the following month
  - Late payment penalty: 10% per annum
  - Non-monetary incentives: valued at cost incurred by payer

US-179: WHT 2% Deduction, Monthly Remittance, and CP58 Integration for
        Agent/Dealer Payments.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe.utils import flt

# WHT rate under Section 107D ITA 1967
WHT_RATE = Decimal("0.02")  # 2%

# Annual de-minimis threshold per recipient per payer company
WHT_ANNUAL_THRESHOLD = Decimal("5000.00")  # RM 5,000

# Legacy alias
WHT_THRESHOLD = WHT_ANNUAL_THRESHOLD

# Remittance deadline: 15th day of the following calendar month
REMITTANCE_DAY = 15

# Late payment penalty rate per annum
LATE_PENALTY_RATE = Decimal("0.10")  # 10%

# Payee classification types subject to WHT under Section 107D
APPLICABLE_RECIPIENT_TYPES = {"Agent", "Dealer", "Distributor"}

# Legacy alias
SUBJECT_PAYEE_TYPES = APPLICABLE_RECIPIENT_TYPES

# Valid payment types
_VALID_PAYMENT_TYPES = {"monetary", "non_monetary"}


# ---------------------------------------------------------------------------
# Core computation functions
# ---------------------------------------------------------------------------


def compute_wht_amount(taxable_amount: Decimal) -> Decimal:
    """Compute 2% WHT on a taxable amount, rounded to 2 dp (ROUND_HALF_UP).

    Args:
        taxable_amount: The amount on which WHT is calculated.

    Returns:
        Decimal WHT amount rounded to nearest sen.
    """
    return (taxable_amount * WHT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def is_wht_threshold_exceeded(annual_total: Decimal) -> bool:
    """Return True when annual_total strictly exceeds RM5,000 threshold.

    The threshold is strict: total must be > RM5,000 (not >= RM5,000).

    Args:
        annual_total: Year-to-date cumulative payments to this recipient.

    Returns:
        True if threshold is exceeded, False otherwise.
    """
    return annual_total > WHT_ANNUAL_THRESHOLD


def compute_wht_for_payment(
    annual_total_before: Decimal,
    payment_amount: Decimal,
    recipient_type: str,
) -> dict:
    """Compute WHT for a single payment given prior year-to-date cumulative.

    Business rules (Section 107D):
      - No WHT if recipient_type not in APPLICABLE_RECIPIENT_TYPES
      - No WHT if (annual_total_before + payment_amount) <= RM5,000
      - WHT on the excess portion when threshold is first crossed
      - WHT on FULL payment if prior cumulative already > RM5,000

    Args:
        annual_total_before: Cumulative paid to this payee before this payment
                             in the current calendar year.
        payment_amount:      Amount of this payment.
        recipient_type:      Classification (Agent / Dealer / Distributor / ...).

    Returns:
        dict:
            wht_applicable (bool):     True if WHT applies.
            wht_amount (Decimal):      WHT amount to deduct.
            new_annual_total (Decimal): Updated year-to-date cumulative.
            wht_rate (Decimal):        WHT rate applied.
    """
    annual_total_before = Decimal(str(annual_total_before))
    payment_amount = Decimal(str(payment_amount))

    new_annual_total = annual_total_before + payment_amount

    # Non-applicable recipient types — no WHT
    if recipient_type not in APPLICABLE_RECIPIENT_TYPES:
        return {
            "wht_applicable": False,
            "wht_amount": Decimal("0.00"),
            "new_annual_total": new_annual_total,
            "wht_rate": WHT_RATE,
        }

    # Determine taxable portion
    if new_annual_total <= WHT_ANNUAL_THRESHOLD:
        # Still under threshold — no WHT
        taxable = Decimal("0.00")
        wht_applicable = False
    elif annual_total_before >= WHT_ANNUAL_THRESHOLD:
        # Already over threshold — full payment is taxable
        taxable = payment_amount
        wht_applicable = True
    else:
        # This payment crosses the threshold — only excess portion is taxable
        taxable = new_annual_total - WHT_ANNUAL_THRESHOLD
        wht_applicable = True

    wht_amount = compute_wht_amount(taxable) if wht_applicable else Decimal("0.00")

    return {
        "wht_applicable": wht_applicable,
        "wht_amount": wht_amount,
        "new_annual_total": new_annual_total,
        "wht_rate": WHT_RATE,
    }


def compute_payment_type_value(amount: float, payment_type: str) -> Decimal:
    """Convert a raw amount to Decimal, validating the payment_type.

    Args:
        amount:       Raw payment or cost amount.
        payment_type: 'monetary' or 'non_monetary'.

    Returns:
        Decimal representation of the amount.

    Raises:
        ValueError: If payment_type is not 'monetary' or 'non_monetary'.
    """
    if payment_type not in _VALID_PAYMENT_TYPES:
        raise ValueError(
            f"Invalid payment_type '{payment_type}'. "
            f"Must be one of: {sorted(_VALID_PAYMENT_TYPES)}"
        )
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_late_penalty(wht_amount: Decimal) -> Decimal:
    """Compute 10% late payment penalty on outstanding WHT amount.

    Args:
        wht_amount: The outstanding WHT amount that was remitted late.

    Returns:
        Decimal penalty amount, rounded to 2 dp.
    """
    return (wht_amount * LATE_PENALTY_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def accumulate_annual_payments(payments: list) -> Decimal:
    """Sum the 'amount' field across a list of payment records.

    Args:
        payments: List of dicts, each with an 'amount' key.

    Returns:
        Decimal total.
    """
    return sum(
        (Decimal(str(p["amount"])) for p in payments),
        Decimal("0.00"),
    )


# ---------------------------------------------------------------------------
# Deadline helpers
# ---------------------------------------------------------------------------


def get_remittance_deadline(year: int, month: int) -> date:
    """Return the WHT remittance deadline: 15th of the month following deduction.

    Args:
        year:  Calendar year of the WHT deduction month.
        month: Calendar month (1–12) of the WHT deduction.

    Returns:
        date object for the 15th of the following month.
    """
    if month == 12:
        return date(year + 1, 1, REMITTANCE_DAY)
    return date(year, month + 1, REMITTANCE_DAY)


def get_cp58_issuance_deadline(assessment_year: int) -> date:
    """Return the CP58 issuance deadline: 31 March of the year following assessment year.

    Args:
        assessment_year: The year for which CP58 is being issued.

    Returns:
        date(assessment_year + 1, 3, 31).
    """
    return date(assessment_year + 1, 3, 31)


# ---------------------------------------------------------------------------
# Schedule and summary builders
# ---------------------------------------------------------------------------


def generate_monthly_remittance_schedule(
    records: list,
    company: str,
    year: int,
    month: int,
) -> dict:
    """Build a monthly WHT remittance schedule for a company.

    Args:
        records:  List of recipient WHT dicts, each with 'recipient_name',
                  'recipient_tin', and 'wht_amount' (Decimal).
        company:  Company name.
        year:     Year of the WHT deduction month.
        month:    Month (1–12) of WHT deduction.

    Returns:
        dict with keys: company, year, month, remittance_deadline,
        total_wht_payable, recipient_breakdown.
    """
    total_wht_payable = sum(
        (Decimal(str(r["wht_amount"])) for r in records),
        Decimal("0.00"),
    )
    return {
        "company": company,
        "year": year,
        "month": month,
        "remittance_deadline": get_remittance_deadline(year, month),
        "total_wht_payable": total_wht_payable,
        "recipient_breakdown": list(records),
    }


def build_cp58_wht_summary(recipient_id: str, year: int, records: list) -> dict:
    """Build CP58 WHT summary for a single recipient.

    Args:
        recipient_id: TIN or unique identifier of the recipient.
        year:         Assessment year.
        records:      List of dicts, each with 'wht_amount' (Decimal).

    Returns:
        dict with keys: recipient_id, year, total_wht, record_count,
        cp58_issuance_deadline.
    """
    total_wht = sum(
        (Decimal(str(r["wht_amount"])) for r in records),
        Decimal("0.00"),
    )
    return {
        "recipient_id": recipient_id,
        "year": year,
        "total_wht": total_wht,
        "record_count": len(records),
        "cp58_issuance_deadline": get_cp58_issuance_deadline(year),
    }


# ---------------------------------------------------------------------------
# Legacy / database-backed functions (kept for backward compatibility)
# ---------------------------------------------------------------------------


def calculate_wht_for_payment(prior_cumulative, payment_amount):
    """Legacy function — delegates to compute_wht_for_payment.

    Accepts float/int args (converts internally). Returns legacy dict keys.
    """
    result = compute_wht_for_payment(
        Decimal(str(prior_cumulative)),
        Decimal(str(payment_amount)),
        "Agent",  # legacy caller assumed applicable
    )
    return {
        "wht_base": (
            result["new_annual_total"] - Decimal(str(prior_cumulative))
            if result["wht_applicable"]
            else Decimal("0.00")
        ),
        "wht_amount": result["wht_amount"],
        "net_payment": Decimal(str(payment_amount)) - result["wht_amount"],
        "threshold_crossed": result["wht_applicable"],
        "wht_rate": float(WHT_RATE),
    }


def get_non_monetary_wht_base(cost_to_payer):
    """Return Decimal representation of non-monetary incentive cost.

    Args:
        cost_to_payer: Cost incurred by the payer for the non-monetary incentive.

    Returns:
        Decimal value.
    """
    return Decimal(str(cost_to_payer)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_annual_cumulative_paid(company, payee_name, year):
    """Query database for year-to-date cumulative payments to a payee.

    Args:
        company:     Company name (Frappe docname).
        payee_name:  Payee name.
        year:        Calendar year.

    Returns:
        Decimal cumulative total.
    """
    try:
        result = frappe.db.sql(
            """SELECT COALESCE(SUM(payment_amount), 0) as total
               FROM `tabWHT 107D Payment`
               WHERE company = %s AND payee_name = %s
                 AND YEAR(payment_date) = %s""",
            (company, payee_name, year),
            as_dict=True,
        )
        return Decimal(str(result[0]["total"])) if result else Decimal("0.00")
    except Exception:
        return Decimal("0.00")


def get_monthly_wht_by_company(company, year, month):
    """Retrieve all WHT records for a company in a specific month.

    Args:
        company: Company name.
        year:    Year.
        month:   Month (1–12).

    Returns:
        List of dicts with payee details and WHT amounts.
    """
    try:
        return frappe.db.sql(
            """SELECT payee_name, payee_type, payment_amount, wht_amount, payment_date
               FROM `tabWHT 107D Payment`
               WHERE company = %s
                 AND YEAR(payment_date) = %s
                 AND MONTH(payment_date) = %s
               ORDER BY payment_date""",
            (company, year, month),
            as_dict=True,
        )
    except Exception:
        return []


def generate_annual_remittance_schedule(company, year):
    """Generate a full-year remittance schedule with monthly deadlines.

    Args:
        company: Company name.
        year:    Calendar year.

    Returns:
        List of monthly schedule dicts.
    """
    schedule = []
    for month in range(1, 13):
        records = get_monthly_wht_by_company(company, year, month)
        schedule.append(
            generate_monthly_remittance_schedule(records, company, year, month)
        )
    return schedule


def get_wht_summary_for_cp58(company, year):
    """Aggregate WHT data per payee for CP58 annual statements.

    Args:
        company: Company name.
        year:    Assessment year.

    Returns:
        List of per-payee CP58 summary dicts.
    """
    try:
        payees = frappe.db.sql(
            """SELECT DISTINCT payee_name, payee_tin
               FROM `tabWHT 107D Payment`
               WHERE company = %s AND YEAR(payment_date) = %s""",
            (company, year),
            as_dict=True,
        )
        summaries = []
        for payee in payees:
            records = frappe.db.sql(
                """SELECT wht_amount FROM `tabWHT 107D Payment`
                   WHERE company = %s AND payee_name = %s AND YEAR(payment_date) = %s""",
                (company, payee["payee_name"], year),
                as_dict=True,
            )
            wht_records = [{"wht_amount": Decimal(str(r["wht_amount"]))} for r in records]
            summaries.append(
                build_cp58_wht_summary(
                    payee.get("payee_tin", payee["payee_name"]), year, wht_records
                )
            )
        return summaries
    except Exception:
        return []


def store_remittance_reference(remittance_record, lhdn_reference):
    """Store LHDN payment reference on a remittance record.

    Args:
        remittance_record: Dict with at least 'name' key (Frappe docname).
        lhdn_reference:    LHDN payment reference string.
    """
    try:
        frappe.db.set_value(
            "WHT 107D Remittance",
            remittance_record.get("name"),
            "lhdn_reference",
            lhdn_reference,
        )
    except Exception:
        pass
