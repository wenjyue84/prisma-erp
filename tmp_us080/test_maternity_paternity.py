"""Tests for US-080: Track Maternity/Paternity Leave and Validate Maternity Pay Rate.

Employment Act 1955:
  - Section 37 (A1651): 98 consecutive days maternity leave; allowance >= ORP * days_taken
  - Section 60FA: 7 consecutive days paternity leave; max 5 live births
"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.employment_compliance import (
    MATERNITY_LEAVE_DAYS,
    MAX_PATERNITY_BIRTHS,
    PATERNITY_LEAVE_DAYS,
    validate_maternity_pay,
    validate_paternity_claims,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestMaternityPaternityConstants(FrappeTestCase):
    """Verify statutory constants match Employment Act 1955."""

    def test_maternity_leave_days_is_98(self):
        self.assertEqual(MATERNITY_LEAVE_DAYS, 98)

    def test_paternity_leave_days_is_7(self):
        self.assertEqual(PATERNITY_LEAVE_DAYS, 7)

    def test_max_paternity_births_is_5(self):
        self.assertEqual(MAX_PATERNITY_BIRTHS, 5)


# ---------------------------------------------------------------------------
# validate_maternity_pay()
# ---------------------------------------------------------------------------


def _make_salary_slip(base, days_taken, maternity_amount):
    """Build a minimal mock Salary Slip."""
    slip = MagicMock()
    slip.employee = "EMP-TEST-001"
    slip.base = base
    # One maternity earnings row
    row = MagicMock()
    row.salary_component = "Maternity Allowance"
    row.amount = maternity_amount
    slip.earnings = [row]
    return slip, days_taken


class TestValidateMaternityPayCompliant(FrappeTestCase):
    """Compliant scenarios: correct payment, within day limits."""

    def _run(self, base, days_taken, maternity_amount):
        slip, days = _make_salary_slip(base, days_taken, maternity_amount)
        with patch(
            "lhdn_payroll_integration.utils.employment_compliance.frappe.get_doc"
        ) as mock_get_doc:
            emp = MagicMock()
            emp.get = MagicMock(
                side_effect=lambda key, default=None: days if key == "custom_maternity_leave_taken" else default
            )
            mock_get_doc.return_value = emp
            return validate_maternity_pay(slip)

    def test_exact_minimum_pay_passes(self):
        # ORP daily = 3000 / 26 = 115.38; 30 days => minimum = 3461.54
        base = 3000.0
        days = 30
        orp_daily = base / 26.0
        minimum = orp_daily * days
        result = self._run(base, days, minimum)
        self.assertTrue(result["compliant"])
        self.assertEqual(result["warnings"], [])

    def test_above_minimum_pay_passes(self):
        base = 4000.0
        days = 20
        orp_daily = base / 26.0
        minimum = orp_daily * days
        result = self._run(base, days, minimum + 100)
        self.assertTrue(result["compliant"])
        self.assertEqual(result["warnings"], [])

    def test_exactly_98_days_passes(self):
        # Exactly at statutory limit — still compliant (not over)
        base = 2000.0
        orp_daily = base / 26.0
        minimum = orp_daily * MATERNITY_LEAVE_DAYS
        result = self._run(base, MATERNITY_LEAVE_DAYS, minimum)
        self.assertTrue(result["compliant"])
        self.assertEqual(result["warnings"], [])

    def test_zero_days_no_warning(self):
        # No maternity leave taken — nothing to validate
        result = self._run(3000.0, 0, 0.0)
        self.assertTrue(result["compliant"])
        self.assertEqual(result["warnings"], [])


class TestValidateMaternityPayNonCompliant(FrappeTestCase):
    """Non-compliant scenarios: underpayment and over-entitlement."""

    def _run(self, base, days_taken, maternity_amount):
        slip, days = _make_salary_slip(base, days_taken, maternity_amount)
        with patch(
            "lhdn_payroll_integration.utils.employment_compliance.frappe.get_doc"
        ) as mock_get_doc:
            emp = MagicMock()
            emp.get = MagicMock(
                side_effect=lambda key, default=None: days if key == "custom_maternity_leave_taken" else default
            )
            mock_get_doc.return_value = emp
            return validate_maternity_pay(slip)

    def test_pay_below_orp_triggers_warning(self):
        base = 3000.0
        days = 30
        orp_daily = base / 26.0
        minimum = orp_daily * days
        # Pay below minimum
        result = self._run(base, days, minimum - 1)
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("below the statutory minimum", result["warnings"][0])

    def test_days_over_98_triggers_warning(self):
        base = 3000.0
        orp_daily = base / 26.0
        minimum = orp_daily * 99
        result = self._run(base, 99, minimum)
        self.assertFalse(result["compliant"])
        self.assertTrue(any("98" in w for w in result["warnings"]))
        self.assertTrue(any("99" in w for w in result["warnings"]))

    def test_days_over_98_and_underpayment_two_warnings(self):
        base = 2000.0
        # Over days AND underpaid
        result = self._run(base, 100, 1.0)
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_warning_mentions_section_37(self):
        base = 3000.0
        days = 30
        orp_daily = base / 26.0
        minimum = orp_daily * days
        result = self._run(base, days, minimum - 1)
        self.assertTrue(any("S.37" in w for w in result["warnings"]))

    def test_result_contains_orp_daily(self):
        base = 2600.0
        result = self._run(base, 10, 500.0)
        self.assertAlmostEqual(result["orp_daily"], 2600 / 26, places=2)

    def test_result_contains_minimum_pay(self):
        base = 2600.0
        days = 10
        result = self._run(base, days, 500.0)
        expected_min = (2600 / 26) * days
        self.assertAlmostEqual(result["minimum_pay"], expected_min, places=2)

    def test_result_contains_maternity_pay(self):
        base = 3000.0
        result = self._run(base, 10, 999.99)
        self.assertAlmostEqual(result["maternity_pay"], 999.99, places=2)


class TestValidateMaternityPayEdgeCases(FrappeTestCase):
    """Edge cases: zero base, missing earnings, multiple components."""

    def _run(self, slip, days_taken):
        with patch(
            "lhdn_payroll_integration.utils.employment_compliance.frappe.get_doc"
        ) as mock_get_doc:
            emp = MagicMock()
            emp.get = MagicMock(
                side_effect=lambda key, default=None: days_taken if key == "custom_maternity_leave_taken" else default
            )
            mock_get_doc.return_value = emp
            return validate_maternity_pay(slip)

    def test_zero_base_no_minimum_pay(self):
        slip = MagicMock()
        slip.employee = "EMP-001"
        slip.base = 0
        slip.earnings = []
        result = self._run(slip, 30)
        # orp_daily = 0, so minimum_pay is None (cannot validate)
        self.assertIsNone(result["minimum_pay"])

    def test_multiple_maternity_components_summed(self):
        slip = MagicMock()
        slip.employee = "EMP-001"
        slip.base = 2600.0
        row1 = MagicMock()
        row1.salary_component = "Maternity Allowance"
        row1.amount = 500.0
        row2 = MagicMock()
        row2.salary_component = "Maternity Bonus"
        row2.amount = 200.0
        slip.earnings = [row1, row2]
        result = self._run(slip, 10)
        self.assertAlmostEqual(result["maternity_pay"], 700.0, places=2)

    def test_non_maternity_components_excluded(self):
        slip = MagicMock()
        slip.employee = "EMP-001"
        slip.base = 2600.0
        row1 = MagicMock()
        row1.salary_component = "Basic Salary"
        row1.amount = 2600.0
        row2 = MagicMock()
        row2.salary_component = "Maternity Allowance"
        row2.amount = 300.0
        slip.earnings = [row1, row2]
        result = self._run(slip, 5)
        self.assertAlmostEqual(result["maternity_pay"], 300.0, places=2)


# ---------------------------------------------------------------------------
# validate_paternity_claims()
# ---------------------------------------------------------------------------


def _make_employee_doc(births_claimed, days_taken):
    emp = MagicMock()
    emp.get = MagicMock(
        side_effect=lambda key, default=None: {
            "custom_paternity_births_claimed": births_claimed,
            "custom_paternity_leave_taken": days_taken,
        }.get(key, default)
    )
    return emp


class TestValidatePaternityClaimsCompliant(FrappeTestCase):
    """Compliant paternity scenarios."""

    def test_five_births_seven_days_passes(self):
        emp = _make_employee_doc(5, 7)
        result = validate_paternity_claims(emp)
        self.assertTrue(result["compliant"])
        self.assertEqual(result["warnings"], [])

    def test_zero_births_zero_days_passes(self):
        emp = _make_employee_doc(0, 0)
        result = validate_paternity_claims(emp)
        self.assertTrue(result["compliant"])

    def test_one_birth_three_days_passes(self):
        emp = _make_employee_doc(1, 3)
        result = validate_paternity_claims(emp)
        self.assertTrue(result["compliant"])

    def test_five_births_exactly_passes(self):
        emp = _make_employee_doc(MAX_PATERNITY_BIRTHS, 7)
        result = validate_paternity_claims(emp)
        self.assertTrue(result["compliant"])


class TestValidatePaternityClaimsNonCompliant(FrappeTestCase):
    """Non-compliant paternity scenarios."""

    def test_six_births_triggers_warning(self):
        emp = _make_employee_doc(6, 7)
        result = validate_paternity_claims(emp)
        self.assertFalse(result["compliant"])
        self.assertTrue(any("6" in w for w in result["warnings"]))
        self.assertTrue(any("5" in w for w in result["warnings"]))

    def test_eight_days_triggers_warning(self):
        emp = _make_employee_doc(1, 8)
        result = validate_paternity_claims(emp)
        self.assertFalse(result["compliant"])
        self.assertTrue(any("8" in w for w in result["warnings"]))
        self.assertTrue(any("7" in w for w in result["warnings"]))

    def test_over_births_and_over_days_two_warnings(self):
        emp = _make_employee_doc(10, 10)
        result = validate_paternity_claims(emp)
        self.assertFalse(result["compliant"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_warning_mentions_section_60fa(self):
        emp = _make_employee_doc(6, 0)
        result = validate_paternity_claims(emp)
        self.assertTrue(any("60FA" in w for w in result["warnings"]))

    def test_result_contains_births_claimed(self):
        emp = _make_employee_doc(6, 7)
        result = validate_paternity_claims(emp)
        self.assertEqual(result["births_claimed"], 6)

    def test_result_contains_days_taken(self):
        emp = _make_employee_doc(1, 8)
        result = validate_paternity_claims(emp)
        self.assertEqual(result["days_taken"], 8)
