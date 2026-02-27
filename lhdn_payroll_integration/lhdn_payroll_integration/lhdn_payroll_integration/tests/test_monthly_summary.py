"""Tests for LHDN Monthly Summary Script Report (US-027).

Verifies monthly aggregation accuracy: 12 rows always returned,
correct month names, correct status counts, and Deadline Status logic.
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


class TestMonthlySummaryColumns(FrappeTestCase):
	"""Tests for get_columns()."""

	def test_get_columns_returns_list(self):
		"""get_columns() must return a list."""
		self.assertIsInstance(get_columns(), list)

	def test_get_columns_minimum_count(self):
		"""get_columns() must return at least 8 columns."""
		self.assertGreaterEqual(len(get_columns()), 8)

	def test_get_columns_required_fieldnames(self):
		"""get_columns() must include all required fieldnames."""
		fieldnames = {c.get("fieldname") for c in get_columns() if isinstance(c, dict)}
		for req in REQUIRED_FIELDNAMES:
			self.assertIn(req, fieldnames, f"Missing column: {req}")


class TestMonthlySummaryDataShape(FrappeTestCase):
	"""Tests for basic data shape returned by get_data()."""

	def test_always_returns_12_rows(self):
		"""Report must return exactly 12 rows even with no DB records."""
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(frappe._dict({"year": "2025"}))
		self.assertEqual(len(rows), 12)

	def test_month_names_correct_order(self):
		"""Each row must contain the correct calendar month name in order."""
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(frappe._dict({"year": "2025"}))
		for i, row in enumerate(rows):
			self.assertEqual(row["month"], MONTH_NAMES[i], f"Wrong month at index {i}")

	def test_rows_have_all_required_keys(self):
		"""Every row must contain all required keys."""
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(frappe._dict({"year": "2025"}))
		for row in rows:
			for key in REQUIRED_FIELDNAMES:
				self.assertIn(key, row, f"Row missing key: {key}")

	def test_empty_months_have_zero_counts(self):
		"""Months with no DB records must have zero counts and 0.0 total value."""
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(frappe._dict({"year": "2025"}))
		for row in rows:
			self.assertEqual(row["total_submitted"], 0)
			self.assertEqual(row["valid_count"], 0)
			self.assertEqual(row["invalid_count"], 0)
			self.assertEqual(row["pending_count"], 0)
			self.assertEqual(row["exempt_count"], 0)
			self.assertEqual(row["total_value"], 0.0)

	def test_execute_returns_columns_and_data(self):
		"""execute() must return a (columns, data) tuple."""
		from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_monthly_summary.lhdn_monthly_summary import execute
		with patch("frappe.db.sql", return_value=[]):
			result = execute(frappe._dict({"year": "2025"}))
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 2)
		cols, data = result
		self.assertIsInstance(cols, list)
		self.assertIsInstance(data, list)


class TestMonthlySummaryAggregation(FrappeTestCase):
	"""Tests verifying monthly aggregation accuracy."""

	def _make_db_row(self, month_num, total, valid, invalid, pending, exempt, value):
		return frappe._dict({
			"month_num": month_num,
			"total_submitted": total,
			"valid_count": valid,
			"invalid_count": invalid,
			"pending_count": pending,
			"exempt_count": exempt,
			"total_value": value,
		})

	def test_aggregates_january_counts_correctly(self):
		"""January row must reflect correct counts from DB result."""
		mock_rows = [self._make_db_row(1, 5, 3, 1, 1, 0, 25000.00)]
		with patch("frappe.db.sql", return_value=mock_rows):
			rows = get_data(frappe._dict({"year": "2025"}))
		jan = rows[0]
		self.assertEqual(jan["total_submitted"], 5)
		self.assertEqual(jan["valid_count"], 3)
		self.assertEqual(jan["invalid_count"], 1)
		self.assertEqual(jan["pending_count"], 1)
		self.assertEqual(jan["exempt_count"], 0)
		self.assertAlmostEqual(jan["total_value"], 25000.00)

	def test_missing_month_remains_zero(self):
		"""A month absent from DB rows must appear with zero counts."""
		mock_rows = [self._make_db_row(3, 2, 2, 0, 0, 0, 8000.00)]
		with patch("frappe.db.sql", return_value=mock_rows):
			rows = get_data(frappe._dict({"year": "2025"}))
		# February (index 1) was not in DB rows
		feb = rows[1]
		self.assertEqual(feb["total_submitted"], 0)
		self.assertEqual(feb["total_value"], 0.0)

	def test_multiple_months_aggregated(self):
		"""Multiple months from DB must each map to correct row."""
		mock_rows = [
			self._make_db_row(1, 5, 3, 1, 1, 0, 25000.00),
			self._make_db_row(6, 10, 8, 0, 2, 0, 50000.00),
			self._make_db_row(12, 3, 3, 0, 0, 0, 12000.00),
		]
		with patch("frappe.db.sql", return_value=mock_rows):
			rows = get_data(frappe._dict({"year": "2025"}))

		self.assertEqual(rows[0]["total_submitted"], 5)   # January
		self.assertEqual(rows[5]["total_submitted"], 10)  # June
		self.assertEqual(rows[11]["total_submitted"], 3)  # December

	def test_exempt_count_tracked(self):
		"""Exempt count must be returned separately from other statuses."""
		mock_rows = [self._make_db_row(4, 4, 2, 0, 1, 1, 10000.00)]
		with patch("frappe.db.sql", return_value=mock_rows):
			rows = get_data(frappe._dict({"year": "2025"}))
		apr = rows[3]
		self.assertEqual(apr["exempt_count"], 1)


class TestMonthlySummaryDeadlineStatus(FrappeTestCase):
	"""Tests for Deadline Status column using the 7-day rule."""

	def test_pending_for_future_year_all_months(self):
		"""All months in a future year must show 'Pending' deadline status."""
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(frappe._dict({"year": "2035"}))
		for row in rows:
			self.assertEqual(
				row["deadline_status"], "Pending",
				f"Expected Pending for future month, got: {row['deadline_status']} ({row['month']})",
			)

	def test_on_time_past_deadline_no_pending(self):
		"""Past month with zero pending docs and past deadline must show 'On Time'."""
		mock_rows = [frappe._dict({
			"month_num": 1,
			"total_submitted": 3,
			"valid_count": 3,
			"invalid_count": 0,
			"pending_count": 0,
			"exempt_count": 0,
			"total_value": 15000.00,
		})]
		with patch("frappe.db.sql", return_value=mock_rows):
			rows = get_data(frappe._dict({"year": "2020"}))
		jan = rows[0]
		self.assertEqual(jan["deadline_status"], "On Time")

	def test_late_past_deadline_with_pending(self):
		"""Past month with pending docs and past deadline must show 'Late'."""
		mock_rows = [frappe._dict({
			"month_num": 1,
			"total_submitted": 3,
			"valid_count": 2,
			"invalid_count": 0,
			"pending_count": 1,
			"exempt_count": 0,
			"total_value": 15000.00,
		})]
		with patch("frappe.db.sql", return_value=mock_rows):
			rows = get_data(frappe._dict({"year": "2020"}))
		jan = rows[0]
		self.assertEqual(jan["deadline_status"], "Late")

	def test_deadline_status_values_limited_to_valid_set(self):
		"""All deadline_status values must be one of: Pending, On Time, Late."""
		valid_statuses = {"Pending", "On Time", "Late"}
		with patch("frappe.db.sql", return_value=[]):
			rows = get_data(frappe._dict({"year": "2025"}))
		for row in rows:
			self.assertIn(
				row["deadline_status"], valid_statuses,
				f"Unexpected deadline_status: {row['deadline_status']}",
			)
