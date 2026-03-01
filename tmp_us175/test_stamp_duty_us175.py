"""Tests for US-175: Employment Contract Stamp Duty Compliance Tracker.

Tracks employment contracts requiring stamping via e-Duti Setem (MyTax)
under the Stamp Duty SAS mandatory from 1 January 2026.

Data stored in 'LHDN Employment Contract Stamp Duty' DocType (linked to Employee).

Tests cover:
- Statutory constants
- Exemption logic (salary <= RM3,000/month)
- Overdue detection (30-day window)
- Late penalty calculation
- Auto-set exempt flag
- get_contracts_pending_stamping query (mocked frappe.get_all)
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service import (
    EXEMPTION_THRESHOLD,
    STAMP_DUTY_AMOUNT,
    STAMPING_DEADLINE_DAYS,
    SAS_EFFECTIVE_DATE,
    calculate_late_penalty,
    get_days_since_signing,
    is_stamp_duty_exempt,
    is_stamping_overdue,
    set_stamp_duty_exempt_flag,
    get_contracts_pending_stamping,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestStampDutyConstants(FrappeTestCase):
    """Verify statutory constants match Malaysian law."""

    def test_stamp_duty_amount(self):
        """Fixed stamp duty RM10 per contract (Item 4, First Schedule, Stamp Act 1949)."""
        self.assertEqual(STAMP_DUTY_AMOUNT, 10.0)

    def test_exemption_threshold(self):
        """Exemption threshold RM3,000/month from Finance Bill 2025."""
        self.assertEqual(EXEMPTION_THRESHOLD, 3000.0)

    def test_stamping_deadline_days(self):
        """Contracts must be stamped within 30 days of signing."""
        self.assertEqual(STAMPING_DEADLINE_DAYS, 30)

    def test_sas_effective_date(self):
        """e-Duti Setem SAS mandatory from 1 January 2026."""
        self.assertEqual(SAS_EFFECTIVE_DATE, "2026-01-01")


# ---------------------------------------------------------------------------
# Exemption Logic
# ---------------------------------------------------------------------------

class TestIsStampDutyExempt(FrappeTestCase):
    """Test exemption boundary at RM3,000/month."""

    def test_salary_below_threshold_is_exempt(self):
        self.assertTrue(is_stamp_duty_exempt(2999))

    def test_salary_exactly_at_threshold_is_exempt(self):
        """Boundary is inclusive — RM3,000 exactly is exempt."""
        self.assertTrue(is_stamp_duty_exempt(3000.0))

    def test_salary_above_threshold_not_exempt(self):
        self.assertFalse(is_stamp_duty_exempt(3001))

    def test_zero_salary_is_exempt(self):
        self.assertTrue(is_stamp_duty_exempt(0))

    def test_none_salary_is_exempt(self):
        """None treated as 0 — exempt."""
        self.assertTrue(is_stamp_duty_exempt(None))

    def test_high_salary_not_exempt(self):
        self.assertFalse(is_stamp_duty_exempt(15000))


# ---------------------------------------------------------------------------
# Days Since Signing
# ---------------------------------------------------------------------------

class TestGetDaysSinceSigning(FrappeTestCase):
    """Test days elapsed calculation."""

    def test_none_contract_date_returns_zero(self):
        self.assertEqual(get_days_since_signing(None), 0)

    def test_today_returns_zero(self):
        from frappe.utils import today
        result = get_days_since_signing(today())
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 1)

    def test_past_date_returns_positive(self):
        from frappe.utils import add_days, today
        past = add_days(today(), -45)
        self.assertEqual(get_days_since_signing(past), 45)

    def test_future_date_returns_zero(self):
        from frappe.utils import add_days, today
        future = add_days(today(), 10)
        self.assertEqual(get_days_since_signing(future), 0)


# ---------------------------------------------------------------------------
# Overdue Detection
# ---------------------------------------------------------------------------

class TestIsStampingOverdue(FrappeTestCase):
    """Test 30-day overdue logic."""

    def _date(self, days_ago):
        from frappe.utils import add_days, today
        return add_days(today(), -days_ago)

    def test_no_contract_date_not_overdue(self):
        self.assertFalse(is_stamping_overdue(None))

    def test_within_30_days_not_overdue(self):
        self.assertFalse(is_stamping_overdue(self._date(20)))

    def test_exactly_30_days_not_overdue(self):
        self.assertFalse(is_stamping_overdue(self._date(30)))

    def test_31_days_is_overdue(self):
        self.assertTrue(is_stamping_overdue(self._date(31)))

    def test_stamped_by_reference_not_overdue(self):
        """Contract with stamp reference is never overdue."""
        self.assertFalse(
            is_stamping_overdue(self._date(60), stamp_reference="SD2026-00123")
        )

    def test_stamped_by_date_not_overdue(self):
        """Contract with stamping_date is never overdue."""
        self.assertFalse(
            is_stamping_overdue(self._date(60), stamping_date=self._date(5))
        )

    def test_old_contract_no_stamp_is_overdue(self):
        """90-day-old contract with no stamp is overdue."""
        self.assertTrue(is_stamping_overdue(self._date(90)))


# ---------------------------------------------------------------------------
# Late Penalty Calculation
# ---------------------------------------------------------------------------

class TestCalculateLatePenalty(FrappeTestCase):
    """Test LHDN penalty schedule."""

    def test_zero_days_late_no_penalty(self):
        self.assertEqual(calculate_late_penalty(0), 0.0)

    def test_negative_days_no_penalty(self):
        self.assertEqual(calculate_late_penalty(-5), 0.0)

    def test_bracket1_low_end_31_days(self):
        """31 days late: max(RM50, 10% of RM10=RM1) = RM50."""
        self.assertEqual(calculate_late_penalty(31), 50.0)

    def test_bracket1_high_end_90_days(self):
        """90 days late: still bracket 1, RM50."""
        self.assertEqual(calculate_late_penalty(90), 50.0)

    def test_bracket2_starts_at_91_days(self):
        """91 days late: max(RM100, 20% of RM10=RM2) = RM100."""
        self.assertEqual(calculate_late_penalty(91), 100.0)

    def test_bracket2_long_delay(self):
        """365 days late: penalty capped at RM100."""
        self.assertEqual(calculate_late_penalty(365), 100.0)


# ---------------------------------------------------------------------------
# Auto-set Exempt Flag (on Employee-like object)
# ---------------------------------------------------------------------------

class TestSetStampDutyExemptFlag(FrappeTestCase):
    """Test set_stamp_duty_exempt_flag on Employee-like doc."""

    def _make_emp(self, salary):
        emp = MagicMock()
        emp.custom_gross_salary_at_signing = salary
        emp.get = lambda k, default=None: salary if k == "custom_gross_salary_at_signing" else default
        return emp

    def test_exempt_flag_set_for_low_salary(self):
        emp = self._make_emp(2500)
        set_stamp_duty_exempt_flag(emp)
        self.assertEqual(emp.custom_stamp_duty_exempt, 1)

    def test_exempt_flag_set_at_threshold(self):
        emp = self._make_emp(3000)
        set_stamp_duty_exempt_flag(emp)
        self.assertEqual(emp.custom_stamp_duty_exempt, 1)

    def test_exempt_flag_cleared_above_threshold(self):
        emp = self._make_emp(5000)
        set_stamp_duty_exempt_flag(emp)
        self.assertEqual(emp.custom_stamp_duty_exempt, 0)

    def test_exempt_flag_for_zero_salary(self):
        emp = self._make_emp(0)
        set_stamp_duty_exempt_flag(emp)
        self.assertEqual(emp.custom_stamp_duty_exempt, 1)

    def test_exempt_flag_none_salary(self):
        emp = self._make_emp(None)
        set_stamp_duty_exempt_flag(emp)
        self.assertEqual(emp.custom_stamp_duty_exempt, 1)


# ---------------------------------------------------------------------------
# get_contracts_pending_stamping (mocked frappe.get_all)
# ---------------------------------------------------------------------------

class TestGetContractsPendingStamping(FrappeTestCase):
    """Test the query helper with mocked frappe.get_all."""

    def _make_record(self, name, emp_name, contract_days_ago, salary):
        from frappe.utils import add_days, today
        return {
            "name": name,
            "employee": name,
            "employee_name": emp_name,
            "company": "Test Co",
            "contract_signing_date": add_days(today(), -contract_days_ago),
            "gross_salary_at_signing": salary,
            "stamp_duty_exempt": 0,
            "eduti_setem_reference": "",
            "contract_stamping_date": None,
        }

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe.get_all"
    )
    def test_overdue_contract_in_results(self, mock_get_all):
        """Contract signed 45 days ago with no stamp — 15 days overdue."""
        mock_get_all.return_value = [
            self._make_record("EMP-001", "Ahmad", 45, 5000),
        ]
        results = get_contracts_pending_stamping()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_overdue"])
        self.assertEqual(results[0]["days_overdue"], 15)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe.get_all"
    )
    def test_within_window_not_overdue(self, mock_get_all):
        """Contract signed 10 days ago — within 30-day window, not overdue."""
        mock_get_all.return_value = [
            self._make_record("EMP-002", "Siti", 10, 5000),
        ]
        results = get_contracts_pending_stamping()
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["is_overdue"])

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe.get_all"
    )
    def test_empty_list_returns_empty(self, mock_get_all):
        mock_get_all.return_value = []
        results = get_contracts_pending_stamping()
        self.assertEqual(results, [])

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe.get_all"
    )
    def test_results_sorted_by_days_overdue_descending(self, mock_get_all):
        """Most overdue contracts appear first."""
        mock_get_all.return_value = [
            self._make_record("EMP-001", "Ahmad", 45, 5000),
            self._make_record("EMP-002", "Siti", 90, 6000),
        ]
        results = get_contracts_pending_stamping()
        self.assertGreater(results[0]["days_overdue"], results[1]["days_overdue"])

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe.get_all"
    )
    def test_company_filter_passed_to_frappe(self, mock_get_all):
        """Company filter is forwarded to frappe.get_all."""
        mock_get_all.return_value = []
        get_contracts_pending_stamping(company="ACME Sdn Bhd")
        call_filters = mock_get_all.call_args[1]["filters"]
        self.assertIn("company", call_filters)
        self.assertEqual(call_filters["company"], "ACME Sdn Bhd")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe.get_all"
    )
    def test_penalty_calculated_for_overdue(self, mock_get_all):
        """Overdue contract has penalty estimated."""
        mock_get_all.return_value = [
            self._make_record("EMP-001", "Ahmad", 65, 5000),
        ]
        results = get_contracts_pending_stamping()
        # 65 days elapsed, 35 days overdue → bracket 1 → RM50
        self.assertEqual(results[0]["penalty_est"], 50.0)
