"""Tests for LHDN Monthly Submission Summary script report (US-027).

Covers:
- Column structure validation
- 12-row output (one per month)
- Monthly aggregation accuracy via mock
- Deadline status logic (Pending / On Time / Late)
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_monthly_summary.lhdn_monthly_summary import (
	get_columns,
	get_data,
)

REQUIRED_FIELDNAMES = {
	"month",
	"total_submitted",
	"valid_count",
	"invalid_count",
	"pending_count",
	"exempt_count",
	"total_value",
	"deadline_status",
}

MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]

VALID_DEADLINE_STATUSES = {"Pending", "On Time", "Late"}


class TestMonthlySummaryColumns(FrappeTestCase):
	"""Tests for get_columns() function."""

	def test_get_columns_returns_list(self):
		"""get_columns() must return a list."""
		columns = get_columns()
		self.assertIsInstance(columns, list)

	def test_get_columns_minimum_count(self):
		"""get_columns() must return at least 8 columns."""
		columns = get_columns()
		self.assertGreaterEqual(len(columns), 8)

	def test_get_columns_required_fieldnames(self):
		"""get_columns() must include all required fieldnames."""
		columns = get_columns()
		fieldnames = set()
		for col in columns:
			if isinstance(col, dict):
				fieldnames.add(col.get("fieldname"))
		for required in REQUIRED_FIELDNAMES:
			self.assertIn(required, fieldnames, f"Missing fieldname: {required}")


class TestMonthlySummaryData(FrappeTestCase):
	"""Tests for get_data() function structure and basic behaviour."""

	def test_get_data_returns_twelve_rows(self):
		"""Report always returns exactly 12 rows (one per month)."""
		filters = frappe._dict({"year": "2026"})
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(filters)
		self.assertEqual(len(rows), 12)

	def test_get_data_month_names_in_order(self):
		"""Rows must have correct month names January through December."""
		filters = frappe._dict({"year": "2026"})
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(filters)
		for i, row in enumerate(rows):
			self.assertEqual(row["month"], MONTH_NAMES[i],
				f"Row {i} has wrong month name: {row['month']}")

	def test_get_data_required_keys_present(self):
		"""Each row must contain all required keys."""
		filters = frappe._dict({"year": "2026"})
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(filters)
		for row in rows:
			for key in REQUIRED_FIELDNAMES:
				self.assertIn(key, row, f"Row missing key: {key}")

	def test_get_data_deadline_status_values_valid(self):
		"""deadline_status must be one of: Pending, On Time, Late."""
		filters = frappe._dict({"year": "2026"})
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(filters)
		for row in rows:
			self.assertIn(row["deadline_status"], VALID_DEADLINE_STATUSES,
				f"Unexpected deadline_status: {row['deadline_status']}")

	def test_empty_months_have_zero_counts(self):
		"""Months with no data must have all counts at zero."""
		filters = frappe._dict({"year": "2026"})
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(filters)
		for row in rows:
			self.assertEqual(row["total_submitted"], 0)
			self.assertEqual(row["valid_count"], 0)
			self.assertEqual(row["invalid_count"], 0)
			self.assertEqual(row["pending_count"], 0)
			self.assertEqual(row["exempt_count"], 0)
			self.assertAlmostEqual(row["total_value"], 0.0)


class TestMonthlySummaryAggregation(FrappeTestCase):
	"""Tests verifying monthly aggregation accuracy."""

	def test_aggregation_counts_correctly(self):
		"""Monthly aggregation must correctly group status counts and sum values."""
		# Simulate DB returning month 3 (March) data
		mock_db_rows = [
			frappe._dict({
				"month_num": 3,
				"total_submitted": 8,
				"valid_count": 5,
				"invalid_count": 1,
				"pending_count": 2,
				"exempt_count": 0,
				"total_value": 36000.0,
			}),
		]
		filters = frappe._dict({"year": "2020"})
		with patch("frappe.db.sql", return_value=mock_db_rows):
			rows = get_data(filters)

		# March is index 2 (0-based)
		march = rows[2]
		self.assertEqual(march["month"], "March")
		self.assertEqual(march["total_submitted"], 8)
		self.assertEqual(march["valid_count"], 5)
		self.assertEqual(march["invalid_count"], 1)
		self.assertEqual(march["pending_count"], 2)
		self.assertEqual(march["exempt_count"], 0)
		self.assertAlmostEqual(march["total_value"], 36000.0)

	def test_other_months_remain_zero_when_only_one_has_data(self):
		"""Months without DB rows must still appear with zero counts."""
		mock_db_rows = [
			frappe._dict({
				"month_num": 6,
				"total_submitted": 3,
				"valid_count": 3,
				"invalid_count": 0,
				"pending_count": 0,
				"exempt_count": 0,
				"total_value": 15000.0,
			}),
		]
		filters = frappe._dict({"year": "2020"})
		with patch("frappe.db.sql", return_value=mock_db_rows):
			rows = get_data(filters)

		# January (index 0) must be zero
		january = rows[0]
		self.assertEqual(january["total_submitted"], 0)
		self.assertAlmostEqual(january["total_value"], 0.0)


class TestMonthlySummaryDeadlineStatus(FrappeTestCase):
	"""Tests for the 7-calendar-day deadline status logic.

	Uses a known past year (2020) to guarantee deadlines have passed,
	and a known far future year (2099) to guarantee deadlines are upcoming.
	"""

	def test_past_month_no_pending_is_on_time(self):
		"""Months in the past with 0 pending docs must show 'On Time'."""
		# January 2020 deadline was 2020-02-07 — well in the past
		mock_db_rows = [
			frappe._dict({
				"month_num": 1,
				"total_submitted": 5,
				"valid_count": 5,
				"invalid_count": 0,
				"pending_count": 0,
				"exempt_count": 0,
				"total_value": 25000.0,
			}),
		]
		filters = frappe._dict({"year": "2020"})
		with patch("frappe.db.sql", return_value=mock_db_rows):
			rows = get_data(filters)

		self.assertEqual(rows[0]["deadline_status"], "On Time")

	def test_past_month_with_pending_is_late(self):
		"""Months in the past with pending docs must show 'Late'."""
		mock_db_rows = [
			frappe._dict({
				"month_num": 1,
				"total_submitted": 5,
				"valid_count": 3,
				"invalid_count": 0,
				"pending_count": 2,
				"exempt_count": 0,
				"total_value": 25000.0,
			}),
		]
		filters = frappe._dict({"year": "2020"})
		with patch("frappe.db.sql", return_value=mock_db_rows):
			rows = get_data(filters)

		self.assertEqual(rows[0]["deadline_status"], "Late")

	def test_future_month_is_pending(self):
		"""Months with future deadlines must always show 'Pending'."""
		# December 2099 deadline is 2100-01-07 — far in the future
		mock_db_rows = [
			frappe._dict({
				"month_num": 12,
				"total_submitted": 10,
				"valid_count": 10,
				"invalid_count": 0,
				"pending_count": 0,
				"exempt_count": 0,
				"total_value": 50000.0,
			}),
		]
		filters = frappe._dict({"year": "2099"})
		with patch("frappe.db.sql", return_value=mock_db_rows):
			rows = get_data(filters)

		# All months in 2099 should be "Pending"
		for row in rows:
			self.assertEqual(row["deadline_status"], "Pending",
				f"{row['month']} 2099 should be Pending but got {row['deadline_status']}")
