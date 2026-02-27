"""Tests for 7-year LHDN audit retention locking — TDD red phase (UT-027).

Tests verify that:
- Retention date is set on LHDN submission
- Retention date is 7 years from submission
- Archive job marks old records
- Archived records cannot be amended
- Records within 7 years are not archived
- Expense Claims with LHDN UUIDs are also locked before_amend (US-045)
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from lhdn_payroll_integration.services.retention_service import run_retention_archival, get_retention_date


class TestAuditRetention(FrappeTestCase):
	"""Test suite for 7-year LHDN audit retention locking."""

	def test_retention_date_set_on_submission(self):
		"""get_retention_date must return a date value (not None) for a
		submitted document with custom_lhdn_validated_datetime set."""
		submission_date = datetime(2026, 1, 15, 10, 0, 0)
		result = get_retention_date(submission_date)
		self.assertIsNotNone(result,
			"Retention date must not be None for a submitted document")

	def test_retention_date_is_7_years_from_submission(self):
		"""get_retention_date must return a date exactly 7 years after
		the submission datetime."""
		submission_date = datetime(2026, 1, 15, 10, 0, 0)
		result = get_retention_date(submission_date)
		expected = datetime(2033, 1, 15, 10, 0, 0)
		self.assertEqual(result, expected,
			f"Retention date must be 7 years after submission. "
			f"Expected {expected}, got {result}")

	@patch("lhdn_payroll_integration.services.retention_service.frappe")
	def test_archive_job_marks_old_records(self, mock_frappe):
		"""run_retention_archival must set custom_lhdn_archived=1 for
		records whose retention period has expired (7+ years old)."""
		# Create a mock record that is 8 years old
		old_record = frappe._dict({
			"name": "SAL-SLP-2018-00001",
			"doctype": "Salary Slip",
			"custom_lhdn_validated_datetime": datetime(2018, 1, 15, 10, 0, 0),
			"custom_lhdn_archived": 0,
		})
		mock_frappe.get_all.return_value = [old_record]
		mock_frappe.utils.now_datetime.return_value = datetime(2026, 2, 1, 10, 0, 0)
		mock_frappe.db = MagicMock()

		run_retention_archival()

		mock_frappe.db.set_value.assert_called()
		# Verify the archived flag was set
		set_call_args = str(mock_frappe.db.set_value.call_args)
		self.assertIn("custom_lhdn_archived", set_call_args,
			"run_retention_archival must set custom_lhdn_archived")

	@patch("lhdn_payroll_integration.services.retention_service.frappe")
	def test_archived_record_cannot_be_amended(self, mock_frappe):
		"""When custom_lhdn_archived=1, any attempt to amend should be
		blocked by raising frappe.ValidationError."""
		doc = MagicMock()
		doc.custom_lhdn_archived = 1
		doc.custom_lhdn_status = "Valid"
		mock_frappe.ValidationError = frappe.ValidationError
		mock_frappe.throw.side_effect = frappe.ValidationError("Record is archived")

		from lhdn_payroll_integration.services.retention_service import check_retention_lock
		with self.assertRaises(frappe.ValidationError):
			check_retention_lock(doc)

	@patch("lhdn_payroll_integration.services.retention_service.frappe")
	def test_records_within_7_years_not_archived(self, mock_frappe):
		"""Records submitted less than 7 years ago must NOT be archived.
		run_retention_archival should skip them."""
		recent_record = frappe._dict({
			"name": "SAL-SLP-2025-00001",
			"doctype": "Salary Slip",
			"custom_lhdn_validated_datetime": datetime(2025, 6, 15, 10, 0, 0),
			"custom_lhdn_archived": 0,
		})
		mock_frappe.get_all.return_value = [recent_record]
		mock_frappe.utils.now_datetime.return_value = datetime(2026, 2, 1, 10, 0, 0)
		mock_frappe.db = MagicMock()

		run_retention_archival()

		# db.set_value should NOT be called for recent records
		if mock_frappe.db.set_value.called:
			for c in mock_frappe.db.set_value.call_args_list:
				self.assertNotIn("SAL-SLP-2025-00001", str(c),
					"Recent record (within 7 years) must not be archived")

	@patch("lhdn_payroll_integration.services.retention_service.frappe")
	def test_expense_claim_archived_cannot_be_amended(self, mock_frappe):
		"""US-045: When an Expense Claim has custom_lhdn_archived=1, the
		before_amend hook (check_retention_lock) must raise ValidationError."""
		doc = MagicMock()
		doc.custom_lhdn_archived = 1
		doc.doctype = "Expense Claim"
		mock_frappe.ValidationError = frappe.ValidationError
		mock_frappe.throw.side_effect = frappe.ValidationError("Record is archived")

		from lhdn_payroll_integration.services.retention_service import check_retention_lock
		with self.assertRaises(frappe.ValidationError,
			msg="Expense Claim with custom_lhdn_archived=1 must raise ValidationError on before_amend"):
			check_retention_lock(doc)

	@patch("lhdn_payroll_integration.services.retention_service.frappe")
	def test_run_retention_archival_queries_expense_claims(self, mock_frappe):
		"""US-045: run_retention_archival must query both Salary Slips and
		Expense Claims, not just Salary Slips."""
		mock_frappe.get_all.return_value = []
		mock_frappe.utils.now_datetime.return_value = datetime(2026, 2, 1, 10, 0, 0)
		mock_frappe.db = MagicMock()

		run_retention_archival()

		# get_all must be called at least twice — once for each doctype
		self.assertGreaterEqual(mock_frappe.get_all.call_count, 2,
			"run_retention_archival must query both Salary Slip and Expense Claim")

		# Verify Expense Claim is among the queried doctypes
		queried_doctypes = [call.args[0] for call in mock_frappe.get_all.call_args_list]
		self.assertIn("Expense Claim", queried_doctypes,
			"run_retention_archival must query Expense Claim doctype")

	@patch("lhdn_payroll_integration.services.retention_service.frappe")
	def test_run_retention_archival_archives_old_expense_claims(self, mock_frappe):
		"""US-045: run_retention_archival must archive Expense Claims whose
		7-year retention period has expired."""
		old_expense_claim = frappe._dict({
			"name": "EXP-2018-00001",
			"doctype": "Expense Claim",
			"custom_lhdn_validated_datetime": datetime(2018, 3, 10, 10, 0, 0),
			"custom_lhdn_archived": 0,
		})

		def get_all_side_effect(doctype, **kwargs):
			if doctype == "Expense Claim":
				return [old_expense_claim]
			return []

		mock_frappe.get_all.side_effect = get_all_side_effect
		mock_frappe.utils.now_datetime.return_value = datetime(2026, 2, 1, 10, 0, 0)
		mock_frappe.db = MagicMock()

		run_retention_archival()

		mock_frappe.db.set_value.assert_called()
		# Verify Expense Claim was archived
		set_value_calls = mock_frappe.db.set_value.call_args_list
		expense_claim_archived = any(
			"EXP-2018-00001" in str(c) and "custom_lhdn_archived" in str(c)
			for c in set_value_calls
		)
		self.assertTrue(expense_claim_archived,
			"run_retention_archival must archive the old Expense Claim")
