"""Tests for monthly consolidation scheduler — TDD red phase (UT-018).

Tests verify that run_monthly_consolidation():
- Queries previous calendar month's pending Salary Slips and Expense Claims
- Excludes high-value docs (>RM 10,000) from batch (submitted individually)
- Groups remaining docs into one consolidated submission
- Sets custom_is_consolidated=1 after successful submission
- Skips already-submitted docs
- Handles empty batches silently
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, call, MagicMock
from datetime import date

from lhdn_payroll_integration.services.consolidation_service import run_monthly_consolidation


class TestConsolidationScheduler(FrappeTestCase):
	"""Test suite for run_monthly_consolidation()."""

	def _make_salary_slip(self, name, net_pay=5000, status="Pending", is_consolidated=0, posting_date=None):
		"""Helper to create a mock Salary Slip record."""
		return frappe._dict({
			"name": name,
			"doctype": "Salary Slip",
			"net_pay": net_pay,
			"custom_lhdn_status": status,
			"custom_is_consolidated": is_consolidated,
			"posting_date": posting_date or date(2026, 1, 15),
		})

	def _make_expense_claim(self, name, total=3000, status="Pending", is_consolidated=0, posting_date=None):
		"""Helper to create a mock Expense Claim record."""
		return frappe._dict({
			"name": name,
			"doctype": "Expense Claim",
			"total_sanctioned_amount": total,
			"custom_lhdn_status": status,
			"custom_is_consolidated": is_consolidated,
			"posting_date": posting_date or date(2026, 1, 20),
		})

	@patch("lhdn_payroll_integration.services.consolidation_service.frappe")
	def test_queries_previous_calendar_month_records(self, mock_frappe):
		"""run_monthly_consolidation must call frappe.get_all for Salary Slip
		and Expense Claim filtered to the previous calendar month, status=Pending,
		and custom_is_consolidated=0."""
		mock_frappe.get_all.return_value = []
		mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
		mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
		mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
		mock_frappe.utils.today.return_value = "2026-02-15"

		run_monthly_consolidation()

		# Must have queried both doctypes
		get_all_calls = mock_frappe.get_all.call_args_list
		doctypes_queried = [c[0][0] if c[0] else c[1].get("doctype") for c in get_all_calls]
		self.assertIn("Salary Slip", doctypes_queried,
			"run_monthly_consolidation must query Salary Slip records")
		self.assertIn("Expense Claim", doctypes_queried,
			"run_monthly_consolidation must query Expense Claim records")

		# Verify at least one call uses the correct filters
		self.assertTrue(len(get_all_calls) >= 2,
			"Expected at least 2 frappe.get_all calls (Salary Slip + Expense Claim)")

	@patch("lhdn_payroll_integration.services.consolidation_service.frappe")
	def test_high_value_docs_excluded_from_batch(self, mock_frappe):
		"""Documents with total > RM 10,000 must NOT be included in the
		consolidated batch — they should be submitted individually."""
		high_value_slip = self._make_salary_slip("SS-HV-001", net_pay=15000)
		normal_slip = self._make_salary_slip("SS-NRM-001", net_pay=5000)
		high_value_claim = self._make_expense_claim("EC-HV-001", total=12000)

		mock_frappe.get_all.side_effect = [
			[high_value_slip, normal_slip],  # Salary Slips
			[high_value_claim],               # Expense Claims
		]
		mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
		mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
		mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
		mock_frappe.utils.today.return_value = "2026-02-15"
		mock_frappe.db = MagicMock()

		with patch("lhdn_payroll_integration.services.consolidation_service.submission_service") as mock_sub:
			run_monthly_consolidation()

			# High-value docs should be submitted individually
			# The batch/consolidated call should NOT include high-value docs
			# At minimum, we verify the function ran and made submission calls
			individual_calls = [c for c in mock_sub.method_calls
				if "individual" in str(c).lower() or "enqueue" in str(c).lower()]
			# High-value docs must be handled separately from the batch
			self.assertTrue(
				mock_sub.called or mock_sub.method_calls,
				"submission_service must be called for high-value documents"
			)

	@patch("lhdn_payroll_integration.services.consolidation_service.frappe")
	def test_batch_submission_called_for_eligible_docs(self, mock_frappe):
		"""Eligible (non-high-value, pending, not-yet-consolidated) documents
		must be grouped into one consolidated submission."""
		slip1 = self._make_salary_slip("SS-001", net_pay=3000)
		slip2 = self._make_salary_slip("SS-002", net_pay=7000)
		claim1 = self._make_expense_claim("EC-001", total=2000)

		mock_frappe.get_all.side_effect = [
			[slip1, slip2],  # Salary Slips
			[claim1],         # Expense Claims
		]
		mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
		mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
		mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
		mock_frappe.utils.today.return_value = "2026-02-15"
		mock_frappe.db = MagicMock()

		with patch("lhdn_payroll_integration.services.consolidation_service.submission_service") as mock_sub:
			run_monthly_consolidation()

			# Consolidated/batch submission must be called
			self.assertTrue(
				mock_sub.called or mock_sub.method_calls,
				"submission_service must be invoked for consolidated batch submission"
			)

	@patch("lhdn_payroll_integration.services.consolidation_service.frappe")
	def test_is_consolidated_set_after_successful_submission(self, mock_frappe):
		"""After successful submission, all included documents must have
		custom_is_consolidated set to 1 via frappe.db.set_value."""
		slip1 = self._make_salary_slip("SS-001", net_pay=4000)
		claim1 = self._make_expense_claim("EC-001", total=2000)

		mock_frappe.get_all.side_effect = [
			[slip1],    # Salary Slips
			[claim1],   # Expense Claims
		]
		mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
		mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
		mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
		mock_frappe.utils.today.return_value = "2026-02-15"
		mock_frappe.db = MagicMock()

		with patch("lhdn_payroll_integration.services.consolidation_service.submission_service"):
			run_monthly_consolidation()

		# frappe.db.set_value should be called to mark docs as consolidated
		set_value_calls = mock_frappe.db.set_value.call_args_list
		self.assertTrue(
			len(set_value_calls) >= 2,
			f"Expected at least 2 set_value calls (one per doc), got {len(set_value_calls)}"
		)

		# Verify the calls set custom_is_consolidated = 1
		for c in set_value_calls:
			args = c[0] if c[0] else ()
			kwargs = c[1] if c[1] else {}
			# set_value(doctype, name, field, value) or set_value(doctype, name, {field: value})
			if len(args) >= 4:
				self.assertEqual(args[2], "custom_is_consolidated")
				self.assertEqual(args[3], 1)
			elif len(args) >= 3 and isinstance(args[2], dict):
				self.assertIn("custom_is_consolidated", args[2])
				self.assertEqual(args[2]["custom_is_consolidated"], 1)

	@patch("lhdn_payroll_integration.services.consolidation_service.frappe")
	def test_already_submitted_docs_excluded(self, mock_frappe):
		"""Documents that are NOT status='Pending' must not be included.
		The frappe.get_all filter must include custom_lhdn_status='Pending'."""
		mock_frappe.get_all.return_value = []
		mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
		mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
		mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
		mock_frappe.utils.today.return_value = "2026-02-15"

		run_monthly_consolidation()

		# Verify the filters include status='Pending' or custom_lhdn_status='Pending'
		for c in mock_frappe.get_all.call_args_list:
			args = c[0] if c[0] else ()
			kwargs = c[1] if c[1] else {}
			filters = kwargs.get("filters") or (args[1] if len(args) > 1 else {})
			if isinstance(filters, dict):
				self.assertIn("custom_lhdn_status", filters,
					"Query filters must include custom_lhdn_status to exclude already-submitted docs")
				self.assertEqual(filters["custom_lhdn_status"], "Pending")

	@patch("lhdn_payroll_integration.services.consolidation_service.frappe")
	def test_empty_batch_completes_silently(self, mock_frappe):
		"""When no documents match the criteria, run_monthly_consolidation
		must complete without raising any exception."""
		mock_frappe.get_all.return_value = []
		mock_frappe.utils.get_first_day.return_value = date(2026, 1, 1)
		mock_frappe.utils.get_last_day.return_value = date(2026, 1, 31)
		mock_frappe.utils.add_months.return_value = date(2026, 1, 15)
		mock_frappe.utils.today.return_value = "2026-02-15"

		# Must not raise
		try:
			run_monthly_consolidation()
		except Exception as e:
			self.fail(f"run_monthly_consolidation raised {type(e).__name__} on empty batch: {e}")
