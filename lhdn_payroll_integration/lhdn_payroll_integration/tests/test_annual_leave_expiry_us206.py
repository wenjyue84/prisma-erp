"""Tests for US-206: EA S.60A Annual Leave Carry-Forward Cap and Cash-Out Enforcement.

Acceptance criteria verified:
1. Annual Leave (EA) carry-forward is configurable with maximum carry-forward days
   (default: 1x annual entitlement, e.g., max 22 days)
2. System generates Leave Expiry Notice per employee showing: days expiring,
   cash-out amount at basic daily rate, carry-forward option
3. HR Manager records employee's decision (Carry Forward | Cash Out |
   Mutual Forfeiture Agreement) before closing leave year
4. Cash-out = (Monthly Basic Salary / 26) x leave days
5. System blocks leave year close-off for employees without recorded decision
6. Audit log records all decisions with HR manager approval and employee
   acknowledgement timestamps
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAnnualLeaveConstants(FrappeTestCase):
    """Test module-level constants."""

    def test_annual_leave_type_ea(self):
        """ANNUAL_LEAVE_TYPE_EA is 'Annual Leave'."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            ANNUAL_LEAVE_TYPE_EA,
        )
        self.assertEqual(ANNUAL_LEAVE_TYPE_EA, "Annual Leave")

    def test_cash_out_divisor_26(self):
        """CASH_OUT_DIVISOR must be 26 per EA S.60A."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            CASH_OUT_DIVISOR,
        )
        self.assertEqual(CASH_OUT_DIVISOR, 26)

    def test_valid_decisions_has_three_options(self):
        """VALID_DECISIONS contains all three decision types."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            VALID_DECISIONS,
        )
        self.assertIn("Carry Forward", VALID_DECISIONS)
        self.assertIn("Cash Out", VALID_DECISIONS)
        self.assertIn("Mutual Forfeiture Agreement", VALID_DECISIONS)
        self.assertEqual(len(VALID_DECISIONS), 3)

    def test_max_carry_forward_multiplier_is_one(self):
        """MAX_CARRY_FORWARD_MULTIPLIER defaults to 1 (full entitlement)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            MAX_CARRY_FORWARD_MULTIPLIER,
        )
        self.assertEqual(MAX_CARRY_FORWARD_MULTIPLIER, 1)


class TestCarryForwardCap(FrappeTestCase):
    """Test max carry-forward calculation (AC-1: configurable carry-forward)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            get_max_carry_forward_days,
        )
        self.fn = get_max_carry_forward_days

    def test_default_multiplier_full_entitlement(self):
        """Default multiplier=1: max carry-forward equals full entitlement."""
        self.assertEqual(self.fn(22), 22)

    def test_half_multiplier(self):
        """Multiplier=0.5: max carry-forward is half the entitlement."""
        self.assertEqual(self.fn(22, 0.5), 11)

    def test_zero_multiplier_no_carry_forward(self):
        """Multiplier=0: no carry-forward allowed."""
        self.assertEqual(self.fn(22, 0.0), 0)

    def test_zero_entitlement(self):
        """Zero entitlement: max carry-forward is 0."""
        self.assertEqual(self.fn(0), 0)

    def test_negative_entitlement_raises(self):
        """Negative entitlement raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn(-1)

    def test_negative_multiplier_raises(self):
        """Negative multiplier raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn(22, -1)

    def test_fractional_entitlement_floored(self):
        """Float entitlement: result is floored int."""
        self.assertEqual(self.fn(22.5, 0.5), 11)

    def test_exact_22_days_standard(self):
        """Standard 22-day entitlement, full carry-forward."""
        self.assertEqual(self.fn(22, 1.0), 22)

    def test_custom_entitlement_12_days(self):
        """12-day entitlement with default multiplier."""
        self.assertEqual(self.fn(12, 1.0), 12)

    def test_custom_multiplier_0_75(self):
        """Multiplier=0.75: 75% of entitlement carries forward."""
        self.assertEqual(self.fn(20, 0.75), 15)


class TestExpiringDays(FrappeTestCase):
    """Test expiring days calculation (AC-2: notice shows days expiring)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            calculate_expiring_days,
        )
        self.fn = calculate_expiring_days

    def test_no_expiry_when_balance_under_cap(self):
        """Balance under max carry-forward: nothing expires."""
        self.assertEqual(self.fn(10, 22), 0.0)

    def test_no_expiry_when_balance_equals_cap(self):
        """Balance equals cap: nothing expires."""
        self.assertEqual(self.fn(22, 22), 0.0)

    def test_partial_expiry(self):
        """Balance exceeds cap: expiry = balance - max."""
        self.assertEqual(self.fn(30, 22), 8.0)

    def test_zero_carry_forward_all_expires(self):
        """No carry-forward allowed: all balance expires."""
        self.assertEqual(self.fn(15, 0), 15.0)

    def test_zero_balance(self):
        """Zero balance: nothing expires."""
        self.assertEqual(self.fn(0, 22), 0.0)

    def test_negative_balance_raises(self):
        """Negative balance raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn(-1, 22)

    def test_expiry_is_float(self):
        """Return type is float."""
        result = self.fn(10, 5)
        self.assertIsInstance(result, float)

    def test_one_day_over_cap(self):
        """Exactly one day over cap expires."""
        self.assertEqual(self.fn(23, 22), 1.0)


class TestCashOutAmount(FrappeTestCase):
    """Test cash-out amount calculation (AC-4: EA S.60A basic rate formula)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            calculate_cash_out_amount,
            CASH_OUT_DIVISOR,
        )
        self.fn = calculate_cash_out_amount
        self.divisor = CASH_OUT_DIVISOR

    def test_cash_out_divisor_is_26(self):
        """CASH_OUT_DIVISOR must be 26 per EA S.60A."""
        self.assertEqual(self.divisor, 26)

    def test_basic_calculation(self):
        """(3000 / 26) x 5 = 576.92 MYR."""
        result = self.fn(3000.0, 5)
        self.assertAlmostEqual(result, 576.92, places=2)

    def test_full_month_22_days(self):
        """Standard 22-day entitlement cash-out."""
        # (5000 / 26) * 22 = 4230.77
        result = self.fn(5000.0, 22)
        self.assertAlmostEqual(result, 4230.77, places=2)

    def test_zero_salary(self):
        """Zero salary -> zero cash-out."""
        self.assertAlmostEqual(self.fn(0, 10), 0.0, places=2)

    def test_zero_days(self):
        """Zero days -> zero cash-out."""
        self.assertAlmostEqual(self.fn(3000, 0), 0.0, places=2)

    def test_negative_salary_raises(self):
        """Negative salary raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn(-1000, 5)

    def test_negative_days_raises(self):
        """Negative days raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn(3000, -5)

    def test_zero_divisor_raises(self):
        """Zero divisor raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn(3000, 5, divisor=0)

    def test_decimal_days(self):
        """Fractional days supported."""
        # (2600 / 26) * 2.5 = 250.00
        result = self.fn(2600.0, 2.5)
        self.assertAlmostEqual(result, 250.0, places=2)

    def test_min_wage_scenario(self):
        """Minimum wage scenario: RM1,700/month, 5 days."""
        # (1700 / 26) * 5 = 326.92
        result = self.fn(1700.0, 5)
        self.assertAlmostEqual(result, 326.92, places=2)


class TestBuildLeaveExpiryNotice(FrappeTestCase):
    """Test Leave Expiry Notice generation (AC-2: notice content)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            build_leave_expiry_notice,
            VALID_DECISIONS,
        )
        self.fn = build_leave_expiry_notice
        self.valid_decisions = VALID_DECISIONS

    def _notice(self, balance=15, entitlement=22, salary=3000):
        return self.fn("EMP-001", 2025, entitlement, balance, salary)

    def test_notice_has_required_keys(self):
        """Notice dict has all required keys."""
        notice = self._notice()
        required = {
            "employee_id", "leave_year", "entitlement_days", "balance_days",
            "max_carry_forward_days", "expiring_days", "carry_forward_days",
            "daily_rate", "cash_out_amount", "valid_decisions",
        }
        self.assertTrue(required.issubset(notice.keys()))

    def test_notice_employee_and_year(self):
        """Notice contains correct employee_id and leave_year."""
        notice = self._notice()
        self.assertEqual(notice["employee_id"], "EMP-001")
        self.assertEqual(notice["leave_year"], 2025)

    def test_notice_max_carry_forward_defaults_to_entitlement(self):
        """Default multiplier=1: max_carry_forward_days = entitlement_days."""
        notice = self._notice(balance=15, entitlement=22)
        self.assertEqual(notice["max_carry_forward_days"], 22)

    def test_notice_expiring_days_zero_when_balance_under_cap(self):
        """Balance < entitlement: no expiring days."""
        notice = self._notice(balance=15, entitlement=22)
        self.assertEqual(notice["expiring_days"], 0.0)

    def test_notice_expiring_days_nonzero_when_balance_over_cap(self):
        """Balance 30 > entitlement 22: 8 days expire."""
        notice = self.fn("EMP-001", 2025, 22, 30, 3000)
        self.assertEqual(notice["expiring_days"], 8.0)

    def test_notice_daily_rate_calculation(self):
        """Daily rate = monthly_basic / 26."""
        notice = self._notice(salary=2600)
        self.assertAlmostEqual(notice["daily_rate"], 100.0, places=2)

    def test_notice_cash_out_amount(self):
        """Cash-out amount = (salary / 26) x balance_days."""
        # (3000 / 26) * 15 = 1730.77
        notice = self._notice(balance=15, salary=3000)
        self.assertAlmostEqual(notice["cash_out_amount"], 1730.77, places=2)

    def test_notice_valid_decisions(self):
        """Notice shows all three valid decisions."""
        notice = self._notice()
        for d in ["Carry Forward", "Cash Out", "Mutual Forfeiture Agreement"]:
            self.assertIn(d, notice["valid_decisions"])

    def test_notice_carry_forward_days_under_cap(self):
        """carry_forward_days = balance when balance < max_carry_forward."""
        notice = self._notice(balance=15, entitlement=22)
        self.assertEqual(notice["carry_forward_days"], 15)

    def test_notice_carry_forward_capped_at_max(self):
        """balance > entitlement: carry_forward_days capped at max."""
        notice = self.fn("EMP-001", 2025, 22, 30, 3000)
        self.assertEqual(notice["carry_forward_days"], 22)

    def test_notice_entitlement_days_recorded(self):
        """Notice records entitlement_days correctly."""
        notice = self._notice(entitlement=16)
        self.assertEqual(notice["entitlement_days"], 16)

    def test_notice_balance_days_recorded(self):
        """Notice records balance_days correctly."""
        notice = self._notice(balance=8)
        self.assertEqual(notice["balance_days"], 8)


class TestValidateDecision(FrappeTestCase):
    """Test decision validation (AC-3: HR Manager records decision)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            validate_decision,
        )
        self.fn = validate_decision

    def test_carry_forward_valid(self):
        """'Carry Forward' is valid."""
        self.fn("Carry Forward")  # Should not raise

    def test_cash_out_valid(self):
        """'Cash Out' is valid."""
        self.fn("Cash Out")  # Should not raise

    def test_mutual_forfeiture_valid(self):
        """'Mutual Forfeiture Agreement' is valid."""
        self.fn("Mutual Forfeiture Agreement")  # Should not raise

    def test_invalid_decision_raises(self):
        """Invalid decision string raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn("Forfeit")

    def test_empty_decision_raises(self):
        """Empty string raises ValueError."""
        with self.assertRaises(ValueError):
            self.fn("")

    def test_case_sensitive_carry_forward(self):
        """Decision matching is case-sensitive."""
        with self.assertRaises(ValueError):
            self.fn("carry forward")

    def test_case_sensitive_cash_out(self):
        """'cash out' (lowercase) is rejected."""
        with self.assertRaises(ValueError):
            self.fn("cash out")

    def test_partial_match_rejected(self):
        """Partial decision string is rejected."""
        with self.assertRaises(ValueError):
            self.fn("Carry")


class TestBuildAuditEntry(FrappeTestCase):
    """Test audit log entry creation (AC-6: audit log with timestamps)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            build_audit_entry,
        )
        self.fn = build_audit_entry

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    def test_audit_entry_has_required_keys(self, mock_now):
        """Audit entry has all required audit fields."""
        mock_now.return_value = datetime(2025, 12, 31, 17, 0, 0)
        entry = self.fn("EMP-001", 2025, "Carry Forward", "HR-MGR-001")
        required = {
            "employee_id", "leave_year", "decision", "hr_manager_id",
            "approved_at", "employee_acknowledged_at",
        }
        self.assertTrue(required.issubset(entry.keys()))

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    def test_audit_entry_correct_values(self, mock_now):
        """Audit entry captures employee, year, decision, hr_manager."""
        mock_now.return_value = datetime(2025, 12, 31, 17, 0, 0)
        entry = self.fn("EMP-001", 2025, "Cash Out", "HR-MGR-001")
        self.assertEqual(entry["employee_id"], "EMP-001")
        self.assertEqual(entry["leave_year"], 2025)
        self.assertEqual(entry["decision"], "Cash Out")
        self.assertEqual(entry["hr_manager_id"], "HR-MGR-001")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    def test_audit_entry_custom_ack_timestamp(self, mock_now):
        """Custom employee_acknowledged_at is preserved."""
        mock_now.return_value = datetime(2025, 12, 31)
        custom_ack = datetime(2025, 12, 30, 10, 0, 0)
        entry = self.fn("EMP-001", 2025, "Carry Forward", "HR-MGR-001", custom_ack)
        self.assertIn(str(custom_ack), entry["employee_acknowledged_at"])

    def test_invalid_decision_raises_no_entry(self):
        """Invalid decision raises ValueError without creating entry."""
        with self.assertRaises(ValueError):
            self.fn("EMP-001", 2025, "INVALID", "HR-MGR-001")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    def test_all_three_valid_decisions_accepted(self, mock_now):
        """All three valid decisions create audit entries without error."""
        mock_now.return_value = datetime(2025, 12, 31)
        for decision in ["Carry Forward", "Cash Out", "Mutual Forfeiture Agreement"]:
            entry = self.fn("EMP-001", 2025, decision, "HR-001")
            self.assertEqual(entry["decision"], decision)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    def test_approved_at_timestamp_recorded(self, mock_now):
        """approved_at is recorded from now_datetime()."""
        fixed_ts = datetime(2025, 12, 31, 12, 0, 0)
        mock_now.return_value = fixed_ts
        entry = self.fn("EMP-001", 2025, "Cash Out", "HR-001")
        self.assertIn(str(fixed_ts), entry["approved_at"])


class TestCanCloseLeaveYear(FrappeTestCase):
    """Test leave year closure blocking logic (AC-5: block without decision)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            can_close_leave_year,
        )
        self.fn = can_close_leave_year

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    def test_can_close_when_no_unused_leave(self, mock_decision, mock_balance):
        """No unused leave -> can close (no action needed)."""
        mock_balance.return_value = 0.0
        self.assertTrue(self.fn("EMP-001", 2025))
        mock_decision.assert_not_called()

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    def test_can_close_when_decision_recorded(self, mock_decision, mock_balance):
        """Unused leave exists AND decision recorded -> can close."""
        mock_balance.return_value = 5.0
        mock_decision.return_value = True
        self.assertTrue(self.fn("EMP-001", 2025))

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    def test_blocked_when_unused_leave_no_decision(self, mock_decision, mock_balance):
        """Unused leave AND no decision -> blocked (cannot close)."""
        mock_balance.return_value = 5.0
        mock_decision.return_value = False
        self.assertFalse(self.fn("EMP-001", 2025))

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    def test_can_close_when_zero_balance(self, mock_decision, mock_balance):
        """Exactly zero balance -> can close without decision."""
        mock_balance.return_value = 0
        self.assertTrue(self.fn("EMP-001", 2025))

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    def test_blocked_for_large_balance(self, mock_decision, mock_balance):
        """Large balance with no decision -> blocked."""
        mock_balance.return_value = 22.0
        mock_decision.return_value = False
        self.assertFalse(self.fn("EMP-001", 2025))


class TestGetEmployeesWithoutDecision(FrappeTestCase):
    """Test listing employees who need a leave expiry decision (AC-5)."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            get_employees_without_decision,
        )
        self.fn = get_employees_without_decision

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch("frappe.get_all")
    def test_returns_employees_with_balance_no_decision(
        self, mock_get_all, mock_balance, mock_decision
    ):
        """Returns employees with unused leave and no decision recorded."""
        mock_get_all.return_value = ["EMP-001", "EMP-002", "EMP-003"]
        mock_balance.side_effect = lambda emp, yr: 10.0 if emp in ("EMP-001", "EMP-002") else 0.0
        mock_decision.side_effect = lambda emp, yr: emp == "EMP-001"

        result = self.fn(2025)
        self.assertIn("EMP-002", result)
        self.assertNotIn("EMP-001", result)   # Has decision
        self.assertNotIn("EMP-003", result)   # No unused leave

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch("frappe.get_all")
    def test_empty_when_all_have_decisions(
        self, mock_get_all, mock_balance, mock_decision
    ):
        """Returns empty list when all employees have decisions."""
        mock_get_all.return_value = ["EMP-001", "EMP-002"]
        mock_balance.return_value = 5.0
        mock_decision.return_value = True
        result = self.fn(2025)
        self.assertEqual(result, [])

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch("frappe.get_all")
    def test_company_filter_passed_to_get_all(
        self, mock_get_all, mock_balance, mock_decision
    ):
        """Company filter is passed to frappe.get_all."""
        mock_get_all.return_value = []
        mock_balance.return_value = 0.0
        mock_decision.return_value = False

        self.fn(2025, company="Test Company")
        call_kwargs = mock_get_all.call_args
        self.assertEqual(call_kwargs[1]["filters"]["company"], "Test Company")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch("frappe.get_all")
    def test_returns_empty_list_no_employees(
        self, mock_get_all, mock_balance, mock_decision
    ):
        """Empty employee list returns empty result."""
        mock_get_all.return_value = []
        result = self.fn(2025)
        self.assertEqual(result, [])

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.has_leave_expiry_decision"
    )
    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.get_leave_balance_at_year_end"
    )
    @patch("frappe.get_all")
    def test_all_without_leave_excluded(
        self, mock_get_all, mock_balance, mock_decision
    ):
        """Employees with zero balance are excluded even without decision."""
        mock_get_all.return_value = ["EMP-001", "EMP-002"]
        mock_balance.return_value = 0.0
        mock_decision.return_value = False
        result = self.fn(2025)
        self.assertEqual(result, [])


class TestRecordLeaveExpiryDecision(FrappeTestCase):
    """Test leave expiry decision recording (AC-3: HR records decision)."""

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    @patch("frappe.get_doc")
    def test_creates_doc_with_correct_fields(self, mock_get_doc, mock_now):
        """record_leave_expiry_decision creates a doc with correct fields."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            record_leave_expiry_decision,
        )
        mock_now.return_value = datetime(2025, 12, 31)
        mock_doc = MagicMock()
        mock_doc.name = "LHDN-LEAVE-EXP-0001"
        mock_get_doc.return_value = mock_doc

        result = record_leave_expiry_decision("EMP-001", 2025, "Cash Out", "HR-001")

        mock_get_doc.assert_called_once()
        call_args = mock_get_doc.call_args[0][0]
        self.assertEqual(call_args["doctype"], "LHDN Leave Expiry Decision")
        self.assertEqual(call_args["employee"], "EMP-001")
        self.assertEqual(call_args["leave_year"], 2025)
        self.assertEqual(call_args["decision"], "Cash Out")
        self.assertEqual(call_args["hr_manager"], "HR-001")
        mock_doc.insert.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(result, "LHDN-LEAVE-EXP-0001")

    @patch("frappe.get_doc")
    def test_invalid_decision_raises_before_doc_creation(self, mock_get_doc):
        """Invalid decision raises ValueError before creating doc."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            record_leave_expiry_decision,
        )
        with self.assertRaises(ValueError):
            record_leave_expiry_decision("EMP-001", 2025, "INVALID", "HR-001")
        mock_get_doc.assert_not_called()

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    @patch("frappe.get_doc")
    def test_all_three_decisions_can_be_recorded(self, mock_get_doc, mock_now):
        """All three valid decisions can be recorded."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            record_leave_expiry_decision,
        )
        mock_now.return_value = datetime(2025, 12, 31)
        for decision in ["Carry Forward", "Cash Out", "Mutual Forfeiture Agreement"]:
            mock_doc = MagicMock()
            mock_doc.name = f"LHDN-{decision[:4]}"
            mock_get_doc.return_value = mock_doc

            result = record_leave_expiry_decision("EMP-001", 2025, decision, "HR-001")
            self.assertIsNotNone(result)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service.now_datetime"
    )
    @patch("frappe.get_doc")
    def test_custom_ack_timestamp_stored(self, mock_get_doc, mock_now):
        """Custom employee_acknowledged_at is stored in the doc."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.annual_leave_expiry_service import (
            record_leave_expiry_decision,
        )
        mock_now.return_value = datetime(2025, 12, 31)
        mock_doc = MagicMock()
        mock_doc.name = "LHDN-001"
        mock_get_doc.return_value = mock_doc

        custom_ack = datetime(2025, 12, 30, 9, 0, 0)
        record_leave_expiry_decision("EMP-001", 2025, "Carry Forward", "HR-001", custom_ack)

        call_args = mock_get_doc.call_args[0][0]
        self.assertEqual(call_args["employee_acknowledged_at"], custom_ack)
