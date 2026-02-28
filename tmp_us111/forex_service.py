"""Multi-Currency Salary Conversion Service for Expatriate PCB Base Calculation (US-111).

LHDN PCB Specification: all income reported in RM (Ringgit Malaysia).
Foreign-currency income must be converted at the kadar pertukaran pada tarikh
pembayaran (exchange rate prevailing on the payment date) — typically the
Bank Negara Malaysia (BNM) middle rate.

References:
    - Income Tax Act 1967, Section 13: employment income includes amounts
      received in foreign currency, converted at the prevailing rate.
    - Bank Negara Malaysia exchange rates: https://www.bnm.gov.my/exchange-rates
    - ERPNext built-in Currency Exchange DocType used as the rate store.

Supported currencies (most common for expatriate employment in Malaysia):
    USD, SGD, GBP, AUD, EUR, JPY, CNY, HKD, INR, THB
    MYR is treated as the base currency (exchange rate = 1.0).
"""
import frappe


# Supported foreign currencies for expatriate salary conversion
SUPPORTED_CURRENCIES = {
    "MYR", "USD", "SGD", "GBP", "AUD", "EUR", "JPY", "CNY", "HKD", "INR", "THB"
}

# Default fallback rates (approximate mid-2025 values) used ONLY when no
# ERPNext Currency Exchange record is found AND no manual rate is provided.
# In production, always set rates via ERPNext Currency Exchange doctype.
_FALLBACK_RATES = {
    "MYR": 1.0,
    "USD": 4.70,
    "SGD": 3.50,
    "GBP": 5.90,
    "AUD": 3.10,
    "EUR": 5.20,
    "JPY": 0.031,
    "CNY": 0.65,
    "HKD": 0.60,
    "INR": 0.057,
    "THB": 0.13,
}


def get_exchange_rate(from_currency: str, to_currency: str = "MYR", date=None) -> float:
    """Fetch exchange rate from ERPNext Currency Exchange DocType.

    Looks up the most recent Currency Exchange record on or before ``date``
    for the given currency pair. Falls back to ``_FALLBACK_RATES`` if no
    record is found (with a warning logged).

    Args:
        from_currency: Source currency code (e.g., "USD", "SGD").
        to_currency: Target currency code (default "MYR").
        date: Date string (YYYY-MM-DD) or date object for rate lookup.
              Uses today if not provided.

    Returns:
        float: Exchange rate such that 1 unit of from_currency = N units of to_currency.
               Returns 1.0 if from_currency == to_currency (or both are MYR).
    """
    from_currency = (from_currency or "MYR").strip().upper()
    to_currency = (to_currency or "MYR").strip().upper()

    if from_currency == to_currency:
        return 1.0

    if not date:
        date = frappe.utils.today()

    date_str = str(date)[:10]

    # Try ERPNext Currency Exchange DocType (most recent on or before date)
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

    # Try reverse lookup (e.g., if MYR→USD is stored but USD→MYR is needed)
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
            (to_currency, from_currency, date_str),
        )
        if result and result[0][0]:
            rate = float(result[0][0])
            if rate > 0:
                return round(1.0 / rate, 6)
    except Exception:
        pass

    # Fall back to static table with a warning
    fallback = _FALLBACK_RATES.get(from_currency)
    if fallback:
        frappe.log_error(
            title="Forex Fallback Rate Used",
            message=(
                f"No Currency Exchange record found for {from_currency}→{to_currency} "
                f"on or before {date_str}. Using fallback rate {fallback}. "
                "Please add a Currency Exchange record for accurate PCB computation."
            ),
        )
        return fallback

    raise ValueError(
        f"Exchange rate not found for {from_currency}→{to_currency} on {date_str}. "
        "Add a Currency Exchange record or update forex_service._FALLBACK_RATES."
    )


def convert_to_myr(amount: float, from_currency: str, exchange_rate: float = None, date=None) -> float:
    """Convert a salary amount from a foreign currency to MYR.

    Args:
        amount: Amount in the source currency.
        from_currency: Source currency code (e.g., "USD", "SGD").
        exchange_rate: Manual exchange rate override (1 unit of from_currency → MYR).
                       When provided, skips the Currency Exchange lookup.
        date: Date for Currency Exchange lookup (default: today).

    Returns:
        float: Equivalent amount in MYR, rounded to 2 decimal places.
    """
    from_currency = (from_currency or "MYR").strip().upper()

    if from_currency == "MYR":
        return round(float(amount), 2)

    if exchange_rate is not None and float(exchange_rate) > 0:
        rate = float(exchange_rate)
    else:
        rate = get_exchange_rate(from_currency, "MYR", date=date)

    return round(float(amount) * rate, 2)


def get_myr_gross_for_pcb(salary_slip_doc) -> float:
    """Extract the MYR-equivalent gross pay from a Salary Slip for PCB computation.

    For MYR salary slips: returns gross_pay directly.
    For foreign-currency salary slips: applies the exchange rate from either
        (a) the manual ``custom_exchange_rate_to_myr`` field, or
        (b) the ERPNext Currency Exchange table (using posting_date or end_date).

    Args:
        salary_slip_doc: Frappe document object for Salary Slip.

    Returns:
        float: Monthly gross income in MYR to use for PCB base calculation.
    """
    doc = salary_slip_doc
    currency = (getattr(doc, "custom_salary_currency", None) or "MYR").strip().upper()

    raw_gross = float(getattr(doc, "gross_pay", 0) or 0)

    if currency == "MYR":
        return raw_gross

    # Determine exchange rate: manual field takes precedence
    manual_rate = float(getattr(doc, "custom_exchange_rate_to_myr", 0) or 0)
    rate_date = (
        getattr(doc, "posting_date", None)
        or getattr(doc, "end_date", None)
        or frappe.utils.today()
    )

    if manual_rate > 0:
        rate = manual_rate
    else:
        rate = get_exchange_rate(currency, "MYR", date=rate_date)

    return round(raw_gross * rate, 2)


def calculate_component_myr(component_amount: float, from_currency: str,
                             exchange_rate: float = None, date=None) -> float:
    """Convert a single salary component amount to MYR.

    Used to display MYR equivalents on payslip for employee transparency
    (acceptance criterion: payslip shows both original currency and MYR equivalent).

    Args:
        component_amount: Component amount in original currency.
        from_currency: Source currency of the salary.
        exchange_rate: Manual rate override (optional).
        date: Date for exchange rate lookup (optional).

    Returns:
        float: MYR equivalent of the component, rounded to 2 decimal places.
    """
    return convert_to_myr(component_amount, from_currency, exchange_rate=exchange_rate, date=date)


@frappe.whitelist()
def fetch_exchange_rate(from_currency: str, date: str = None) -> dict:
    """Whitelisted API: fetch the current MYR exchange rate for a currency.

    Called from Salary Slip form to auto-populate custom_exchange_rate_to_myr
    when the user selects a foreign salary currency.

    Args:
        from_currency: Source currency code (e.g., "USD").
        date: Date string for rate lookup (default: today).

    Returns:
        dict with keys:
            - from_currency (str): The requested currency.
            - to_currency (str): Always "MYR".
            - exchange_rate (float): Rate found.
            - source (str): "Currency Exchange table" or "fallback".
            - date (str): The date used for lookup.
    """
    from_currency = (from_currency or "MYR").strip().upper()
    date_str = date or frappe.utils.today()

    if from_currency == "MYR":
        return {
            "from_currency": "MYR",
            "to_currency": "MYR",
            "exchange_rate": 1.0,
            "source": "base_currency",
            "date": date_str,
        }

    # Try to find in Currency Exchange table
    try:
        result = frappe.db.sql(
            """
            SELECT exchange_rate
            FROM `tabCurrency Exchange`
            WHERE from_currency = %s
              AND to_currency = 'MYR'
              AND date <= %s
            ORDER BY date DESC
            LIMIT 1
            """,
            (from_currency, date_str),
        )
        if result and result[0][0]:
            rate = float(result[0][0])
            if rate > 0:
                return {
                    "from_currency": from_currency,
                    "to_currency": "MYR",
                    "exchange_rate": rate,
                    "source": "Currency Exchange table",
                    "date": date_str,
                }
    except Exception:
        pass

    # Use fallback
    fallback = _FALLBACK_RATES.get(from_currency, 0)
    return {
        "from_currency": from_currency,
        "to_currency": "MYR",
        "exchange_rate": fallback,
        "source": "fallback",
        "date": date_str,
    }
