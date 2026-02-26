"""Tests for mandatory e-invoice date gating by company revenue tier — TDD red phase (UT-028).

Tests verify that:
- Revenue tiers have correct mandatory start dates
- Production mode before mandatory date logs a warning
- Sandbox mode bypasses mandatory date check
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
from datetime import date

from lhdn_payroll_integration.utils.config import get_mandatory_date, check_mandatory_compliance


class TestMandatoryDateGating(FrappeTestCase):
	"""Test suite for mandatory e-invoice date gating by company revenue tier."""

	def test_revenue_above_100m_mandatory_from_aug_2024(self):
		"""Companies with annual revenue > RM 100M: mandatory from 1 Aug 2024."""
		result = get_mandatory_date(150_000_000)
		self.assertEqual(result, date(2024, 8, 1),
			f"Revenue > 100M: mandatory date must be 2024-08-01, got {result}")

	def test_revenue_25m_to_100m_mandatory_from_jan_2025(self):
		"""Companies with revenue RM 25M to RM 100M: mandatory from 1 Jan 2025."""
		result = get_mandatory_date(50_000_000)
		self.assertEqual(result, date(2025, 1, 1),
			f"Revenue 25M-100M: mandatory date must be 2025-01-01, got {result}")

	def test_revenue_5m_to_25m_mandatory_from_jul_2025(self):
		"""Companies with revenue RM 5M to RM 25M: mandatory from 1 Jul 2025."""
		result = get_mandatory_date(10_000_000)
		self.assertEqual(result, date(2025, 7, 1),
			f"Revenue 5M-25M: mandatory date must be 2025-07-01, got {result}")

	def test_revenue_1m_to_5m_mandatory_from_jan_2026(self):
		"""Companies with revenue RM 1M to RM 5M: mandatory from 1 Jan 2026."""
		result = get_mandatory_date(3_000_000)
		self.assertEqual(result, date(2026, 1, 1),
			f"Revenue 1M-5M: mandatory date must be 2026-01-01, got {result}")

	def test_below_1m_exempt_mandatory_date_is_none(self):
		"""Companies below RM 1M annual revenue: no mandatory date (exempt)."""
		result = get_mandatory_date(500_000)
		self.assertIsNone(result,
			f"Revenue < 1M: mandatory date must be None (exempt), got {result}")

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_production_before_mandatory_date_logs_warning(self, mock_frappe):
		"""In production mode, submitting before mandatory date must log a warning."""
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_environment": "production",
		}.get(key, default)
		mock_frappe.utils.today.return_value = "2024-06-01"

		check_mandatory_compliance(150_000_000)

		mock_frappe.log_error.assert_called()

	@patch("lhdn_payroll_integration.utils.config.frappe")
	def test_sandbox_mode_bypasses_mandatory_date_check(self, mock_frappe):
		"""In sandbox mode, mandatory date check must be bypassed entirely."""
		mock_frappe.conf.get.side_effect = lambda key, default=None: {
			"lhdn_environment": "sandbox",
		}.get(key, default)

		# Should not raise even with future mandatory date
		try:
			check_mandatory_compliance(500_000)
		except Exception as e:
			self.fail(f"Sandbox mode should bypass mandatory check, got: {e}")
