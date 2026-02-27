"""Tests for Self-Billed Credit Note (type 12) flow — TDD red phase (UT-023).

Tests verify that credit_note_service:
- build_credit_note_xml() returns valid UBL XML with InvoiceTypeCode='12'
- BillingReference contains the original invoice LHDN UUID and docname
- Credit note amounts are negative (reversal of original)
- cancellation_service error message directs user to issue Credit Note
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

from lhdn_payroll_integration.services.credit_note_service import build_credit_note_xml

# UBL 2.1 namespaces for XPath queries
NS = {
	"inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
	"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
	"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


class TestSelfBilledCreditNote(FrappeTestCase):
	"""Test suite for Self-Billed Credit Note (type 12) builder."""

	def _mock_original_doc(self):
		"""Create a mock Salary Slip that was previously submitted to LHDN."""
		doc = MagicMock()
		doc.name = "SAL-SLP-2026-00001"
		doc.doctype = "Salary Slip"
		doc.company = "Test Company"
		doc.custom_lhdn_uuid = "ABC-123-DEF-456"
		doc.custom_lhdn_status = "Valid"
		doc.employee = "HR-EMP-00001"
		doc.employee_name = "Ahmad bin Abdullah"
		doc.posting_date = "2026-01-15"
		doc.net_pay = 5000.00
		doc.gross_pay = 6000.00
		doc.total_deduction = 1000.00
		# Simulate earnings child table
		earning1 = MagicMock()
		earning1.salary_component = "Basic Salary"
		earning1.amount = 4000.00
		earning2 = MagicMock()
		earning2.salary_component = "Allowance"
		earning2.amount = 2000.00
		doc.earnings = [earning1, earning2]
		doc.deductions = []
		return doc

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_build_credit_note_xml_returns_string(self, mock_frappe):
		"""build_credit_note_xml must return a non-empty XML string."""
		mock_doc = self._mock_original_doc()
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_cached_doc.return_value = MagicMock(
			custom_company_tin_number="C12345678901",
			custom_sandbox_url="https://preprod-api.myinvois.hasil.gov.my",
			custom_integration_type="Sandbox",
		)
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		result = build_credit_note_xml("SAL-SLP-2026-00001", "Correction required")

		self.assertIsInstance(result, str,
			"build_credit_note_xml must return a string")
		self.assertTrue(len(result) > 0,
			"build_credit_note_xml must return a non-empty string")
		# Must be parseable XML
		ET.fromstring(result)

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_invoice_type_code_is_12(self, mock_frappe):
		"""InvoiceTypeCode element must have text '12' for credit note."""
		mock_doc = self._mock_original_doc()
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_cached_doc.return_value = MagicMock(
			custom_company_tin_number="C12345678901",
			custom_sandbox_url="https://preprod-api.myinvois.hasil.gov.my",
			custom_integration_type="Sandbox",
		)
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		xml_str = build_credit_note_xml("SAL-SLP-2026-00001", "Correction")
		root = ET.fromstring(xml_str)

		type_code = root.find(".//cbc:InvoiceTypeCode", NS)
		self.assertIsNotNone(type_code,
			"InvoiceTypeCode element must be present in credit note XML")
		self.assertEqual(type_code.text, "12",
			f"InvoiceTypeCode must be '12' for credit note, got '{type_code.text}'")

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_billing_reference_contains_original_uuid(self, mock_frappe):
		"""BillingReference/InvoiceDocumentReference/UUID must contain
		the original invoice's LHDN UUID."""
		mock_doc = self._mock_original_doc()
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_cached_doc.return_value = MagicMock(
			custom_company_tin_number="C12345678901",
			custom_sandbox_url="https://preprod-api.myinvois.hasil.gov.my",
			custom_integration_type="Sandbox",
		)
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		xml_str = build_credit_note_xml("SAL-SLP-2026-00001", "Correction")
		root = ET.fromstring(xml_str)

		uuid_elem = root.find(
			".//cac:BillingReference/cac:InvoiceDocumentReference/cbc:UUID", NS
		)
		self.assertIsNotNone(uuid_elem,
			"BillingReference/InvoiceDocumentReference/UUID must be present")
		self.assertEqual(uuid_elem.text, "ABC-123-DEF-456",
			f"UUID must match original LHDN UUID, got '{uuid_elem.text}'")

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_billing_reference_internal_id_present(self, mock_frappe):
		"""BillingReference/InvoiceDocumentReference/ID must contain
		the original Frappe docname."""
		mock_doc = self._mock_original_doc()
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_cached_doc.return_value = MagicMock(
			custom_company_tin_number="C12345678901",
			custom_sandbox_url="https://preprod-api.myinvois.hasil.gov.my",
			custom_integration_type="Sandbox",
		)
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		xml_str = build_credit_note_xml("SAL-SLP-2026-00001", "Correction")
		root = ET.fromstring(xml_str)

		id_elem = root.find(
			".//cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID", NS
		)
		self.assertIsNotNone(id_elem,
			"BillingReference/InvoiceDocumentReference/ID must be present")
		self.assertEqual(id_elem.text, "SAL-SLP-2026-00001",
			f"ID must match original docname, got '{id_elem.text}'")

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_credit_note_amount_is_negative_adjustment(self, mock_frappe):
		"""Credit note line amounts must be negative (reversal of original).
		The LegalMonetaryTotal/PayableAmount should be negative."""
		mock_doc = self._mock_original_doc()
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_cached_doc.return_value = MagicMock(
			custom_company_tin_number="C12345678901",
			custom_sandbox_url="https://preprod-api.myinvois.hasil.gov.my",
			custom_integration_type="Sandbox",
		)
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		xml_str = build_credit_note_xml("SAL-SLP-2026-00001", "Reversal")
		root = ET.fromstring(xml_str)

		payable = root.find(
			".//cac:LegalMonetaryTotal/cbc:PayableAmount", NS
		)
		self.assertIsNotNone(payable,
			"LegalMonetaryTotal/PayableAmount must be present")
		payable_amount = float(payable.text)
		self.assertLess(payable_amount, 0,
			f"Credit note PayableAmount must be negative, got {payable_amount}")

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_credit_note_references_original_docname(self, mock_frappe):
		"""The credit note XML must include a reference to the original
		document name somewhere in the document (BillingReference or Note)."""
		mock_doc = self._mock_original_doc()
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_cached_doc.return_value = MagicMock(
			custom_company_tin_number="C12345678901",
			custom_sandbox_url="https://preprod-api.myinvois.hasil.gov.my",
			custom_integration_type="Sandbox",
		)
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		xml_str = build_credit_note_xml("SAL-SLP-2026-00001", "Correction")

		self.assertIn("SAL-SLP-2026-00001", xml_str,
			"Credit note XML must reference the original docname")

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_credit_note_supplier_id_uses_lhdn_tin(self, mock_frappe):
		"""Supplier party ID in credit note must use employee.custom_lhdn_tin, not doc.employee (US-009)."""
		mock_doc = self._mock_original_doc()

		mock_employee = MagicMock()
		mock_employee.custom_lhdn_tin = "IG12345678901"
		mock_employee.custom_id_type = "NRIC"
		mock_employee.custom_id_value = "901201145678"
		mock_employee.custom_is_foreign_worker = 0
		mock_employee.custom_state_code = "01"
		mock_employee.custom_sst_registration_number = None

		mock_company = MagicMock()
		mock_company.custom_company_tin_number = "C12345678901"
		mock_company.name = "Test Company"
		mock_company.custom_state_code = "14"
		mock_company.custom_sst_registration_number = None

		def _get_doc(doctype, name=None, **kw):
			if doctype == "Salary Slip":
				return mock_doc
			if doctype == "Employee":
				return mock_employee
			return MagicMock()

		mock_frappe.get_doc.side_effect = _get_doc
		mock_frappe.get_cached_doc.return_value = mock_company
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_einvoice_version": "1.1",
		}.get(key, default)

		xml_str = build_credit_note_xml("SAL-SLP-2026-00001", "Correction")
		root = ET.fromstring(xml_str)

		supplier_id = root.find(
			".//cac:AccountingSupplierParty//cac:PartyIdentification/cbc:ID", NS
		)
		self.assertIsNotNone(supplier_id, "Supplier PartyIdentification/ID must be present")
		self.assertEqual(supplier_id.text, "IG12345678901",
			f"Supplier ID must be LHDN TIN, got '{supplier_id.text}' (should not be ERPNext employee code)")
		self.assertEqual(supplier_id.get("schemeID"), "TIN",
			"Supplier ID schemeID must be 'TIN'")

	@patch("lhdn_payroll_integration.services.credit_note_service.frappe")
	def test_credit_note_raises_if_source_is_cancelled(self, mock_frappe):
		"""build_credit_note_xml must raise ValidationError when source custom_lhdn_status == Cancelled."""
		mock_doc = self._mock_original_doc()
		mock_doc.custom_lhdn_status = "Cancelled"
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.ValidationError = frappe.ValidationError
		mock_frappe.throw.side_effect = frappe.ValidationError("Cannot issue credit note")

		with self.assertRaises(frappe.ValidationError):
			build_credit_note_xml("SAL-SLP-2026-00001", "Correction")

	def test_cancellation_error_includes_credit_note_instruction(self):
		"""When cancellation_service rejects a cancellation (past 72 hours),
		the ValidationError message must include credit note guidance."""
		from lhdn_payroll_integration.services.cancellation_service import _handle_cancel

		# Create a mock doc that is past the 72-hour window
		doc = MagicMock()
		doc.custom_lhdn_status = "Valid"
		doc.custom_lhdn_uuid = "ABC-123-DEF-456"
		doc.custom_lhdn_validated_datetime = frappe.utils.add_days(
			frappe.utils.now_datetime(), -4
		)
		doc.custom_lhdn_submission_datetime = frappe.utils.add_days(
			frappe.utils.now_datetime(), -4
		)

		with self.assertRaises(frappe.ValidationError) as ctx:
			_handle_cancel(doc, "on_cancel")

		error_msg = str(ctx.exception)
		self.assertIn("Credit Note", error_msg,
			f"Cancellation error must mention 'Credit Note', got: {error_msg}")
