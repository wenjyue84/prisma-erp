"""Self-Billed Credit Note (type 12) builder for LHDN MyInvois.

Generates UBL 2.1 Credit Note XML that references the original self-billed
invoice. Used when an e-Invoice needs to be amended after the 72-hour
cancellation window has expired.

LHDN type code 12 = Self-Billed Credit Note.
"""
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP

import frappe

# UBL 2.1 Namespaces (same as payload_builder)
UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

TWO_DP = Decimal("0.01")


def _quantize(value):
	"""Quantize a value to 2 decimal places with ROUND_HALF_UP."""
	return Decimal(str(value)).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def _sub(parent, ns, tag, text=None, **attribs):
	"""Create a sub-element with namespace prefix."""
	elem = ET.SubElement(parent, f"{{{ns}}}{tag}", **attribs)
	if text is not None:
		elem.text = str(text)
	return elem


def build_credit_note_xml(original_docname, reason=None):
	"""Build UBL 2.1 Self-Billed Credit Note XML (type 12).

	References the original invoice via BillingReference with UUID and docname.
	All amounts are reversed (negative) to credit the original invoice.

	Args:
		original_docname: The original Salary Slip document name.
		reason: Optional reason for credit note issuance.

	Returns:
		str: UBL 2.1 XML string.

	Raises:
		frappe.ValidationError: If original document has no LHDN UUID.
	"""
	doc = frappe.get_doc("Salary Slip", original_docname)

	if not doc.custom_lhdn_uuid:
		frappe.throw(
			f"Cannot issue credit note: {original_docname} has no LHDN UUID. "
			"The original invoice must be submitted to LHDN first.",
			frappe.ValidationError,
		)

	company = frappe.get_cached_doc("Company", doc.company)

	# Register namespaces
	ET.register_namespace("", UBL_NS)
	ET.register_namespace("cac", CAC_NS)
	ET.register_namespace("cbc", CBC_NS)

	root = ET.Element(f"{{{UBL_NS}}}Invoice")

	# Credit note ID references original docname
	_sub(root, CBC_NS, "ID", f"CN-{original_docname}")
	_sub(root, CBC_NS, "IssueDate", str(doc.posting_date))

	# InvoiceTypeCode = 12 (Self-Billed Credit Note)
	version = frappe.conf.get("lhdn_einvoice_version", "1.1")
	type_code = _sub(root, CBC_NS, "InvoiceTypeCode", "12")
	type_code.set("listVersionID", version)

	_sub(root, CBC_NS, "DocumentCurrencyCode", "MYR")

	# Note with reason
	if reason:
		_sub(root, CBC_NS, "Note", reason)

	# BillingReference — references the original invoice
	billing_ref = _sub(root, CAC_NS, "BillingReference")
	invoice_doc_ref = _sub(billing_ref, CAC_NS, "InvoiceDocumentReference")
	_sub(invoice_doc_ref, CBC_NS, "ID", original_docname)
	_sub(invoice_doc_ref, CBC_NS, "UUID", doc.custom_lhdn_uuid)

	# AccountingSupplierParty (Employee = Payee = Supplier in self-billed)
	supplier_party = _sub(root, CAC_NS, "AccountingSupplierParty")
	supplier_inner = _sub(supplier_party, CAC_NS, "Party")
	supplier_id = _sub(supplier_inner, CAC_NS, "PartyIdentification")
	_sub(supplier_id, CBC_NS, "ID", doc.employee)
	supplier_name = _sub(supplier_inner, CAC_NS, "PartyName")
	_sub(supplier_name, CBC_NS, "Name", doc.employee_name)

	# AccountingCustomerParty (Company = Payer = Buyer in self-billed)
	customer_party = _sub(root, CAC_NS, "AccountingCustomerParty")
	customer_inner = _sub(customer_party, CAC_NS, "Party")
	customer_id = _sub(customer_inner, CAC_NS, "PartyIdentification")
	_sub(customer_id, CBC_NS, "ID", company.custom_company_tin_number)
	customer_name = _sub(customer_inner, CAC_NS, "PartyName")
	_sub(customer_name, CBC_NS, "Name", doc.company)

	# Calculate reversed totals from earnings
	total_excl = Decimal("0.00")
	for earning in doc.earnings:
		total_excl += _quantize(earning.amount)

	# Negate for credit note
	total_excl_neg = -total_excl
	total_tax = Decimal("0.00")
	total_incl_neg = total_excl_neg + total_tax

	# TaxTotal
	tax_total = _sub(root, CAC_NS, "TaxTotal")
	_sub(tax_total, CBC_NS, "TaxAmount", str(total_tax), currencyID="MYR")

	tax_subtotal = _sub(tax_total, CAC_NS, "TaxSubtotal")
	_sub(tax_subtotal, CBC_NS, "TaxableAmount", str(total_excl_neg), currencyID="MYR")
	_sub(tax_subtotal, CBC_NS, "TaxAmount", str(total_tax), currencyID="MYR")
	tax_cat = _sub(tax_subtotal, CAC_NS, "TaxCategory")
	_sub(tax_cat, CBC_NS, "ID", "E")
	tax_scheme = _sub(tax_cat, CAC_NS, "TaxScheme")
	_sub(tax_scheme, CBC_NS, "ID", "OTH")

	# LegalMonetaryTotal (all negative for credit note)
	monetary_total = _sub(root, CAC_NS, "LegalMonetaryTotal")
	_sub(monetary_total, CBC_NS, "TaxExclusiveAmount", str(total_excl_neg), currencyID="MYR")
	_sub(monetary_total, CBC_NS, "TaxInclusiveAmount", str(total_incl_neg), currencyID="MYR")
	_sub(monetary_total, CBC_NS, "PayableAmount", str(total_incl_neg), currencyID="MYR")

	# InvoiceLines (one per earnings row, amounts reversed)
	for idx, earning in enumerate(doc.earnings, start=1):
		line = _sub(root, CAC_NS, "InvoiceLine")
		_sub(line, CBC_NS, "ID", str(idx))
		_sub(line, CBC_NS, "InvoicedQuantity", "1", unitCode="C62")

		amount = -_quantize(earning.amount)
		_sub(line, CBC_NS, "LineExtensionAmount", str(amount), currencyID="MYR")

		item = _sub(line, CAC_NS, "Item")
		_sub(item, CBC_NS, "Description", f"Credit Note - {earning.salary_component}")

		commodity = _sub(item, CAC_NS, "CommodityClassification")
		_sub(commodity, CBC_NS, "ItemClassificationCode", "022", listID="CLASS")

		price = _sub(line, CAC_NS, "Price")
		_sub(price, CBC_NS, "PriceAmount", str(amount), currencyID="MYR")

	return ET.tostring(root, encoding="unicode", xml_declaration=True)
