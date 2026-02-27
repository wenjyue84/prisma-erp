# Copyright (c) 2026, Prisma Technology and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEmployeeCustomFields(FrappeTestCase):
	"""Tests for Employee LHDN custom fields (TDD red phase).

	These tests verify that the 8 custom fields required for LHDN
	self-billed e-Invoice are present on the Employee DocType under
	the 'LHDN Malaysia Setup' section.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.meta = frappe.get_meta("Employee")

	def test_employee_lhdn_section_exists(self):
		"""LHDN Malaysia Setup section break must exist on Employee."""
		field = self.meta.get_field("custom_lhdn_section")
		self.assertIsNotNone(field, "custom_lhdn_section field missing from Employee")
		self.assertEqual(field.fieldtype, "Section Break")

	def test_requires_self_billed_invoice_is_check_field(self):
		"""custom_requires_self_billed_invoice must be a Check field defaulting to 0."""
		field = self.meta.get_field("custom_requires_self_billed_invoice")
		self.assertIsNotNone(
			field, "custom_requires_self_billed_invoice field missing from Employee"
		)
		self.assertEqual(field.fieldtype, "Check")
		self.assertEqual(str(field.default or "0"), "0")

	def test_lhdn_tin_field_exists(self):
		"""custom_lhdn_tin must be a Data field with mandatory_depends_on."""
		field = self.meta.get_field("custom_lhdn_tin")
		self.assertIsNotNone(field, "custom_lhdn_tin field missing from Employee")
		self.assertEqual(field.fieldtype, "Data")
		self.assertIn(
			"custom_requires_self_billed_invoice",
			str(field.mandatory_depends_on or ""),
			"custom_lhdn_tin should be mandatory when custom_requires_self_billed_invoice is checked",
		)

	def test_id_type_options(self):
		"""custom_id_type must be a Select field with the correct options."""
		field = self.meta.get_field("custom_id_type")
		self.assertIsNotNone(field, "custom_id_type field missing from Employee")
		self.assertEqual(field.fieldtype, "Select")
		options = (field.options or "").split("\n")
		expected = ["NRIC", "Passport", "BRN", "Army ID"]
		for opt in expected:
			self.assertIn(opt, options, f"Option '{opt}' missing from custom_id_type")

	def test_id_value_field_exists(self):
		"""custom_id_value must be a Data field."""
		field = self.meta.get_field("custom_id_value")
		self.assertIsNotNone(field, "custom_id_value field missing from Employee")
		self.assertEqual(field.fieldtype, "Data")

	def test_msic_code_link_field(self):
		"""custom_msic_code must be a Link field to LHDN MSIC Code."""
		field = self.meta.get_field("custom_msic_code")
		self.assertIsNotNone(field, "custom_msic_code field missing from Employee")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "LHDN MSIC Code")

	def test_is_foreign_worker_field(self):
		"""custom_is_foreign_worker must be a Check field defaulting to 0."""
		field = self.meta.get_field("custom_is_foreign_worker")
		self.assertIsNotNone(
			field, "custom_is_foreign_worker field missing from Employee"
		)
		self.assertEqual(field.fieldtype, "Check")
		self.assertEqual(str(field.default or "0"), "0")

	def test_bank_account_number_field(self):
		"""custom_bank_account_number must be a Data field."""
		field = self.meta.get_field("custom_bank_account_number")
		self.assertIsNotNone(
			field, "custom_bank_account_number field missing from Employee"
		)
		self.assertEqual(field.fieldtype, "Data")

	def test_all_fields_have_correct_module(self):
		"""All LHDN custom fields must have module = 'LHDN Payroll Integration'."""
		custom_field_names = [
			"custom_lhdn_section",
			"custom_requires_self_billed_invoice",
			"custom_lhdn_tin",
			"custom_id_type",
			"custom_id_value",
			"custom_msic_code",
			"custom_is_foreign_worker",
			"custom_bank_account_number",
		]
		for fname in custom_field_names:
			# Custom fields are stored in Custom Field doctype
			cf_name = f"Employee-{fname}"
			self.assertTrue(
				frappe.db.exists("Custom Field", cf_name),
				f"Custom Field '{cf_name}' does not exist in database",
			)
			cf_doc = frappe.get_doc("Custom Field", cf_name)
			self.assertEqual(
				cf_doc.module,
				"LHDN Payroll Integration",
				f"Custom Field '{cf_name}' module should be 'LHDN Payroll Integration', got '{cf_doc.module}'",
			)


class TestSalaryComponentCustomFields(FrappeTestCase):
	"""Tests for Salary Component LHDN custom fields (TDD red phase).

	These tests verify that the custom_lhdn_classification_code field
	is present on the Salary Component DocType as a Select field with
	the correct LHDN classification code options.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.meta = frappe.get_meta("Salary Component")

	def test_lhdn_classification_code_field_exists(self):
		"""custom_lhdn_classification_code must exist on Salary Component."""
		field = self.meta.get_field("custom_lhdn_classification_code")
		self.assertIsNotNone(
			field,
			"custom_lhdn_classification_code field missing from Salary Component",
		)
		self.assertEqual(field.fieldtype, "Select")

	def test_classification_code_options_contain_022(self):
		"""Classification code options must include 022 and 037."""
		field = self.meta.get_field("custom_lhdn_classification_code")
		self.assertIsNotNone(
			field,
			"custom_lhdn_classification_code field missing from Salary Component",
		)
		options = (field.options or "").split("\n")
		self.assertTrue(
			any("022" in opt for opt in options),
			"Option containing '022' (Employment Income) missing from classification codes",
		)
		self.assertTrue(
			any("037" in opt for opt in options),
			"Option containing '037' (Allowances) missing from classification codes",
		)

	def test_field_is_optional(self):
		"""custom_lhdn_classification_code should be optional (not mandatory)."""
		field = self.meta.get_field("custom_lhdn_classification_code")
		self.assertIsNotNone(
			field,
			"custom_lhdn_classification_code field missing from Salary Component",
		)
		self.assertFalse(
			field.reqd,
			"custom_lhdn_classification_code should not be mandatory",
		)

	def test_field_persists_after_save(self):
		"""A Salary Component with custom_lhdn_classification_code should persist the value."""
		sc = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": "_Test LHDN Component",
				"salary_component_abbr": "TLHDN",
				"type": "Earning",
				"custom_lhdn_classification_code": "022 : Others",
			}
		)
		sc.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Salary Component", sc.name, force=True))

		# Reload from DB and verify
		reloaded = frappe.get_doc("Salary Component", sc.name)
		self.assertEqual(
			reloaded.custom_lhdn_classification_code,
			"022 : Others",
			"custom_lhdn_classification_code value did not persist after save",
		)


class TestSalarySlipCustomFields(FrappeTestCase):
	"""Tests for Salary Slip LHDN custom fields (TDD red phase).

	These tests verify that the 10 custom fields for LHDN e-Invoice
	status tracking are present on the Salary Slip DocType under the
	'LHDN e-Invoice Status' section. All response fields must be read_only.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.meta = frappe.get_meta("Salary Slip")

	def test_lhdn_status_section_exists(self):
		"""LHDN e-Invoice Status section break must exist on Salary Slip."""
		field = self.meta.get_field("custom_lhdn_section")
		self.assertIsNotNone(field, "custom_lhdn_section field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Section Break")

	def test_lhdn_status_options(self):
		"""custom_lhdn_status must be a Select with correct status options."""
		field = self.meta.get_field("custom_lhdn_status")
		self.assertIsNotNone(field, "custom_lhdn_status field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Select")
		options = (field.options or "").split("\n")
		for expected in ["Pending", "Submitted", "Valid", "Invalid", "Exempt", "Cancelled"]:
			self.assertIn(expected, options, f"Option '{expected}' missing from custom_lhdn_status")
		# Status field should be read_only (set by background worker only)
		self.assertEqual(int(field.read_only or 0), 1, "custom_lhdn_status should be read_only")

	def test_uuid_is_read_only(self):
		"""custom_lhdn_uuid must be a Data field and read_only."""
		field = self.meta.get_field("custom_lhdn_uuid")
		self.assertIsNotNone(field, "custom_lhdn_uuid field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Data")
		self.assertEqual(int(field.read_only or 0), 1, "custom_lhdn_uuid should be read_only")

	def test_submission_datetime_is_datetime_field(self):
		"""custom_lhdn_submission_datetime must be a Datetime field and read_only."""
		field = self.meta.get_field("custom_lhdn_submission_datetime")
		self.assertIsNotNone(field, "custom_lhdn_submission_datetime field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Datetime")
		self.assertEqual(int(field.read_only or 0), 1, "custom_lhdn_submission_datetime should be read_only")

	def test_validated_datetime_is_datetime_field(self):
		"""custom_lhdn_validated_datetime must be a Datetime field and read_only."""
		field = self.meta.get_field("custom_lhdn_validated_datetime")
		self.assertIsNotNone(field, "custom_lhdn_validated_datetime field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Datetime")
		self.assertEqual(int(field.read_only or 0), 1, "custom_lhdn_validated_datetime should be read_only")

	def test_retry_count_defaults_to_zero(self):
		"""custom_retry_count must be an Int field, read_only, default 0."""
		field = self.meta.get_field("custom_retry_count")
		self.assertIsNotNone(field, "custom_retry_count field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Int")
		self.assertEqual(int(field.read_only or 0), 1, "custom_retry_count should be read_only")
		self.assertEqual(str(field.default or "0"), "0", "custom_retry_count should default to 0")

	def test_is_consolidated_defaults_to_zero(self):
		"""custom_is_consolidated must be a Check field, read_only, default 0."""
		field = self.meta.get_field("custom_is_consolidated")
		self.assertIsNotNone(field, "custom_is_consolidated field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Check")
		self.assertEqual(int(field.read_only or 0), 1, "custom_is_consolidated should be read_only")
		self.assertEqual(str(field.default or "0"), "0", "custom_is_consolidated should default to 0")

	def test_qr_code_is_read_only(self):
		"""custom_lhdn_qr_code must be an HTML field and read_only."""
		field = self.meta.get_field("custom_lhdn_qr_code")
		self.assertIsNotNone(field, "custom_lhdn_qr_code field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "HTML")
		self.assertEqual(int(field.read_only or 0), 1, "custom_lhdn_qr_code should be read_only")

	def test_qr_url_is_read_only(self):
		"""custom_lhdn_qr_url must be a Data field and read_only."""
		field = self.meta.get_field("custom_lhdn_qr_url")
		self.assertIsNotNone(field, "custom_lhdn_qr_url field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Data")
		self.assertEqual(int(field.read_only or 0), 1, "custom_lhdn_qr_url should be read_only")

	def test_error_log_is_read_only(self):
		"""custom_error_log must be a Text Editor field and read_only."""
		field = self.meta.get_field("custom_error_log")
		self.assertIsNotNone(field, "custom_error_log field missing from Salary Slip")
		self.assertEqual(field.fieldtype, "Text Editor")
		self.assertEqual(int(field.read_only or 0), 1, "custom_error_log should be read_only")


class TestExpenseClaimCustomFields(FrappeTestCase):
	"""Tests for Expense Claim LHDN custom fields (TDD red phase).

	These tests verify that the 9 custom fields for LHDN e-Invoice
	compliance are present on the Expense Claim DocType. The expense
	category and employee receipt fields are editable; status/response
	fields are read_only.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.meta = frappe.get_meta("Expense Claim")

	def test_lhdn_section_exists(self):
		"""LHDN e-Invoice section break must exist on Expense Claim."""
		field = self.meta.get_field("custom_lhdn_section")
		self.assertIsNotNone(field, "custom_lhdn_section field missing from Expense Claim")
		self.assertEqual(field.fieldtype, "Section Break")

	def test_expense_category_options(self):
		"""custom_expense_category must be a Select with the correct pathway options."""
		field = self.meta.get_field("custom_expense_category")
		self.assertIsNotNone(field, "custom_expense_category field missing from Expense Claim")
		self.assertEqual(field.fieldtype, "Select")
		options = (field.options or "").split("\n")
		for expected in ["Self-Billed Required", "Employee Receipt Provided", "Overseas - Exempt"]:
			self.assertIn(expected, options, f"Option '{expected}' missing from custom_expense_category")

	def test_receipt_fields_are_editable(self):
		"""custom_employee_receipt_uuid and custom_employee_receipt_qr_url must be editable."""
		for fname in ["custom_employee_receipt_uuid", "custom_employee_receipt_qr_url"]:
			field = self.meta.get_field(fname)
			self.assertIsNotNone(field, f"{fname} field missing from Expense Claim")
			self.assertEqual(field.fieldtype, "Data")
			self.assertEqual(
				int(field.read_only or 0), 0,
				f"{fname} should be editable (read_only=0)",
			)

	def test_status_fields_are_read_only(self):
		"""LHDN response fields must be read_only."""
		read_only_fields = {
			"custom_lhdn_status": "Select",
			"custom_lhdn_uuid": "Data",
			"custom_lhdn_qr_url": "Data",
			"custom_error_log": "Text Editor",
			"custom_retry_count": "Int",
		}
		for fname, expected_type in read_only_fields.items():
			field = self.meta.get_field(fname)
			self.assertIsNotNone(field, f"{fname} field missing from Expense Claim")
			self.assertEqual(field.fieldtype, expected_type, f"{fname} should be {expected_type}")
			self.assertEqual(
				int(field.read_only or 0), 1,
				f"{fname} should be read_only",
			)

	def test_retry_count_default(self):
		"""custom_retry_count must default to 0."""
		field = self.meta.get_field("custom_retry_count")
		self.assertIsNotNone(field, "custom_retry_count field missing from Expense Claim")
		self.assertEqual(str(field.default or "0"), "0", "custom_retry_count should default to 0")
