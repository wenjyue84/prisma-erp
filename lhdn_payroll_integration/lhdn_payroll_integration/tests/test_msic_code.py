# Copyright (c) 2026, Prisma Technology and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestLHDNMSICCode(FrappeTestCase):
	"""Tests for LHDN MSIC Code DocType and seed data (TDD red phase).

	These tests verify that the LHDN MSIC Code DocType exists, is seeded
	with at least 4 records, and that Employee can link to it via
	custom_msic_code.
	"""

	def test_msic_code_doctype_exists(self):
		"""LHDN MSIC Code DocType must exist."""
		self.assertTrue(
			frappe.db.exists("DocType", "LHDN MSIC Code"),
			"DocType 'LHDN MSIC Code' does not exist",
		)

	def test_minimum_records_count(self):
		"""At least 4 MSIC Code records must be seeded."""
		records = frappe.get_all("LHDN MSIC Code")
		self.assertGreaterEqual(
			len(records),
			4,
			f"Expected at least 4 MSIC Code records, found {len(records)}",
		)

	def test_labour_supply_code_78300_exists(self):
		"""Code 78300 (Labour supply services) must exist."""
		self.assertTrue(
			frappe.db.exists("LHDN MSIC Code", "78300"),
			"MSIC Code '78300' (Labour supply services) not found",
		)

	def test_not_applicable_code_00000_exists(self):
		"""Code 00000 (Not Applicable) must exist."""
		self.assertTrue(
			frappe.db.exists("LHDN MSIC Code", "00000"),
			"MSIC Code '00000' (Not Applicable) not found",
		)

	def test_employee_can_link_msic_code(self):
		"""Employee custom_msic_code Link field must accept a valid MSIC Code."""
		meta = frappe.get_meta("Employee")
		field = meta.get_field("custom_msic_code")
		self.assertIsNotNone(field, "custom_msic_code field missing from Employee")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "LHDN MSIC Code")
