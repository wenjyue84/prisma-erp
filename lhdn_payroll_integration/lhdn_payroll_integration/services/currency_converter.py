"""Multi-Currency Salary Conversion Service (US-111).

LHDN PCB Specification: all employment income is reported in RM (Ringgit Malaysia).
Foreign-currency income must be converted at the kadar pertukaran pada tarikh pembayaran
(exchange rate prevailing on the payment date) — Bank Negara Malaysia middle rate.

References:
    - Income Tax Act 1967, Section 13: employment income includes amounts received in
      foreign currency, converted at the prevailing rate.
    - Bank Negara Malaysia exchange rates: https://www.bnm.gov.my/exchange-rates
    - ERPNext built-in Currency Exchange DocType is used as the rate store.

Functions:
    get_exchange_rate(from_currency, to_currency, date) → float
    get_gross_myr_for_slip(salary_slip_doc) → float
    apply_myr_conversion(salary_slip_doc) → None  (validate hook)
"""

import frappe


def get_exchange_rate(from_currency: str, to_currency: str = "MYR", date=None) -> float:
    """Fetch the exchange rate from ERPNext Currency Exchange DocType.

    Looks up the most recent Currency Exchange record on or before ``date``
    for the given currency pair. Returns 1.0 when:
      - from_currency == to_currency (or either is None/empty → treated as MYR)
      - No record found in the table
      - A database exception occurs

    Args:
        from_currency: Source currency code (e.g., "USD", "SGD"). None treated as "MYR".
        to_currency: Target currency code (default "MYR").
        date: Date string (YYYY-MM-DD) or date object for rate lookup.
              Uses today if not provided.

    Returns:
        float: Exchange rate such that 1 unit of from_currency = N units of to_currency.
               Returns 1.0 for same-currency pairs or when no record is found.
    """
    from_currency = (from_currency or "MYR").strip().upper()
    to_currency = (to_currency or "MYR").strip().upper()

    if from_currency == to_currency or from_currency == "MYR":
        return 1.0

    if not date:
        date = frappe.utils.today()

    date_str = str(date)[:10]

    try:
        result = frappe.db.sql(
            """
            SELECT exchange_rate
            FROM `tabCurrency Exchange`
            WHERE from_currency = %s
              AND to_currency = %s
              AND date <= %s
            ORDER BY date DESC
            LIMIT 1
            """,
            (from_currency, to_currency, date_str),
        )
        if result and result[0][0]:
            rate = float(result[0][0])
            if rate > 0:
                return rate
    except Exception:
        pass

    # No record found or DB error → fall back to 1.0
    return 1.0


def get_gross_myr_for_slip(salary_slip_doc) -> float:
    """Compute the MYR-equivalent gross pay from a Salary Slip document.

    For MYR salary slips: returns gross_pay directly.
    For foreign-currency salary slips: applies custom_exchange_rate_to_myr
    (or fetches from Currency Exchange table if the rate field is 0/unset).

    Args:
        salary_slip_doc: Frappe document object (or mock) for a Salary Slip.

    Returns:
        float: Monthly gross income in MYR for use as PCB base.
    """
    doc = salary_slip_doc
    currency = (getattr(doc, "custom_salary_currency", None) or "MYR").strip().upper()
    raw_gross = float(getattr(doc, "gross_pay", 0) or 0)

    if currency == "MYR":
        return raw_gross

    # Use the manually set exchange rate if available
    manual_rate = float(getattr(doc, "custom_exchange_rate_to_myr", 0) or 0)
    if manual_rate > 0:
        return round(raw_gross * manual_rate, 2)

    # Auto-fetch from Currency Exchange table
    rate_date = (
        getattr(doc, "posting_date", None)
        or getattr(doc, "start_date", None)
        or frappe.utils.today()
    )
    rate = get_exchange_rate(currency, "MYR", date=rate_date)
    return round(raw_gross * rate, 2)


def apply_myr_conversion(salary_slip_doc, method=None) -> None:
    """Validate hook: compute and set MYR-equivalent fields on a Salary Slip.

    Sets:
        custom_exchange_rate_to_myr: The effective exchange rate used (float).
        custom_gross_myr: gross_pay * exchange_rate in MYR (float).

    For MYR salary slips, both fields are set to their identity values
    (exchange_rate = 1.0, gross_myr = gross_pay).
    For foreign-currency slips, the rate is sourced from:
        1. custom_exchange_rate_to_myr (if already set manually)
        2. Currency Exchange table (auto-lookup)
        3. 1.0 (safe fallback when no record found)

    Called by hooks.py doc_events["Salary Slip"]["validate"] (US-111).

    Args:
        salary_slip_doc: The Salary Slip document being validated.
        method: Frappe event method string (unused, required by hook signature).
    """
    doc = salary_slip_doc
    currency = None
    try:
        currency = (doc.custom_salary_currency or "MYR").strip().upper()
    except AttributeError:
        currency = "MYR"

    raw_gross = float(getattr(doc, "gross_pay", 0) or 0)

    if currency == "MYR":
        doc.custom_exchange_rate_to_myr = 1.0
        doc.custom_gross_myr = raw_gross
        return

    # Determine the effective exchange rate
    manual_rate = float(getattr(doc, "custom_exchange_rate_to_myr", 0) or 0)
    if manual_rate > 0:
        effective_rate = manual_rate
    else:
        rate_date = (
            getattr(doc, "posting_date", None)
            or getattr(doc, "start_date", None)
            or frappe.utils.today()
        )
        effective_rate = get_exchange_rate(currency, "MYR", rate_date)

    # Ensure rate is at least 1.0 when no value found (safe fallback)
    if not effective_rate or effective_rate <= 0:
        effective_rate = 1.0

    doc.custom_exchange_rate_to_myr = effective_rate
    doc.custom_gross_myr = round(raw_gross * effective_rate, 2)
