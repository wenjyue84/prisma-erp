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


def _add_postal_address(party_elem, state_code):
	"""Add cac:PostalAddress with cbc:CountrySubentityCode to a Party element."""
	postal = _sub(party_elem, CAC_NS, "PostalAddress")
	_sub(postal, CBC_NS, "CountrySubentityCode", state_code)


def _add_party_tax_scheme(party_elem, sst_registration):
	"""Add cac:PartyTaxScheme to a Party element."""
	reg_name = sst_registration if sst_registration else "NA"
	scheme_id = "SST" if sst_registration else "NA"
	tax_scheme_elem = _sub(party_elem, CAC_NS, "PartyTaxScheme")
	_sub(tax_scheme_elem, CBC_NS, "RegistrationName", reg_name)
	inner_scheme = _sub(tax_scheme_elem, CAC_NS, "TaxScheme")
	_sub(inner_scheme, CBC_NS, "ID", scheme_id)


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

	if doc.custom_lhdn_status == "Cancelled":
		frappe.throw(
			f"Cannot issue credit note: {original_docname} has already been cancelled on LHDN. "
			"LHDN rejects credit notes that reference a cancelled document.",
			frappe.ValidationError,
		)

	employee = frappe.get_doc("Employee", doc.employee)
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

	# Resolve state codes for postal addresses
	supplier_state = (
		"17" if getattr(employee, "custom_is_foreign_worker", 0)
		else str(getattr(employee, "custom_state_code", None) or "01")
	)
	buyer_state = str(getattr(company, "custom_state_code", None) or "14")

	# AccountingSupplierParty (Employee = Payee = Supplier in self-billed)
	# Use LHDN TIN (not ERPNext employee code) as supplier identifier
	supplier_party = _sub(root, CAC_NS, "AccountingSupplierParty")
	supplier_inner = _sub(supplier_party, CAC_NS, "Party")
	supplier_id = _sub(supplier_inner, CAC_NS, "PartyIdentification")
	_sub(supplier_id, CBC_NS, "ID", employee.custom_lhdn_tin, schemeID="TIN")
	supplier_name = _sub(supplier_inner, CAC_NS, "PartyName")
	_sub(supplier_name, CBC_NS, "Name", doc.employee_name)
	_add_postal_address(supplier_inner, supplier_state)
	_add_party_tax_scheme(
		supplier_inner,
		getattr(employee, "custom_sst_registration_number", None) or ""
	)

	# AccountingCustomerParty (Company = Payer = Buyer in self-billed)
	customer_party = _sub(root, CAC_NS, "AccountingCustomerParty")
	customer_inner = _sub(customer_party, CAC_NS, "Party")
	customer_id = _sub(customer_inner, CAC_NS, "PartyIdentification")
	_sub(customer_id, CBC_NS, "ID", company.custom_company_tin_number, schemeID="TIN")
	customer_name = _sub(customer_inner, CAC_NS, "PartyName")
	_sub(customer_name, CBC_NS, "Name", doc.company)
	_add_postal_address(customer_inner, buyer_state)
	_add_party_tax_scheme(
		customer_inner,
		getattr(company, "custom_sst_registration_number", None) or ""
	)

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
