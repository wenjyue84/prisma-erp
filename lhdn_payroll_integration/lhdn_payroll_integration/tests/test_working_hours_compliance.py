"""Tests for validate_weekly_hours() — Employment Act S.60A(1) 45-hour weekly limit.

US-081: Working Hours Compliance Check (45-Hour Weekly Limit)

Employment Act 1955 Section 60A(1) post-2022 amendment: maximum 45 hours per week.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch

from lhdn_payroll_integration.lhdn_payroll_integration.utils.employment_compliance import (
    validate_weekly_hours,
    MAX_WEEKLY_HOURS,
    WEEKS_PER_MONTH,
)


def _make_slip(contracted_weekly=45.0, ot_hours=0.0, ot_day_type="Normal"):
    """Build a minimal mock Salary Slip with the given contracted hours and OT."""
    slip = MagicMock()
    slip.employee = None  # no Employee DB lookup needed

    if ot_hours > 0:
        row = MagicMock()
        row.custom_day_type = ot_day_type
        row.qty = ot_hours
        slip.earnings = [row]
    else:
        slip.earnings = []

    # Patch frappe.get_doc to return an employee with the given contracted hours
    # (will be overridden per-test when needed)
    return slip


class TestMaxWeeklyHoursConstant(FrappeTestCase):
    """Verify the statutory constant is correct."""

    def test_max_weekly_hours_value(self):
        """MAX_WEEKLY_HOURS must be 45 (EA S.60A(1) post-2022 amendment)."""
        self.assertEqual(MAX_WEEKLY_HOURS, 45)

    def test_weeks_per_month_value(self):
        """WEEKS_PER_MONTH must be 4.33 (average weeks per calendar month)."""
        self.assertAlmostEqual(WEEKS_PER_MONTH, 4.33)


class TestValidateWeeklyHoursNoOT(FrappeTestCase):
    """Scenarios with no overtime."""

    def test_exactly_45_hours_is_compliant(self):
        """45 contracted hours per week with no OT should be compliant."""
        slip = _make_slip(contracted_weekly=45.0, ot_hours=0)
        with patch("frappe.get_doc") as mock_get_doc:
            emp = MagicMock()
            emp.custom_contracted_weekly_hours = 45.0
            mock_get_doc.return_value = emp
            slip.employee = "EMP-001"
            result = validate_weekly_hours(slip)

        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])
        self.assertAlmostEqual(result["implied_weekly_hours"], 45.0)
        self.assertEqual(result["max_weekly_hours"], 45)

    def test_40_hours_is_compliant(self):
        """40-hour week with no OT is well within limit."""
        slip = _make_slip(ot_hours=0)
        with patch("frappe.get_doc") as mock_get_doc:
            emp = MagicMock()
            emp.custom_contracted_weekly_hours = 40.0
            mock_get_doc.return_value = emp
            slip.employee = "EMP-002"
            result = validate_weekly_hours(slip)

        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])
        self.assertAlmostEqual(result["implied_weekly_hours"], 40.0)

    def test_no_employee_falls_back_to_45_default(self):
        """When no employee ID is set, default contracted hours = 45 (MAX)."""
        slip = _make_slip(ot_hours=0)
        slip.employee = None
        result = validate_weekly_hours(slip)

        self.assertTrue(result["compliant"])
        self.assertAlmostEqual(result["contracted_weekly_hours"], 45.0)


class TestValidateWeeklyHoursWithOT(FrappeTestCase):
    """Scenarios involving overtime entries."""

    def _slip_with_employee_hours(self, contracted_weekly, ot_hours_monthly, day_type="Normal"):
        """Helper: create slip and patch frappe.get_doc."""
        slip = MagicMock()
        slip.employee = "EMP-TEST"

        if ot_hours_monthly > 0:
            row = MagicMock()
            row.custom_day_type = day_type
            row.qty = ot_hours_monthly
            slip.earnings = [row]
        else:
            slip.earnings = []

        emp = MagicMock()
        emp.custom_contracted_weekly_hours = contracted_weekly
        return slip, emp

    def test_46_hour_implied_week_triggers_warning(self):
        """Implied weekly hours of 46 should trigger a non-compliant warning."""
        # OT needed: (46 - 45) * 4.33 = 4.33 hours/month OT
        ot_monthly = 1.0 * WEEKS_PER_MONTH  # exactly 1 extra hour/week = 4.33/month
        slip, emp = self._slip_with_employee_hours(45.0, ot_monthly)
        with patch("frappe.get_doc", return_value=emp):
            result = validate_weekly_hours(slip)

        self.assertFalse(result["compliant"])
        self.assertIsNotNone(result["warning"])
        self.assertIn("45", result["warning"])
        self.assertGreater(result["implied_weekly_hours"], 45.0)

    def test_45_hour_implied_week_passes(self):
        """Exactly 45 implied weekly hours (contracted 40 + OT bringing to 45) should pass."""
        # OT = (45 - 40) * 4.33 = 21.65 hours/month to hit exactly 45/week
        ot_monthly = 5.0 * WEEKS_PER_MONTH
        slip, emp = self._slip_with_employee_hours(40.0, ot_monthly)
        with patch("frappe.get_doc", return_value=emp):
            result = validate_weekly_hours(slip)

        self.assertTrue(result["compliant"])
        self.assertIsNone(result["warning"])
        self.assertAlmostEqual(result["implied_weekly_hours"], 45.0, places=1)

    def test_ot_row_without_custom_day_type_not_counted(self):
        """Earnings rows without custom_day_type should not count as OT hours."""
        slip = MagicMock()
        slip.employee = None

        row = MagicMock()
        row.custom_day_type = ""  # empty = not OT
        row.qty = 100.0  # large value — should be ignored
        slip.earnings = [row]

        result = validate_weekly_hours(slip)
        self.assertAlmostEqual(result["ot_hours_monthly"], 0.0)
        self.assertTrue(result["compliant"])  # 45 contracted + 0 OT = 45

    def test_multiple_ot_rows_summed(self):
        """Multiple OT rows with custom_day_type should all be summed."""
        slip = MagicMock()
        slip.employee = None

        # Two OT rows: 1h normal + 2h rest day = 3h OT/month
        row1 = MagicMock()
        row1.custom_day_type = "Normal"
        row1.qty = 1.0

        row2 = MagicMock()
        row2.custom_day_type = "Rest Day"
        row2.qty = 2.0

        # Regular row (no day type)
        row3 = MagicMock()
        row3.custom_day_type = ""
        row3.qty = 50.0  # should be ignored

        slip.earnings = [row1, row2, row3]

        result = validate_weekly_hours(slip)
        self.assertAlmostEqual(result["ot_hours_monthly"], 3.0)

    def test_return_dict_has_all_keys(self):
        """validate_weekly_hours always returns all expected keys."""
        slip = _make_slip()
        slip.employee = None
        result = validate_weekly_hours(slip)

        required_keys = {
            "compliant",
            "warning",
            "implied_weekly_hours",
            "max_weekly_hours",
            "contracted_weekly_hours",
            "ot_hours_monthly",
        }
        self.assertEqual(required_keys, set(result.keys()))

    def test_warning_contains_section_reference(self):
        """Non-compliant warning should reference Employment Act S.60A(1)."""
        ot_monthly = 5.0 * WEEKS_PER_MONTH  # 5 extra hours/week → 50h/week total
        slip = MagicMock()
        slip.employee = None
        row = MagicMock()
        row.custom_day_type = "Normal"
        row.qty = ot_monthly
        slip.earnings = [row]

        result = validate_weekly_hours(slip)
        self.assertFalse(result["compliant"])
        self.assertIn("60A", result["warning"])
