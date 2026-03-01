"""
Tests for US-206: Employment Act S.60A — Annual Leave Carry-Forward Cap
and Cash-Out Enforcement at Year-End.

TDD GREEN: bench --site frontend run-tests \
    --module lhdn_payroll_integration.tests.test_annual_leave_s60a
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.annual_leave_s60a_service import (
    ANNUAL_LEAVE_TYPE,
    VALID_DECISIONS,
    WORKING_DAYS_PER_MONTH,
    calculate_cashout_amount,
    check_leave_year_close_eligibility,
    compute_carry_forward_cap,
    generate_leave_expiry_notice,
    get_leave_audit_log,
    record_leave_expiry_decision,
)


# ── Constants tests ──────────────────────────────────────────────────────────────


class TestConstants(FrappeTestCase):
    """Verify statutory constants match Employment Act 1955 S.60A."""

    def test_working_days_per_month_is_26(self):
        self.assertEqual(WORKING_DAYS_PER_MONTH, 26)

    def test_annual_leave_type_name(self):
        self.assertEqual(ANNUAL_LEAVE_TYPE, "Annual Leave (EA)")

    def test_valid_decisions_contains_three_options(self):
        self.assertEqual(len(VALID_DECISIONS), 3)
        self.assertIn("Carry Forward", VALID_DECISIONS)
        self.assertIn("Cash Out", VALID_DECISIONS)
        self.assertIn("Mutual Forfeiture Agreement", VALID_DECISIONS)


# ── Carry-forward cap tests ──────────────────────────────────────────────────────


class TestComputeCarryForwardCap(FrappeTestCase):
    """EA S.60A: carry-forward cap defaults to 1× annual entitlement."""

    def test_default_cap_equals_entitlement(self):
        self.assertEqual(compute_carry_forward_cap(14), 14)

    def test_default_cap_for_18_days(self):
        self.assertEqual(compute_carry_forward_cap(18), 18)

    def test_default_cap_for_22_days(self):
        self.assertEqual(compute_carry_forward_cap(22), 22)

    def test_custom_cap_below_entitlement(self):
        # Employer restricts to 5 days carry-forward (stricter but legal)
        self.assertEqual(compute_carry_forward_cap(14, custom_cap=5), 5)

    def test_custom_cap_equals_entitlement(self):
        self.assertEqual(compute_carry_forward_cap(22, custom_cap=22), 22)

    def test_custom_cap_cannot_exceed_entitlement(self):
        # Cap of 30 with 22-day entitlement → capped at 22
        self.assertEqual(compute_carry_forward_cap(22, custom_cap=30), 22)

    def test_zero_entitlement_returns_zero(self):
        self.assertEqual(compute_carry_forward_cap(0), 0)

    def test_negative_entitlement_treated_as_zero(self):
        self.assertEqual(compute_carry_forward_cap(-5), 0)

    def test_negative_custom_cap_treated_as_zero(self):
        self.assertEqual(compute_carry_forward_cap(14, custom_cap=-3), 0)

    def test_none_custom_cap_uses_default(self):
        self.assertEqual(compute_carry_forward_cap(14, custom_cap=None), 14)


# ── Cash-out calculation tests ───────────────────────────────────────────────────


class TestCalculateCashoutAmount(FrappeTestCase):
    """EA S.60A(3): Cash-out = (Monthly Basic / 26) × leave days."""

    def test_standard_26_working_days(self):
        # RM 3000 / 26 × 5 days = 576.92
        result = calculate_cashout_amount(5, 3000.0)
        self.assertAlmostEqual(result, 576.92, places=2)

    def test_zero_days_returns_zero(self):
        self.assertEqual(calculate_cashout_amount(0, 5000.0), 0.0)

    def test_zero_salary_returns_zero(self):
        self.assertEqual(calculate_cashout_amount(5, 0.0), 0.0)

    def test_custom_working_days_per_month(self):
        # RM 2600 / 22 working days × 3 days = 354.55
        result = calculate_cashout_amount(3, 2600.0, working_days_per_month=22)
        self.assertAlmostEqual(result, 354.55, places=2)

    def test_fractional_days(self):
        # RM 5200 / 26 × 0.5 days = 100.00
        result = calculate_cashout_amount(0.5, 5200.0)
        self.assertAlmostEqual(result, 100.00, places=2)

    def test_result_rounded_to_2_decimal_places(self):
        result = calculate_cashout_amount(7, 4500.0)
        # 4500 / 26 × 7 = 1211.538... → 1211.54
        self.assertAlmostEqual(result, 1211.54, places=2)

    def test_none_days_treated_as_zero(self):
        self.assertEqual(calculate_cashout_amount(None, 3000.0), 0.0)

    def test_negative_days_treated_as_zero(self):
        self.assertEqual(calculate_cashout_amount(-2, 3000.0), 0.0)

    def test_none_salary_treated_as_zero(self):
        self.assertEqual(calculate_cashout_amount(5, None), 0.0)


# ── Leave expiry notice tests ────────────────────────────────────────────────────


class TestGenerateLeaveExpiryNotice(FrappeTestCase):
    """Leave Expiry Notice contains correct days_expiring and cash_out_amount."""

    def test_all_days_unused_no_cf_cap_restriction(self):
        notice = generate_leave_expiry_notice(
            employee="EMP-001",
            leave_year_end="2025-12-31",
            annual_allocation=14,
            days_taken=0,
            monthly_basic_salary=3000.0,
        )
        self.assertEqual(notice["annual_entitlement"], 14)
        self.assertEqual(notice["days_unused"], 14.0)
        # Default cap = 1× entitlement → all 14 can carry forward, nothing expires
        self.assertEqual(notice["days_expiring"], 0.0)
        self.assertEqual(notice["days_to_carry_forward"], 14.0)
        self.assertEqual(notice["cash_out_amount"], 0.0)
        self.assertEqual(notice["options"], [])

    def test_days_expiring_with_restricted_cf_cap(self):
        # 14-day entitlement, 0 taken, cap at 5 → 9 days expire
        notice = generate_leave_expiry_notice(
            employee="EMP-002",
            leave_year_end="2025-12-31",
            annual_allocation=14,
            days_taken=0,
            monthly_basic_salary=3000.0,
            carry_forward_cap=5,
        )
        self.assertEqual(notice["days_expiring"], 9.0)
        self.assertEqual(notice["days_to_carry_forward"], 5.0)
        # 3000/26 × 9 = 1038.46
        self.assertAlmostEqual(notice["cash_out_amount"], 1038.46, places=2)

    def test_partial_leave_taken_correctly_counted(self):
        # 22 days entitlement, 10 taken, 12 unused, cap = 22 → 0 expire
        notice = generate_leave_expiry_notice(
            employee="EMP-003",
            leave_year_end="2025-12-31",
            annual_allocation=22,
            days_taken=10,
            monthly_basic_salary=5000.0,
        )
        self.assertEqual(notice["days_taken"], 10.0)
        self.assertEqual(notice["days_unused"], 12.0)
        self.assertEqual(notice["days_expiring"], 0.0)

    def test_employee_field_in_notice(self):
        notice = generate_leave_expiry_notice("EMP-004", "2025-12-31", 14, 7, 3000.0)
        self.assertEqual(notice["employee"], "EMP-004")
        self.assertEqual(notice["leave_year_end"], "2025-12-31")

    def test_options_list_populated_when_days_expire(self):
        notice = generate_leave_expiry_notice(
            employee="EMP-005",
            leave_year_end="2025-12-31",
            annual_allocation=14,
            days_taken=0,
            monthly_basic_salary=3000.0,
            carry_forward_cap=5,
        )
        self.assertIn("Carry Forward", notice["options"])
        self.assertIn("Cash Out", notice["options"])
        self.assertIn("Mutual Forfeiture Agreement", notice["options"])

    def test_zero_unused_days_returns_zero_expiring(self):
        # All leave taken
        notice = generate_leave_expiry_notice("EMP-006", "2025-12-31", 14, 14, 3000.0)
        self.assertEqual(notice["days_unused"], 0.0)
        self.assertEqual(notice["days_expiring"], 0.0)
        self.assertEqual(notice["cash_out_amount"], 0.0)


# ── Record decision tests ────────────────────────────────────────────────────────


class TestRecordLeaveExpiryDecision(FrappeTestCase):
    """HR Manager must record employee's decision before leave year close-off."""

    def _mock_persist(self, *args, **kwargs):
        """Patch both DocType and cache to avoid DB writes in unit tests."""
        pass

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._upsert_leave_decision_log"
    )
    def test_carry_forward_decision_recorded(self, mock_upsert):
        entry = record_leave_expiry_decision(
            employee="EMP-010",
            leave_year_end="2025-12-31",
            decision="Carry Forward",
            hr_manager="admin",
            employee_acknowledged=True,
            days_decided=5,
        )
        self.assertEqual(entry["decision"], "Carry Forward")
        self.assertEqual(entry["employee"], "EMP-010")
        mock_upsert.assert_called_once()

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._upsert_leave_decision_log"
    )
    def test_cash_out_decision_recorded(self, mock_upsert):
        entry = record_leave_expiry_decision(
            employee="EMP-011",
            leave_year_end="2025-12-31",
            decision="Cash Out",
            hr_manager="admin",
            employee_acknowledged=True,
            days_decided=9,
            cash_out_amount=1038.46,
        )
        self.assertEqual(entry["decision"], "Cash Out")
        self.assertAlmostEqual(entry["cash_out_amount"], 1038.46, places=2)

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._upsert_leave_decision_log"
    )
    def test_mutual_forfeiture_requires_acknowledgement(self, mock_upsert):
        """EA 2022 Amendment: Forfeiture without consent must be rejected."""
        with self.assertRaises(Exception):
            record_leave_expiry_decision(
                employee="EMP-012",
                leave_year_end="2025-12-31",
                decision="Mutual Forfeiture Agreement",
                hr_manager="admin",
                employee_acknowledged=False,
            )

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._upsert_leave_decision_log"
    )
    def test_mutual_forfeiture_with_acknowledgement_accepted(self, mock_upsert):
        entry = record_leave_expiry_decision(
            employee="EMP-013",
            leave_year_end="2025-12-31",
            decision="Mutual Forfeiture Agreement",
            hr_manager="admin",
            employee_acknowledged=True,
            days_decided=3,
        )
        self.assertEqual(entry["decision"], "Mutual Forfeiture Agreement")
        self.assertTrue(entry["employee_acknowledged"])

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._upsert_leave_decision_log"
    )
    def test_invalid_decision_raises_exception(self, mock_upsert):
        with self.assertRaises(Exception):
            record_leave_expiry_decision(
                employee="EMP-014",
                leave_year_end="2025-12-31",
                decision="Forfeit Silently",  # Not a valid decision
                hr_manager="admin",
            )

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._upsert_leave_decision_log"
    )
    def test_log_entry_contains_recorded_at_date(self, mock_upsert):
        entry = record_leave_expiry_decision(
            employee="EMP-015",
            leave_year_end="2025-12-31",
            decision="Cash Out",
            hr_manager="admin",
            employee_acknowledged=True,
        )
        self.assertIn("recorded_at", entry)
        self.assertIsNotNone(entry["recorded_at"])


# ── Leave year close eligibility tests ──────────────────────────────────────────


class TestCheckLeaveYearCloseEligibility(FrappeTestCase):
    """System blocks leave year close-off without a recorded decision."""

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._get_leave_decision_log",
        return_value=None,
    )
    def test_blocked_when_no_decision_recorded(self, mock_get):
        result = check_leave_year_close_eligibility("EMP-020", "2025-12-31")
        self.assertFalse(result["eligible"])
        self.assertIn("blocked", result["reason"].lower())

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._get_leave_decision_log",
        return_value={"decision": "Cash Out", "employee": "EMP-021"},
    )
    def test_eligible_when_decision_recorded(self, mock_get):
        result = check_leave_year_close_eligibility("EMP-021", "2025-12-31")
        self.assertTrue(result["eligible"])
        self.assertIn("Cash Out", result["reason"])

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._get_leave_decision_log",
        return_value={"decision": "Carry Forward", "employee": "EMP-022"},
    )
    def test_eligible_with_carry_forward_decision(self, mock_get):
        result = check_leave_year_close_eligibility("EMP-022", "2025-12-31")
        self.assertTrue(result["eligible"])

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service._get_leave_decision_log",
        return_value={"decision": "Mutual Forfeiture Agreement", "employee": "EMP-023"},
    )
    def test_eligible_with_mutual_forfeiture_decision(self, mock_get):
        result = check_leave_year_close_eligibility("EMP-023", "2025-12-31")
        self.assertTrue(result["eligible"])


# ── Audit log tests ──────────────────────────────────────────────────────────────


class TestGetLeaveAuditLog(FrappeTestCase):
    """Audit log returns all leave expiry decisions for an employee."""

    @patch("lhdn_payroll_integration.services.annual_leave_s60a_service.frappe.db.exists", return_value=False)
    def test_returns_list(self, mock_exists):
        logs = get_leave_audit_log("EMP-030")
        self.assertIsInstance(logs, list)

    @patch("lhdn_payroll_integration.services.annual_leave_s60a_service.frappe.db.exists", return_value=False)
    def test_empty_log_when_no_doctype(self, mock_exists):
        logs = get_leave_audit_log("EMP-031", "2025-12-31")
        self.assertEqual(logs, [])

    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service.frappe.get_all",
        return_value=[
            {
                "employee": "EMP-032",
                "leave_year_end": "2025-12-31",
                "decision": "Cash Out",
                "hr_manager": "admin",
                "employee_acknowledged": 1,
                "days_decided": 5.0,
                "cash_out_amount": 576.92,
                "recorded_at": "2025-12-30",
            }
        ],
    )
    @patch(
        "lhdn_payroll_integration.services.annual_leave_s60a_service.frappe.db.exists",
        return_value=True,
    )
    def test_returns_log_entries_from_doctype(self, mock_exists, mock_get_all):
        logs = get_leave_audit_log("EMP-032", "2025-12-31")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["decision"], "Cash Out")
        self.assertAlmostEqual(logs[0]["cash_out_amount"], 576.92, places=2)
