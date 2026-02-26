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
		expected = ["NRIC", "Passport", "Business Registration Number", "Army ID"]
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
				"custom_lhdn_classification_code": "022",
			}
		)
		sc.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Salary Component", sc.name, force=True))

		# Reload from DB and verify
		reloaded = frappe.get_doc("Salary Component", sc.name)
		self.assertEqual(
			reloaded.custom_lhdn_classification_code,
			"022",
			"custom_lhdn_classification_code value did not persist after save",
		)
