"""Tests for Wage Payment Deadline Compliance — Employment Act S.19 7-Day Rule.

US-106: Add Wage Payment Deadline Compliance Alerts

Tests cover:
  - compute_payment_deadlines(): correct S.19(1) and S.19(1A) deadlines
  - get_payroll_compliance_status(): On-Time, At Risk, Overdue states
  - Status based on unsubmitted slip count and days remaining
  - Constants verification
"""
from datetime import date, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch

from lhdn_payroll_integration.lhdn_payroll_integration.utils.wage_payment_compliance import (
    compute_payment_deadlines,
    get_payroll_compliance_status,
    NORMAL_WAGE_PAYMENT_DAYS,
    OT_WAGE_PAYMENT_DAYS,
    ALERT_DAYS_BEFORE,
    STATUS_ON_TIME,
    STATUS_AT_RISK,
    STATUS_OVERDUE,
    send_wage_payment_alerts,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_entry(end_date: date, company="Test Co") -> MagicMock:
    """Build a minimal mock Payroll Entry."""
    entry = MagicMock()
    entry.end_date = end_date
    entry.company = company
    return entry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestWagePaymentConstants(FrappeTestCase):
    """Verify the statutory constants are correct."""

    def test_normal_wage_payment_days(self):
        """EA S.19(1): normal wages must be paid within 7 calendar days."""
        self.assertEqual(NORMAL_WAGE_PAYMENT_DAYS, 7)

    def test_ot_wage_payment_days(self):
        """EA S.19(1A): overtime wages must be paid within 10 calendar days."""
        self.assertEqual(OT_WAGE_PAYMENT_DAYS, 10)

    def test_alert_days_before(self):
        """Alerts triggered 2 days before the due date."""
        self.assertEqual(ALERT_DAYS_BEFORE, 2)

    def test_status_constants(self):
        """Status strings must match the expected dashboard display values."""
        self.assertEqual(STATUS_ON_TIME, "On-Time")
        self.assertEqual(STATUS_AT_RISK, "At Risk")
        self.assertEqual(STATUS_OVERDUE, "Overdue")


# ---------------------------------------------------------------------------
# compute_payment_deadlines
# ---------------------------------------------------------------------------

class TestComputePaymentDeadlines(FrappeTestCase):
    """Unit tests for compute_payment_deadlines()."""

    def test_normal_due_is_7_days_after_wage_period_end(self):
        """Normal payment due = wage_period_end + 7 days (S.19(1))."""
        end = date(2025, 10, 31)  # Oct 31
        result = compute_payment_deadlines(end)
        self.assertEqual(result["normal_due"], date(2025, 11, 7))

    def test_overtime_due_is_10_days_after_wage_period_end(self):
        """Overtime payment due = wage_period_end + 10 days (S.19(1A))."""
        end = date(2025, 10, 31)
        result = compute_payment_deadlines(end)
        self.assertEqual(result["overtime_due"], date(2025, 11, 10))

    def test_string_date_input(self):
        """compute_payment_deadlines accepts ISO string dates."""
        result = compute_payment_deadlines("2025-09-30")
        self.assertEqual(result["normal_due"], date(2025, 10, 7))
        self.assertEqual(result["overtime_due"], date(2025, 10, 10))

    def test_deadline_crosses_month_boundary(self):
        """Deadlines correctly cross month boundaries."""
        end = date(2025, 12, 28)
        result = compute_payment_deadlines(end)
        self.assertEqual(result["normal_due"], date(2026, 1, 4))
        self.assertEqual(result["overtime_due"], date(2026, 1, 7))

    def test_deadline_crosses_year_boundary(self):
        """Deadlines correctly cross year boundaries."""
        end = date(2025, 12, 31)
        result = compute_payment_deadlines(end)
        self.assertEqual(result["normal_due"], date(2026, 1, 7))
        self.assertEqual(result["overtime_due"], date(2026, 1, 10))

    def test_return_dict_has_required_keys(self):
        """compute_payment_deadlines always returns both keys."""
        result = compute_payment_deadlines(date(2025, 6, 30))
        self.assertIn("normal_due", result)
        self.assertIn("overtime_due", result)

    def test_overtime_due_after_normal_due(self):
        """OT deadline is always 3 days after normal deadline."""
        end = date(2025, 5, 31)
        result = compute_payment_deadlines(end)
        delta = (result["overtime_due"] - result["normal_due"]).days
        self.assertEqual(delta, 3)


# ---------------------------------------------------------------------------
# get_payroll_compliance_status
# ---------------------------------------------------------------------------

class TestGetPayrollComplianceStatus(FrappeTestCase):
    """Tests for get_payroll_compliance_status()."""

    def _run_status(self, wage_period_end: date, reference_date: date,
                    unsubmitted_count: int = 0):
        """Helper: mock frappe.get_doc and frappe.db.count, run status check."""
        entry = _make_entry(wage_period_end)
        with patch("frappe.get_doc", return_value=entry), \
             patch("frappe.db.count", return_value=unsubmitted_count):
            return get_payroll_compliance_status(
                "PE-TEST-001", reference_date=reference_date
            )

    # --- All slips submitted → On-Time regardless of days_remaining ---

    def test_all_submitted_before_due_date_is_on_time(self):
        """Slips submitted before deadline → On-Time."""
        end = date(2025, 9, 30)
        ref = date(2025, 10, 3)  # 4 days before due date (Oct 7)
        result = self._run_status(end, ref, unsubmitted_count=0)
        self.assertEqual(result["status"], STATUS_ON_TIME)
        self.assertTrue(result["all_slips_submitted"])

    def test_all_submitted_on_due_date_is_on_time(self):
        """Slips submitted exactly on deadline → On-Time."""
        end = date(2025, 9, 30)
        ref = date(2025, 10, 7)  # = normal_due
        result = self._run_status(end, ref, unsubmitted_count=0)
        self.assertEqual(result["status"], STATUS_ON_TIME)

    # --- Unsubmitted slips, plenty of time → On-Time ---

    def test_unsubmitted_slips_with_plenty_of_time_is_on_time(self):
        """Unsubmitted slips with 5 days remaining → On-Time (above alert threshold)."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 2)  # 5 days before Nov 7 due date
        result = self._run_status(end, ref, unsubmitted_count=3)
        self.assertEqual(result["status"], STATUS_ON_TIME)
        self.assertFalse(result["all_slips_submitted"])
        self.assertEqual(result["unsubmitted_count"], 3)

    # --- At Risk: 0–2 days remaining, slips not submitted ---

    def test_two_days_remaining_is_at_risk(self):
        """2 days remaining with unsubmitted slips → At Risk."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 5)  # 2 days before Nov 7
        result = self._run_status(end, ref, unsubmitted_count=1)
        self.assertEqual(result["status"], STATUS_AT_RISK)
        self.assertEqual(result["days_remaining"], 2)

    def test_one_day_remaining_is_at_risk(self):
        """1 day remaining with unsubmitted slips → At Risk."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 6)  # 1 day before Nov 7
        result = self._run_status(end, ref, unsubmitted_count=2)
        self.assertEqual(result["status"], STATUS_AT_RISK)
        self.assertEqual(result["days_remaining"], 1)

    def test_zero_days_remaining_is_at_risk(self):
        """0 days remaining (due today) with unsubmitted slips → At Risk."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 7)  # = normal_due
        result = self._run_status(end, ref, unsubmitted_count=5)
        self.assertEqual(result["status"], STATUS_AT_RISK)
        self.assertEqual(result["days_remaining"], 0)

    # --- Overdue: past due date, slips not submitted ---

    def test_one_day_past_due_is_overdue(self):
        """1 day past deadline with unsubmitted slips → Overdue."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 8)  # 1 day after Nov 7
        result = self._run_status(end, ref, unsubmitted_count=1)
        self.assertEqual(result["status"], STATUS_OVERDUE)
        self.assertEqual(result["days_remaining"], -1)

    def test_many_days_past_due_is_overdue(self):
        """15 days past deadline → Overdue."""
        end = date(2025, 9, 30)
        ref = date(2025, 10, 22)  # 15 days after Oct 7
        result = self._run_status(end, ref, unsubmitted_count=10)
        self.assertEqual(result["status"], STATUS_OVERDUE)
        self.assertLess(result["days_remaining"], 0)

    # --- Return dict structure ---

    def test_return_dict_has_all_required_keys(self):
        """get_payroll_compliance_status always returns all expected keys."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 2)
        result = self._run_status(end, ref, unsubmitted_count=0)

        required_keys = {
            "status", "days_remaining", "normal_due", "overtime_due",
            "all_slips_submitted", "unsubmitted_count", "wage_period_end",
        }
        self.assertEqual(required_keys, set(result.keys()))

    def test_deadlines_computed_correctly_from_entry(self):
        """normal_due and overtime_due in result match compute_payment_deadlines."""
        end = date(2025, 11, 30)
        ref = date(2025, 12, 1)
        result = self._run_status(end, ref, unsubmitted_count=0)

        expected = compute_payment_deadlines(end)
        self.assertEqual(result["normal_due"], expected["normal_due"])
        self.assertEqual(result["overtime_due"], expected["overtime_due"])

    def test_unsubmitted_count_zero_means_all_submitted(self):
        """unsubmitted_count=0 sets all_slips_submitted=True."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 2)
        result = self._run_status(end, ref, unsubmitted_count=0)
        self.assertTrue(result["all_slips_submitted"])
        self.assertEqual(result["unsubmitted_count"], 0)

    def test_unsubmitted_count_nonzero_means_not_all_submitted(self):
        """unsubmitted_count>0 sets all_slips_submitted=False."""
        end = date(2025, 10, 31)
        ref = date(2025, 11, 2)
        result = self._run_status(end, ref, unsubmitted_count=3)
        self.assertFalse(result["all_slips_submitted"])
        self.assertEqual(result["unsubmitted_count"], 3)

    def test_wage_period_end_in_result(self):
        """wage_period_end in result matches the Payroll Entry end_date."""
        end = date(2025, 8, 31)
        ref = date(2025, 9, 1)
        result = self._run_status(end, ref, unsubmitted_count=0)
        self.assertEqual(result["wage_period_end"], end)

    def test_string_reference_date_accepted(self):
        """reference_date can be passed as ISO string."""
        end = date(2025, 10, 31)
        entry = _make_entry(end)
        with patch("frappe.get_doc", return_value=entry), \
             patch("frappe.db.count", return_value=0):
            result = get_payroll_compliance_status("PE-001", reference_date="2025-11-02")
        self.assertEqual(result["status"], STATUS_ON_TIME)


# ---------------------------------------------------------------------------
# send_wage_payment_alerts
# ---------------------------------------------------------------------------

class TestSendWagePaymentAlerts(FrappeTestCase):
    """Tests for the daily background alert job send_wage_payment_alerts()."""

    def test_no_entries_exits_cleanly(self):
        """With no Payroll Entries, function returns without error."""
        with patch("frappe.get_all", return_value=[]):
            # Should not raise
            send_wage_payment_alerts()

    def test_no_hr_managers_exits_cleanly(self):
        """With no HR Manager users, function returns without sending emails."""
        today = date.today()
        end = today - timedelta(days=10)
        entries = [{"name": "PE-001", "company": "Test Co",
                    "end_date": end, "start_date": end - timedelta(days=30)}]
        with patch("frappe.get_all", return_value=entries), \
             patch("frappe.db.count", return_value=5), \
             patch("frappe.get_doc", return_value=_make_entry(end)):
            # _get_hr_manager_emails returns [] because get_all returns []
            # but we need to patch it to return [] for HR query
            with patch(
                "lhdn_payroll_integration.lhdn_payroll_integration.utils.wage_payment_compliance._get_hr_manager_emails",
                return_value=[]
            ):
                send_wage_payment_alerts()  # should not raise

    def test_at_risk_entry_triggers_sendmail(self):
        """At Risk entries trigger frappe.sendmail for each HR Manager."""
        today = date.today()
        # Create an entry where slips are not submitted and we're 1 day from due
        end = today - timedelta(days=6)  # 6 days ago → normal_due = today + 1 → 1 day remaining
        entries = [{"name": "PE-RISK-001", "company": "Test Co",
                    "end_date": end, "start_date": end - timedelta(days=30)}]

        with patch("frappe.get_all", return_value=entries), \
             patch("frappe.get_doc", return_value=_make_entry(end)), \
             patch("frappe.db.count", return_value=3), \
             patch(
                 "lhdn_payroll_integration.lhdn_payroll_integration.utils.wage_payment_compliance._get_hr_manager_emails",
                 return_value=["hr@test.com"]
             ), \
             patch("frappe.sendmail") as mock_sendmail:
            send_wage_payment_alerts()
            mock_sendmail.assert_called_once()
            call_kwargs = mock_sendmail.call_args[1]
            self.assertIn("hr@test.com", call_kwargs["recipients"])

    def test_overdue_entry_triggers_sendmail(self):
        """Overdue entries trigger frappe.sendmail with OVERDUE in subject."""
        today = date.today()
        end = today - timedelta(days=15)  # 15 days ago → 8 days overdue
        entries = [{"name": "PE-OVERDUE-001", "company": "Test Co",
                    "end_date": end, "start_date": end - timedelta(days=30)}]

        with patch("frappe.get_all", return_value=entries), \
             patch("frappe.get_doc", return_value=_make_entry(end)), \
             patch("frappe.db.count", return_value=2), \
             patch(
                 "lhdn_payroll_integration.lhdn_payroll_integration.utils.wage_payment_compliance._get_hr_manager_emails",
                 return_value=["hr@test.com"]
             ), \
             patch("frappe.sendmail") as mock_sendmail:
            send_wage_payment_alerts()
            mock_sendmail.assert_called_once()
            subject = mock_sendmail.call_args[1]["subject"]
            self.assertIn("OVERDUE", subject)

    def test_on_time_entry_does_not_trigger_alert(self):
        """On-Time entries (all slips submitted) do not trigger alerts."""
        today = date.today()
        end = today - timedelta(days=3)  # 3 days ago → normal_due = today + 4 → 4 days remaining
        entries = [{"name": "PE-OK-001", "company": "Test Co",
                    "end_date": end, "start_date": end - timedelta(days=30)}]

        with patch("frappe.get_all", return_value=entries), \
             patch("frappe.get_doc", return_value=_make_entry(end)), \
             patch("frappe.db.count", return_value=0), \
             patch(
                 "lhdn_payroll_integration.lhdn_payroll_integration.utils.wage_payment_compliance._get_hr_manager_emails",
                 return_value=["hr@test.com"]
             ), \
             patch("frappe.sendmail") as mock_sendmail:
            send_wage_payment_alerts()
            mock_sendmail.assert_not_called()
