"""Tests for US-206: Employment Act S.60A Annual Leave Carry-Forward Cap and Cash-Out.

Acceptance criteria:
  AC1: Carry-forward configurable with max days (default 1× annual entitlement, e.g. 22 days)
  AC2: Leave Expiry Notice shows days expiring, cash-out amount, carry-forward option
  AC3: HR Manager records decision (Carry Forward | Cash Out | Mutual Forfeiture Agreement)
  AC4: Cash-out = (Monthly Basic Salary / 26) × days, recorded with HR manager
  AC5: Block year close-off for employees without a recorded leave expiry decision
  AC6: Audit log records decisions with HR manager approval and timestamp

TDD GREEN: bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_us206_annual_leave_expiry
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.leave_expiry_service import (
    EA_LEAVE_TYPE,
    EA_ANNUAL_LEAVE_TIERS,
    CARRY_FORWARD_DEFAULT_MULTIPLIER,
    DECISION_CARRY_FORWARD,
    DECISION_CASH_OUT,
    DECISION_MUTUAL_FORFEITURE,
    VALID_DECISIONS,
    WORKING_DAYS_PER_MONTH,
    EA_LEAVE_EXPIRY_NOTICE_DOCTYPE,
    get_ea_leave_entitlement,
    get_carry_forward_cap,
    calculate_cash_out,
    generate_leave_expiry_notices,
    record_leave_decision,
    validate_year_close_readiness,
)


# ---------------------------------------------------------------------------
# AC1: Statutory constants
# ---------------------------------------------------------------------------

class TestEALeaveConstants(FrappeTestCase):
    """Verify EA statutory constants match Employment Act 1955 S.60A/S.60E."""

    def test_ea_leave_type_name(self):
        self.assertEqual(EA_LEAVE_TYPE, "Annual Leave (EA)")

    def test_working_days_divisor_is_26(self):
        self.assertEqual(WORKING_DAYS_PER_MONTH, 26)

    def test_carry_forward_default_multiplier_is_1(self):
        self.assertEqual(CARRY_FORWARD_DEFAULT_MULTIPLIER, 1)

    def test_annual_leave_tier_under_2_years(self):
        self.assertEqual(EA_ANNUAL_LEAVE_TIERS["< 2 years"], 8)

    def test_annual_leave_tier_2_to_5_years(self):
        self.assertEqual(EA_ANNUAL_LEAVE_TIERS["2-5 years"], 12)

    def test_annual_leave_tier_over_5_years(self):
        self.assertEqual(EA_ANNUAL_LEAVE_TIERS["> 5 years"], 16)

    def test_valid_decisions_contains_carry_forward(self):
        self.assertIn(DECISION_CARRY_FORWARD, VALID_DECISIONS)

    def test_valid_decisions_contains_cash_out(self):
        self.assertIn(DECISION_CASH_OUT, VALID_DECISIONS)

    def test_valid_decisions_contains_mutual_forfeiture(self):
        self.assertIn(DECISION_MUTUAL_FORFEITURE, VALID_DECISIONS)

    def test_doctype_name(self):
        self.assertEqual(EA_LEAVE_EXPIRY_NOTICE_DOCTYPE, "EA Leave Expiry Notice")


# ---------------------------------------------------------------------------
# AC1: Leave entitlement tiers by years of service (EA S.60E)
# ---------------------------------------------------------------------------

class TestGetEALeaveEntitlement(FrappeTestCase):
    """get_ea_leave_entitlement returns correct days per EA S.60E."""

    def test_zero_years_returns_8(self):
        self.assertEqual(get_ea_leave_entitlement(0), 8)

    def test_under_2_years_returns_8(self):
        self.assertEqual(get_ea_leave_entitlement(1), 8)
        self.assertEqual(get_ea_leave_entitlement(1.9), 8)

    def test_exactly_2_years_returns_12(self):
        self.assertEqual(get_ea_leave_entitlement(2), 12)

    def test_between_2_and_5_years_returns_12(self):
        self.assertEqual(get_ea_leave_entitlement(3), 12)
        self.assertEqual(get_ea_leave_entitlement(5), 12)

    def test_over_5_years_returns_16(self):
        self.assertEqual(get_ea_leave_entitlement(5.1), 16)
        self.assertEqual(get_ea_leave_entitlement(10), 16)
        self.assertEqual(get_ea_leave_entitlement(25), 16)


# ---------------------------------------------------------------------------
# AC1: Carry-forward cap is configurable
# ---------------------------------------------------------------------------

class TestGetCarryForwardCap(FrappeTestCase):
    """Carry-forward cap = entitlement × multiplier (default 1×)."""

    def test_default_1x_for_8_day_entitlement(self):
        self.assertEqual(get_carry_forward_cap(8), 8)

    def test_default_1x_for_12_day_entitlement(self):
        self.assertEqual(get_carry_forward_cap(12), 12)

    def test_default_1x_for_16_day_entitlement(self):
        self.assertEqual(get_carry_forward_cap(16), 16)

    def test_custom_multiplier_2x(self):
        self.assertEqual(get_carry_forward_cap(16, multiplier=2), 32)

    def test_higher_employer_entitlement_22_days(self):
        """Employer may grant >statutory minimum (e.g. 22 days); cap stays 1× that."""
        self.assertEqual(get_carry_forward_cap(22), 22)

    def test_zero_entitlement_returns_zero(self):
        self.assertEqual(get_carry_forward_cap(0), 0)


# ---------------------------------------------------------------------------
# AC4: Cash-out formula (Monthly Basic / 26 × days)
# ---------------------------------------------------------------------------

class TestCalculateCashOut(FrappeTestCase):
    """Cash-out = (Monthly Basic / 26) × leave_days."""

    def test_basic_calculation(self):
        # 2600 / 26 = 100 per day × 5 = 500
        self.assertAlmostEqual(calculate_cash_out(2600, 5), 500.0, places=2)

    def test_rounds_to_2_decimal_places(self):
        # 3000 / 26 = 115.3846... × 3 = 346.15
        self.assertAlmostEqual(calculate_cash_out(3000, 3), 346.15, places=2)

    def test_zero_days_returns_zero(self):
        self.assertEqual(calculate_cash_out(5000, 0), 0.0)

    def test_zero_salary_returns_zero(self):
        self.assertEqual(calculate_cash_out(0, 10), 0.0)

    def test_negative_salary_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_cash_out(-1000, 5)

    def test_negative_days_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_cash_out(3000, -1)

    def test_large_salary_10_days(self):
        # 52000 / 26 = 2000 × 10 = 20000
        self.assertAlmostEqual(calculate_cash_out(52000, 10), 20000.0, places=2)

    def test_fractional_days(self):
        # 2600 / 26 = 100 × 2.5 = 250
        self.assertAlmostEqual(calculate_cash_out(2600, 2.5), 250.0, places=2)

    def test_uses_26_not_30_as_divisor(self):
        """Confirm divisor is 26 (EA standard), not 30."""
        result_26 = calculate_cash_out(2600, 5)   # 500.00
        result_30 = 2600 / 30 * 5                  # 433.33
        self.assertAlmostEqual(result_26, 500.0, places=2)
        self.assertNotAlmostEqual(result_26, result_30, places=1)

    def test_common_salary_ranges(self):
        # RM 1,500: 1500/26 × 3 = 173.08
        self.assertAlmostEqual(calculate_cash_out(1500, 3), 173.08, places=2)
        # RM 5,000: 5000/26 × 2 = 384.62
        self.assertAlmostEqual(calculate_cash_out(5000, 2), 384.62, places=2)


# ---------------------------------------------------------------------------
# AC2: Leave Expiry Notice generation
# ---------------------------------------------------------------------------

class TestGenerateLeaveExpiryNotices(FrappeTestCase):
    """generate_leave_expiry_notices builds correct notice dicts."""

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_annual_entitlement")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_monthly_basic")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_generates_notice_for_employee_with_unused_leave(
        self, mock_frappe, mock_basic, mock_entitlement, mock_unused
    ):
        mock_unused.return_value = 10.0
        mock_entitlement.return_value = 16  # >5 years → 16-day entitlement
        mock_basic.return_value = 4000.0
        mock_frappe.db.get_value.return_value = None  # no existing notice

        notices = generate_leave_expiry_notices(2025, ["EMP-001"])

        self.assertEqual(len(notices), 1)
        n = notices[0]
        self.assertEqual(n["employee"], "EMP-001")
        self.assertEqual(n["leave_year"], 2025)
        self.assertEqual(n["expiring_days"], 10.0)
        self.assertEqual(n["carry_forward_cap"], 16)  # 1× 16-day entitlement
        self.assertEqual(n["cash_out_days"], 0.0)      # 10 unused ≤ 16 cap → 0 cash-out
        self.assertAlmostEqual(n["cash_out_amount"], 0.0, places=2)

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    def test_no_notice_when_no_unused_leave(self, mock_unused):
        mock_unused.return_value = 0.0  # All leave consumed

        notices = generate_leave_expiry_notices(2025, ["EMP-002"])

        self.assertEqual(len(notices), 0)

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_annual_entitlement")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_monthly_basic")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_cash_out_days_when_unused_exceeds_cap(
        self, mock_frappe, mock_basic, mock_entitlement, mock_unused
    ):
        # Unused: 20 days, cap: 16 → 4 days must be cashed out
        mock_unused.return_value = 20.0
        mock_entitlement.return_value = 16
        mock_basic.return_value = 2600.0  # 2600/26=100 per day
        mock_frappe.db.get_value.return_value = None

        notices = generate_leave_expiry_notices(2025, ["EMP-003"])

        self.assertEqual(len(notices), 1)
        n = notices[0]
        self.assertEqual(n["cash_out_days"], 4.0)
        # 4 × 100 = 400
        self.assertAlmostEqual(n["cash_out_amount"], 400.0, places=2)

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_annual_entitlement")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_monthly_basic")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_existing_decision_included_in_notice(
        self, mock_frappe, mock_basic, mock_entitlement, mock_unused
    ):
        mock_unused.return_value = 5.0
        mock_entitlement.return_value = 12
        mock_basic.return_value = 3000.0
        mock_frappe.db.get_value.return_value = DECISION_CARRY_FORWARD

        notices = generate_leave_expiry_notices(2025, ["EMP-004"])

        self.assertEqual(notices[0]["decision"], DECISION_CARRY_FORWARD)

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    def test_empty_employee_list_returns_empty(self, mock_unused):
        notices = generate_leave_expiry_notices(2025, [])
        self.assertEqual(notices, [])

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_annual_entitlement")
    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_monthly_basic")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_notice_structure_has_required_keys(
        self, mock_frappe, mock_basic, mock_entitlement, mock_unused
    ):
        mock_unused.return_value = 8.0
        mock_entitlement.return_value = 12
        mock_basic.return_value = 2500.0
        mock_frappe.db.get_value.return_value = None

        notices = generate_leave_expiry_notices(2025, ["EMP-005"])
        n = notices[0]

        for key in ("employee", "leave_year", "expiring_days", "carry_forward_cap",
                    "cash_out_days", "cash_out_amount", "decision"):
            self.assertIn(key, n, f"Notice must contain '{key}' key")


# ---------------------------------------------------------------------------
# AC3: Record leave decision
# ---------------------------------------------------------------------------

class TestRecordLeaveDecision(FrappeTestCase):
    """HR Manager records decision and it is persisted correctly."""

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_record_carry_forward_decision(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_doc.name = "EALN-2025-EMP001"
        mock_frappe.new_doc.return_value = mock_doc
        mock_frappe.throw = MagicMock(side_effect=Exception("frappe.throw called"))

        record_leave_decision(
            employee="EMP-001",
            year=2025,
            decision=DECISION_CARRY_FORWARD,
            hr_manager="HR-MGR-001",
            carry_forward_days=8,
        )

        mock_doc.save.assert_called_once()
        self.assertEqual(mock_doc.decision, DECISION_CARRY_FORWARD)
        self.assertEqual(mock_doc.hr_manager, "HR-MGR-001")
        self.assertEqual(mock_doc.carry_forward_days, 8)

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_record_cash_out_decision(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-002",
            year=2025,
            decision=DECISION_CASH_OUT,
            hr_manager="HR-MGR-001",
            cash_out_days=5.0,
        )

        self.assertEqual(mock_doc.decision, DECISION_CASH_OUT)
        self.assertEqual(mock_doc.cash_out_days, 5.0)

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_record_mutual_forfeiture_decision(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-003",
            year=2025,
            decision=DECISION_MUTUAL_FORFEITURE,
            hr_manager="HR-MGR-001",
        )

        self.assertEqual(mock_doc.decision, DECISION_MUTUAL_FORFEITURE)

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_invalid_decision_calls_frappe_throw(self, mock_frappe):
        thrown = []
        mock_frappe.throw.side_effect = lambda msg, title="": (_ for _ in ()).throw(
            Exception(thrown.append(msg) or "thrown")
        )

        with self.assertRaises(Exception):
            record_leave_decision(
                employee="EMP-001",
                year=2025,
                decision="Invalid Decision",
                hr_manager="HR-MGR-001",
            )

        self.assertTrue(len(thrown) > 0, "frappe.throw should have been called")

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_updates_existing_notice_not_creates_new(self, mock_frappe):
        mock_frappe.db.get_value.return_value = "EALN-2025-EMP001"  # Existing record
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-001",
            year=2025,
            decision=DECISION_CASH_OUT,
            hr_manager="HR-MGR-002",
        )

        mock_frappe.get_doc.assert_called_once_with(
            EA_LEAVE_EXPIRY_NOTICE_DOCTYPE, "EALN-2025-EMP001"
        )
        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_creates_new_notice_when_none_exists(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-001",
            year=2025,
            decision=DECISION_CARRY_FORWARD,
            hr_manager="HR-MGR-001",
        )

        mock_frappe.new_doc.assert_called_once_with(EA_LEAVE_EXPIRY_NOTICE_DOCTYPE)
        mock_frappe.get_doc.assert_not_called()


# ---------------------------------------------------------------------------
# AC5: Year close-off validation
# ---------------------------------------------------------------------------

class TestValidateYearCloseReadiness(FrappeTestCase):
    """System blocks year close-off for employees without recorded decision."""

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_returns_employee_without_decision(self, mock_frappe, mock_unused):
        mock_unused.side_effect = lambda emp, yr: 10.0 if emp == "EMP-001" else 0.0
        mock_frappe.db.exists.return_value = None  # No decision recorded

        pending = validate_year_close_readiness(2025, ["EMP-001", "EMP-002"])

        self.assertIn("EMP-001", pending, "EMP-001 has unused leave and no decision — must be in pending")
        self.assertNotIn("EMP-002", pending, "EMP-002 has no unused leave — no decision needed")

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_returns_empty_when_all_decisions_recorded(self, mock_frappe, mock_unused):
        mock_unused.return_value = 10.0
        mock_frappe.db.exists.return_value = "EALN-2025-EMP001"  # Decision exists

        pending = validate_year_close_readiness(2025, ["EMP-001"])

        self.assertEqual(pending, [], "Should return empty list when all decisions recorded")

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_no_unused_leave_needs_no_decision(self, mock_frappe, mock_unused):
        mock_unused.return_value = 0.0  # No unused leave

        pending = validate_year_close_readiness(2025, ["EMP-001"])

        self.assertEqual(pending, [], "No unused leave → no decision required → year can close")

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    def test_empty_employee_list_returns_empty(self, mock_unused):
        pending = validate_year_close_readiness(2025, [])
        self.assertEqual(pending, [])

    @patch("lhdn_payroll_integration.services.leave_expiry_service._get_unused_annual_leave")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    def test_multiple_pending_employees_all_returned(self, mock_frappe, mock_unused):
        mock_unused.return_value = 5.0
        mock_frappe.db.exists.return_value = None

        pending = validate_year_close_readiness(2025, ["EMP-001", "EMP-002", "EMP-003"])

        self.assertEqual(set(pending), {"EMP-001", "EMP-002", "EMP-003"})


# ---------------------------------------------------------------------------
# AC6: Audit log — decision timestamp and HR manager recorded
# ---------------------------------------------------------------------------

class TestDecisionAuditLog(FrappeTestCase):
    """Audit log records decisions with HR manager and timestamp."""

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.nowdatetime")
    def test_decision_timestamp_is_recorded(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-01-15 10:30:00"
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-001",
            year=2025,
            decision=DECISION_CARRY_FORWARD,
            hr_manager="HR-MGR-001",
        )

        self.assertEqual(mock_doc.decision_timestamp, "2026-01-15 10:30:00")

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.nowdatetime")
    def test_hr_manager_name_is_recorded(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-01-15 10:30:00"
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-001",
            year=2025,
            decision=DECISION_CASH_OUT,
            hr_manager="HR-MANAGER-JANE",
        )

        self.assertEqual(mock_doc.hr_manager, "HR-MANAGER-JANE")

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.nowdatetime")
    def test_employee_and_year_set_on_new_doc(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-01-15 10:30:00"
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-007",
            year=2024,
            decision=DECISION_MUTUAL_FORFEITURE,
            hr_manager="HR-MGR-ADMIN",
        )

        self.assertEqual(mock_doc.employee, "EMP-007")
        self.assertEqual(mock_doc.leave_year, 2024)

    @patch("lhdn_payroll_integration.services.leave_expiry_service.frappe")
    @patch("lhdn_payroll_integration.services.leave_expiry_service.nowdatetime")
    def test_save_is_called_with_ignore_permissions(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-01-15 10:30:00"
        mock_frappe.db.get_value.return_value = None
        mock_doc = MagicMock()
        mock_frappe.new_doc.return_value = mock_doc

        record_leave_decision(
            employee="EMP-001",
            year=2025,
            decision=DECISION_CARRY_FORWARD,
            hr_manager="HR-MGR-001",
        )

        mock_doc.save.assert_called_once_with(ignore_permissions=True)
