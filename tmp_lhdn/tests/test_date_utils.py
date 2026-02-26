"""Tests for LHDN date utilities.

TDD Red Phase — these tests import from lhdn_payroll_integration.utils.date_utils
which does NOT exist yet. All tests should fail with ImportError.
"""

from datetime import date, datetime

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.date_utils import (
    to_lhdn_date,
    to_lhdn_datetime,
)


class TestDateUtils(FrappeTestCase):
    """Test LHDN date formatting utilities."""

    def test_to_lhdn_date_valid_date_object(self):
        """to_lhdn_date with a date object should return YYYY-MM-DD string."""
        result = to_lhdn_date(date(2026, 1, 15))
        self.assertEqual(result, "2026-01-15")

    def test_to_lhdn_date_valid_string(self):
        """to_lhdn_date with a valid YYYY-MM-DD string should return it as-is."""
        result = to_lhdn_date("2026-03-20")
        self.assertEqual(result, "2026-03-20")

    def test_to_lhdn_date_invalid_raises_value_error(self):
        """to_lhdn_date with invalid input ('N/A', empty, garbage) should raise ValueError."""
        with self.assertRaises(ValueError):
            to_lhdn_date("N/A")
        with self.assertRaises(ValueError):
            to_lhdn_date("")
        with self.assertRaises(ValueError):
            to_lhdn_date("not-a-date")

    def test_to_lhdn_datetime_returns_utc_format(self):
        """to_lhdn_datetime should return current UTC time as YYYY-MM-DDTHH:MM:SSZ."""
        result = to_lhdn_datetime()
        # Format: 2026-01-15T12:30:45Z
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
