"""Multi-Currency Salary Conversion Service (US-111).

LHDN PCB Specification: All income reported in RM.
Foreign-currency income is converted at the exchange rate on the date of payment
(kadar pertukaran pada tarikh pembayaran) per Bank Negara Malaysia middle rate.

Income Tax Act 1967, Section 13: employment income includes amounts received
in foreign currency — converted to MYR for PCB and EA Form reporting.
"""

import frappe


def get_exchange_rate(from_currency: str, to_currency: str = "MYR", date=None) -> float:
	"""Fetch exchange rate from ERPNext Currency Exchange DocType.

	Looks up the most recent Currency Exchange record for the given pair
	on or before ``date``. Falls back to 1.0 if the pair is not found
	(e.g. MYR→MYR) or if no record exists.

	Args:
		from_currency: ISO 4217 source currency code (e.g. "USD", "SGD").
		to_currency: ISO 4217 target currency code (default "MYR").
		date: Date of payment (str "YYYY-MM-DD" or date object). Uses today if None.

	Returns:
		float: Exchange rate (1 from_currency = X to_currency). 1.0 if not found.
	"""
	if not from_currency or from_currency == to_currency:
		return 1.0

	if date is None:
		date = frappe.utils.nowdate()
	elif hasattr(date, "isoformat"):
		date = date.isoformat()
	else:
		date = str(date)[:10]

	try:
		result = frappe.db.sql(
			"""
			SELECT exchange_rate
			FROM `tabCurrency Exchange`
			WHERE from_currency = %s
			  AND to_currency   = %s
			  AND date          <= %s
			ORDER BY date DESC
			LIMIT 1
			""",
			(from_currency, to_currency, date),
		)
		if result:
			return float(result[0][0])
	except Exception:
		pass

	return 1.0


def get_gross_myr_for_slip(doc) -> float:
	"""Return gross pay in MYR for a Salary Slip document.

	If the slip's salary currency is MYR (or unset), returns ``gross_pay``
	unchanged. For non-MYR slips, multiplies ``gross_pay`` by
	``custom_exchange_rate_to_myr``.

	Args:
		doc: Salary Slip Frappe document (or dict with the required fields).

	Returns:
		float: Gross pay expressed in MYR.
	"""
	currency = getattr(doc, "custom_salary_currency", None) or "MYR"
	gross = float(getattr(doc, "gross_pay", 0) or 0)

	if currency == "MYR":
		return gross

	exchange_rate = float(getattr(doc, "custom_exchange_rate_to_myr", 1.0) or 1.0)
	return round(gross * exchange_rate, 2)


def apply_myr_conversion(doc, method=None):
	"""Salary Slip validate hook: compute and persist custom_gross_myr.

	When ``custom_salary_currency`` is set to a non-MYR currency, this hook:
	  1. Auto-fetches the exchange rate from Currency Exchange if the user has
	     not manually set ``custom_exchange_rate_to_myr`` (or left it at 0/1.0
	     without changing the currency).
	  2. Calculates ``custom_gross_myr = gross_pay * exchange_rate``.

	For MYR slips, ``custom_gross_myr`` mirrors ``gross_pay`` exactly.

	Args:
		doc: Salary Slip document being validated.
		method: Frappe doc event method name (not used).
	"""
	currency = getattr(doc, "custom_salary_currency", None) or "MYR"

	if currency == "MYR":
		# For MYR slips: ensure exchange rate = 1.0 and gross_myr mirrors gross_pay
		doc.custom_exchange_rate_to_myr = 1.0
		doc.custom_gross_myr = float(doc.gross_pay or 0)
		return

	# Non-MYR slip — use manually entered rate or fetch from Currency Exchange
	manual_rate = float(getattr(doc, "custom_exchange_rate_to_myr", 0) or 0)
	if manual_rate <= 0 or manual_rate == 1.0:
		# Try to auto-fetch from Currency Exchange table
		slip_date = getattr(doc, "posting_date", None) or getattr(doc, "start_date", None)
		fetched = get_exchange_rate(currency, "MYR", slip_date)
		if fetched > 0:
			doc.custom_exchange_rate_to_myr = fetched
			manual_rate = fetched

	if manual_rate <= 0:
		manual_rate = 1.0
		doc.custom_exchange_rate_to_myr = 1.0

	gross = float(doc.gross_pay or 0)
	doc.custom_gross_myr = round(gross * manual_rate, 2)
