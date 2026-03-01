"""Tests for PCB Late Payment Surcharge Service — US-146.

Section 107C(9) ITA 1967: 10% surcharge on outstanding PCB if remitted after the 15th.

Coverage:
  - compute_pcb_due_date: correct due date for any month/year including December
  - compute_surcharge: 10% flat calculation
  - check_and_flag_overdue_submissions: flags overdue CP39 logs
  - record_late_payment: records payment date and surcharge
  - send_pcb_deadline_alerts: returns count when no logs need alerting
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.pcb_surcharge_service import (
    PCB_SURCHARGE_RATE,
    check_and_flag_overdue_submissions,
    compute_pcb_due_date,
    compute_surcharge,
    record_late_payment,
    send_pcb_deadline_alerts,
)


class TestComputePcbDueDate(FrappeTestCase):
    """Unit tests for compute_pcb_due_date()."""

    def test_regular_month_returns_15th_of_next_month(self):
        """January payroll → due 15 February."""
        due = compute_pcb_due_date(1, 2025)
        self.assertEqual(due, date(2025, 2, 15))

    def test_december_wraps_to_january_next_year(self):
        """December payroll → due 15 January next year."""
        due = compute_pcb_due_date(12, 2024)
        self.assertEqual(due, date(2025, 1, 15))

    def test_string_inputs_accepted(self):
        """Month/year as strings should be coerced to int."""
        due = compute_pcb_due_date("3", "2025")
        self.assertEqual(due, date(2025, 4, 15))

    def test_all_months_return_15th(self):
        """Due date day is always 15 for all months."""
        for m in range(1, 13):
            due = compute_pcb_due_date(m, 2025)
            self.assertEqual(due.day, 15)

    def test_november_returns_december_15(self):
        """November payroll → 15 December."""
        due = compute_pcb_due_date(11, 2025)
        self.assertEqual(due, date(2025, 12, 15))


class TestComputeSurcharge(FrappeTestCase):
    """Unit tests for compute_surcharge()."""

    def test_ten_percent_of_standard_amount(self):
        """RM 10,000 PCB → RM 1,000 surcharge."""
        self.assertAlmostEqual(compute_surcharge(10000.0), 1000.0, places=2)

    def test_zero_pcb_gives_zero_surcharge(self):
        """Zero PCB → zero surcharge."""
        self.assertAlmostEqual(compute_surcharge(0), 0.0, places=2)

    def test_fractional_amount_rounded_to_two_decimals(self):
        """RM 333.33 × 10% = RM 33.33."""
        result = compute_surcharge(333.33)
        self.assertEqual(result, 33.33)

    def test_surcharge_rate_is_ten_percent(self):
        """Constant PCB_SURCHARGE_RATE must equal 0.10."""
        self.assertAlmostEqual(PCB_SURCHARGE_RATE, 0.10, places=5)

    def test_large_payroll_surcharge(self):
        """RM 500,000 payroll → RM 50,000 surcharge."""
        self.assertAlmostEqual(compute_surcharge(500000), 50000.0, places=2)


class TestCheckAndFlagOverdue(FrappeTestCase):
    """Tests for check_and_flag_overdue_submissions()."""

    def _make_cp39_log(self, due_date, status="Submitted", pcb_amount=5000.0):
        """Create a minimal CP39 Submission Log for testing."""
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No company found")
        log = frappe.new_doc("LHDN CP39 Submission Log")
        log.company = company
        log.month = "01"
        log.year = 2025
        log.status = status
        log.submission_reference = "TEST-REF"
        log.total_pcb_amount = pcb_amount
        log.pcb_payment_due_date = due_date
        log.is_late = 0
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log.name

    def test_overdue_log_gets_flagged(self):
        """A log with past due date and status=Submitted is flagged Overdue."""
        past_due = (date.today() - timedelta(days=5)).isoformat()
        log_name = self._make_cp39_log(past_due)
        try:
            flagged = check_and_flag_overdue_submissions()
            self.assertIn(log_name, flagged)
            updated = frappe.db.get_value(
                "LHDN CP39 Submission Log",
                log_name,
                ["is_late", "status", "estimated_surcharge"],
                as_dict=True,
            )
            self.assertEqual(updated["is_late"], 1)
            self.assertEqual(updated["status"], "Overdue")
            self.assertAlmostEqual(float(updated["estimated_surcharge"]), 500.0, places=2)
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log_name, ignore_missing=True, force=True)
            frappe.db.commit()

    def test_future_due_date_not_flagged(self):
        """A log with a future due date is NOT flagged."""
        future_due = (date.today() + timedelta(days=10)).isoformat()
        log_name = self._make_cp39_log(future_due)
        try:
            flagged = check_and_flag_overdue_submissions()
            self.assertNotIn(log_name, flagged)
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log_name, ignore_missing=True, force=True)
            frappe.db.commit()

    def test_already_late_not_re_flagged(self):
        """A log already marked is_late=1 is not processed again."""
        past_due = (date.today() - timedelta(days=3)).isoformat()
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No company found")
        log = frappe.new_doc("LHDN CP39 Submission Log")
        log.company = company
        log.month = "02"
        log.year = 2025
        log.status = "Submitted"
        log.submission_reference = "TEST-ALREADY-LATE"
        log.total_pcb_amount = 3000.0
        log.pcb_payment_due_date = past_due
        log.is_late = 1  # already flagged
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            flagged = check_and_flag_overdue_submissions()
            self.assertNotIn(log.name, flagged)
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log.name, ignore_missing=True, force=True)
            frappe.db.commit()

    def test_paid_status_not_flagged(self):
        """A log with status=Paid is not flagged as overdue."""
        past_due = (date.today() - timedelta(days=5)).isoformat()
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No company found")
        log = frappe.new_doc("LHDN CP39 Submission Log")
        log.company = company
        log.month = "03"
        log.year = 2025
        log.status = "Paid"
        log.submission_reference = "TEST-PAID"
        log.total_pcb_amount = 2000.0
        log.pcb_payment_due_date = past_due
        log.is_late = 0
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        try:
            flagged = check_and_flag_overdue_submissions()
            self.assertNotIn(log.name, flagged)
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log.name, ignore_missing=True, force=True)
            frappe.db.commit()


class TestRecordLatePayment(FrappeTestCase):
    """Tests for record_late_payment()."""

    def _make_log(self, due_date, pcb_amount=8000.0):
        company = frappe.db.get_value("Company", {}, "name")
        if not company:
            self.skipTest("No company found")
        log = frappe.new_doc("LHDN CP39 Submission Log")
        log.company = company
        log.month = "04"
        log.year = 2025
        log.status = "Submitted"
        log.submission_reference = "TEST-PAY"
        log.total_pcb_amount = pcb_amount
        log.pcb_payment_due_date = due_date
        log.is_late = 0
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        return log.name

    def test_late_payment_sets_is_late_and_estimated_surcharge(self):
        """Paying after due date → is_late=1, estimated_surcharge=10%, status=Paid."""
        due = date.today() - timedelta(days=3)
        log_name = self._make_log(due.isoformat())
        try:
            result = record_late_payment(log_name, date.today())
            self.assertEqual(result["is_late"], 1)
            self.assertAlmostEqual(result["estimated_surcharge"], 800.0, places=2)
            self.assertEqual(result["status"], "Paid")
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log_name, ignore_missing=True, force=True)
            frappe.db.commit()

    def test_on_time_payment_not_late(self):
        """Paying before due date → is_late=0, estimated_surcharge=0."""
        due = date.today() + timedelta(days=5)
        log_name = self._make_log(due.isoformat())
        try:
            result = record_late_payment(log_name, date.today())
            self.assertEqual(result["is_late"], 0)
            self.assertAlmostEqual(result["estimated_surcharge"], 0.0, places=2)
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log_name, ignore_missing=True, force=True)
            frappe.db.commit()

    def test_actual_surcharge_stored_when_provided(self):
        """Actual LHDN-assessed surcharge is stored if provided."""
        due = date.today() - timedelta(days=10)
        log_name = self._make_log(due.isoformat(), pcb_amount=20000.0)
        try:
            result = record_late_payment(log_name, date.today(), actual_surcharge=1800.0)
            self.assertAlmostEqual(result["actual_surcharge_assessed"], 1800.0, places=2)
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log_name, ignore_missing=True, force=True)
            frappe.db.commit()

    def test_payment_date_as_string_accepted(self):
        """payment_date can be provided as ISO string."""
        due = date.today() - timedelta(days=2)
        log_name = self._make_log(due.isoformat())
        try:
            result = record_late_payment(log_name, date.today().isoformat())
            self.assertEqual(result["status"], "Paid")
        finally:
            frappe.delete_doc("LHDN CP39 Submission Log", log_name, ignore_missing=True, force=True)
            frappe.db.commit()


class TestSendPcbDeadlineAlerts(FrappeTestCase):
    """Tests for send_pcb_deadline_alerts() — basic smoke test."""

    def test_no_crash_when_no_logs_to_alert(self):
        """Function returns an int and does not raise even with no matching logs."""
        result = send_pcb_deadline_alerts()
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)
