"""Tests for Gig Workers Act 2025 — 7-Day Payment Deadline Alert Service (US-183).

Covers:
- Constants and configuration values
- Payment deadline computation
- Days remaining calculation
- Overdue detection
- Urgency classification
- Payment schedule detection
- Deadline tracking eligibility
- Transaction evaluation
- Payment completion recording
- Alert generation
- Overdue transaction filtering
- Dashboard grouping and summary
- MOHR compliance report generation
"""

import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.gig_payment_deadline_service import (
    PAYMENT_DEADLINE_DAYS,
    ALERT_DAYS_BEFORE_DEADLINE,
    GIG_WORKER_EMPLOYMENT_TYPE,
    TRACKABLE_STATUSES,
    SEVERITY_OVERDUE,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_ON_TRACK,
    BUCKET_OVERDUE,
    BUCKET_DUE_TODAY,
    BUCKET_DUE_TOMORROW,
    BUCKET_DUE_2_3,
    BUCKET_ON_TRACK,
    compute_payment_deadline,
    get_days_remaining,
    is_payment_overdue,
    classify_urgency,
    has_payment_schedule,
    needs_deadline_tracking,
    evaluate_transaction,
    record_payment_completion,
    should_alert,
    get_transactions_needing_alerts,
    get_overdue_transactions,
    group_by_days_remaining,
    get_dashboard_summary,
    generate_compliance_report,
)


class TestConstants(unittest.TestCase):
    """Verify module-level constants."""

    def test_payment_deadline_days_is_7(self):
        self.assertEqual(PAYMENT_DEADLINE_DAYS, 7)

    def test_alert_days_before_deadline_is_1(self):
        self.assertEqual(ALERT_DAYS_BEFORE_DEADLINE, 1)

    def test_gig_worker_employment_type(self):
        self.assertEqual(GIG_WORKER_EMPLOYMENT_TYPE, "Gig / Platform Worker")

    def test_trackable_statuses_contains_completed(self):
        self.assertIn("Completed", TRACKABLE_STATUSES)

    def test_severity_values(self):
        self.assertEqual(SEVERITY_OVERDUE, "Overdue")
        self.assertEqual(SEVERITY_CRITICAL, "Critical")
        self.assertEqual(SEVERITY_WARNING, "Warning")
        self.assertEqual(SEVERITY_ON_TRACK, "On Track")

    def test_bucket_keys(self):
        self.assertEqual(BUCKET_OVERDUE, "overdue")
        self.assertEqual(BUCKET_DUE_TODAY, "due_today")
        self.assertEqual(BUCKET_DUE_TOMORROW, "due_tomorrow")
        self.assertEqual(BUCKET_DUE_2_3, "due_2_3_days")
        self.assertEqual(BUCKET_ON_TRACK, "on_track")


class TestComputePaymentDeadline(unittest.TestCase):
    """Test compute_payment_deadline()."""

    def test_basic_deadline(self):
        result = compute_payment_deadline("2026-03-01")
        self.assertEqual(result, "2026-03-08")

    def test_deadline_crossing_month(self):
        result = compute_payment_deadline("2026-01-28")
        self.assertEqual(result, "2026-02-04")

    def test_deadline_crossing_year(self):
        result = compute_payment_deadline("2025-12-28")
        self.assertEqual(result, "2026-01-04")

    def test_leap_year_boundary(self):
        # 2028 is a leap year
        result = compute_payment_deadline("2028-02-25")
        self.assertEqual(result, "2028-03-03")

    def test_date_object_input(self):
        result = compute_payment_deadline(date(2026, 6, 15))
        self.assertEqual(result, "2026-06-22")


class TestGetDaysRemaining(unittest.TestCase):
    """Test get_days_remaining()."""

    def test_full_7_days_remaining(self):
        # Completion today, check today → 7 days remaining
        result = get_days_remaining("2026-03-01", "2026-03-01")
        self.assertEqual(result, 7)

    def test_3_days_remaining(self):
        # Completed on 1st, check on 5th → deadline 8th → 3 days
        result = get_days_remaining("2026-03-01", "2026-03-05")
        self.assertEqual(result, 3)

    def test_zero_days_remaining(self):
        # Completed on 1st, check on 8th → deadline 8th → 0 days
        result = get_days_remaining("2026-03-01", "2026-03-08")
        self.assertEqual(result, 0)

    def test_negative_days_overdue(self):
        # Completed on 1st, check on 10th → deadline 8th → -2 days
        result = get_days_remaining("2026-03-01", "2026-03-10")
        self.assertEqual(result, -2)

    def test_1_day_remaining(self):
        result = get_days_remaining("2026-03-01", "2026-03-07")
        self.assertEqual(result, 1)


class TestIsPaymentOverdue(unittest.TestCase):
    """Test is_payment_overdue()."""

    def test_not_overdue_day_1(self):
        self.assertFalse(is_payment_overdue("2026-03-01", "2026-03-01"))

    def test_not_overdue_on_deadline_day(self):
        self.assertFalse(is_payment_overdue("2026-03-01", "2026-03-08"))

    def test_overdue_one_day_past(self):
        self.assertTrue(is_payment_overdue("2026-03-01", "2026-03-09"))

    def test_overdue_many_days(self):
        self.assertTrue(is_payment_overdue("2026-03-01", "2026-03-20"))

    def test_not_overdue_midweek(self):
        self.assertFalse(is_payment_overdue("2026-03-01", "2026-03-05"))


class TestClassifyUrgency(unittest.TestCase):
    """Test classify_urgency()."""

    def test_on_track_full_week(self):
        # 7 days remaining → on track
        result = classify_urgency("2026-03-01", "2026-03-01")
        self.assertEqual(result, SEVERITY_ON_TRACK)

    def test_on_track_4_days(self):
        result = classify_urgency("2026-03-01", "2026-03-04")
        self.assertEqual(result, SEVERITY_ON_TRACK)

    def test_warning_3_days(self):
        result = classify_urgency("2026-03-01", "2026-03-05")
        self.assertEqual(result, SEVERITY_WARNING)

    def test_warning_2_days(self):
        result = classify_urgency("2026-03-01", "2026-03-06")
        self.assertEqual(result, SEVERITY_WARNING)

    def test_critical_1_day(self):
        result = classify_urgency("2026-03-01", "2026-03-07")
        self.assertEqual(result, SEVERITY_CRITICAL)

    def test_critical_0_days(self):
        result = classify_urgency("2026-03-01", "2026-03-08")
        self.assertEqual(result, SEVERITY_CRITICAL)

    def test_overdue(self):
        result = classify_urgency("2026-03-01", "2026-03-09")
        self.assertEqual(result, SEVERITY_OVERDUE)

    def test_overdue_many_days(self):
        result = classify_urgency("2026-03-01", "2026-03-15")
        self.assertEqual(result, SEVERITY_OVERDUE)


class TestHasPaymentSchedule(unittest.TestCase):
    """Test has_payment_schedule()."""

    def test_with_schedule(self):
        txn = {"payment_schedule": "Monthly on 15th"}
        self.assertTrue(has_payment_schedule(txn))

    def test_without_schedule_none(self):
        txn = {"payment_schedule": None}
        self.assertFalse(has_payment_schedule(txn))

    def test_without_schedule_empty(self):
        txn = {"payment_schedule": ""}
        self.assertFalse(has_payment_schedule(txn))

    def test_without_schedule_whitespace(self):
        txn = {"payment_schedule": "   "}
        self.assertFalse(has_payment_schedule(txn))

    def test_without_schedule_key_missing(self):
        txn = {}
        self.assertFalse(has_payment_schedule(txn))


class TestNeedsDeadlineTracking(unittest.TestCase):
    """Test needs_deadline_tracking()."""

    def test_completed_no_schedule_no_payment(self):
        txn = {"status": "Completed", "payment_schedule": None, "remittance_date": None}
        self.assertTrue(needs_deadline_tracking(txn))

    def test_not_completed(self):
        txn = {"status": "Pending", "payment_schedule": None, "remittance_date": None}
        self.assertFalse(needs_deadline_tracking(txn))

    def test_cancelled(self):
        txn = {"status": "Cancelled", "payment_schedule": None, "remittance_date": None}
        self.assertFalse(needs_deadline_tracking(txn))

    def test_has_schedule(self):
        txn = {"status": "Completed", "payment_schedule": "Weekly", "remittance_date": None}
        self.assertFalse(needs_deadline_tracking(txn))

    def test_already_paid(self):
        txn = {"status": "Completed", "payment_schedule": None, "remittance_date": "2026-03-05"}
        self.assertFalse(needs_deadline_tracking(txn))


class TestEvaluateTransaction(unittest.TestCase):
    """Test evaluate_transaction()."""

    def test_tracking_needed(self):
        txn = {
            "name": "TXN-001",
            "employee": "EMP-001",
            "service_completion_date": "2026-03-01",
            "status": "Completed",
            "payment_schedule": None,
            "remittance_date": None,
        }
        result = evaluate_transaction(txn, "2026-03-05")
        self.assertTrue(result["needs_tracking"])
        self.assertEqual(result["deadline"], "2026-03-08")
        self.assertEqual(result["days_remaining"], 3)
        self.assertEqual(result["urgency"], SEVERITY_WARNING)
        self.assertFalse(result["is_overdue"])
        self.assertFalse(result["is_paid"])

    def test_not_tracking_paid(self):
        txn = {
            "status": "Completed",
            "payment_schedule": None,
            "remittance_date": "2026-03-04",
        }
        result = evaluate_transaction(txn, "2026-03-05")
        self.assertFalse(result["needs_tracking"])
        self.assertTrue(result["is_paid"])

    def test_not_tracking_has_schedule(self):
        txn = {
            "status": "Completed",
            "payment_schedule": "Bi-weekly",
            "remittance_date": None,
        }
        result = evaluate_transaction(txn)
        self.assertFalse(result["needs_tracking"])

    def test_overdue_transaction(self):
        txn = {
            "name": "TXN-002",
            "service_completion_date": "2026-02-20",
            "status": "Completed",
            "payment_schedule": None,
            "remittance_date": None,
        }
        result = evaluate_transaction(txn, "2026-03-05")
        self.assertTrue(result["needs_tracking"])
        self.assertTrue(result["is_overdue"])
        self.assertEqual(result["urgency"], SEVERITY_OVERDUE)

    def test_no_completion_date(self):
        txn = {
            "status": "Completed",
            "payment_schedule": None,
            "remittance_date": None,
            "service_completion_date": None,
        }
        result = evaluate_transaction(txn)
        self.assertTrue(result["needs_tracking"])
        self.assertIsNone(result["deadline"])
        self.assertIsNone(result["days_remaining"])


class TestRecordPaymentCompletion(unittest.TestCase):
    """Test record_payment_completion()."""

    def test_paid_on_time(self):
        txn = {"service_completion_date": "2026-03-01"}
        result = record_payment_completion(txn, "2026-03-05")
        self.assertEqual(result["service_completion_date"], "2026-03-01")
        self.assertEqual(result["remittance_date"], "2026-03-05")
        self.assertEqual(result["deadline"], "2026-03-08")
        self.assertEqual(result["days_to_pay"], 4)
        self.assertTrue(result["within_deadline"])
        self.assertEqual(result["days_overdue"], 0)

    def test_paid_on_deadline_day(self):
        txn = {"service_completion_date": "2026-03-01"}
        result = record_payment_completion(txn, "2026-03-08")
        self.assertTrue(result["within_deadline"])
        self.assertEqual(result["days_to_pay"], 7)
        self.assertEqual(result["days_overdue"], 0)

    def test_paid_late(self):
        txn = {"service_completion_date": "2026-03-01"}
        result = record_payment_completion(txn, "2026-03-10")
        self.assertFalse(result["within_deadline"])
        self.assertEqual(result["days_to_pay"], 9)
        self.assertEqual(result["days_overdue"], 2)

    def test_paid_same_day(self):
        txn = {"service_completion_date": "2026-03-01"}
        result = record_payment_completion(txn, "2026-03-01")
        self.assertTrue(result["within_deadline"])
        self.assertEqual(result["days_to_pay"], 0)

    def test_no_completion_date(self):
        txn = {"service_completion_date": None}
        result = record_payment_completion(txn, "2026-03-05")
        self.assertIsNone(result["service_completion_date"])
        self.assertFalse(result["within_deadline"])


class TestShouldAlert(unittest.TestCase):
    """Test should_alert()."""

    def test_alert_when_1_day_left(self):
        # Completed 1st, check 7th → 1 day remaining → alert
        self.assertTrue(should_alert("2026-03-01", "2026-03-07"))

    def test_alert_when_0_days_left(self):
        # Completed 1st, check 8th → 0 days → alert
        self.assertTrue(should_alert("2026-03-01", "2026-03-08"))

    def test_alert_when_overdue(self):
        self.assertTrue(should_alert("2026-03-01", "2026-03-10"))

    def test_no_alert_when_2_days_left(self):
        # Completed 1st, check 6th → 2 days → no alert
        self.assertFalse(should_alert("2026-03-01", "2026-03-06"))

    def test_no_alert_when_full_week(self):
        self.assertFalse(should_alert("2026-03-01", "2026-03-01"))


class TestGetTransactionsNeedingAlerts(unittest.TestCase):
    """Test get_transactions_needing_alerts()."""

    def test_filters_alertable_transactions(self):
        transactions = [
            {
                "name": "TXN-001",
                "employee": "EMP-001",
                "employee_name": "Ali",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
            {
                "name": "TXN-002",
                "employee": "EMP-002",
                "employee_name": "Bala",
                "service_completion_date": "2026-03-06",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        # Check on 2026-03-07 → TXN-001 has 1 day (alert), TXN-002 has 6 days (no alert)
        alerts = get_transactions_needing_alerts(transactions, "2026-03-07")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["transaction"], "TXN-001")

    def test_excludes_paid_transactions(self):
        transactions = [
            {
                "name": "TXN-001",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-05",
            },
        ]
        alerts = get_transactions_needing_alerts(transactions, "2026-03-07")
        self.assertEqual(len(alerts), 0)

    def test_excludes_transactions_with_schedule(self):
        transactions = [
            {
                "name": "TXN-001",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": "Monthly",
                "remittance_date": None,
            },
        ]
        alerts = get_transactions_needing_alerts(transactions, "2026-03-07")
        self.assertEqual(len(alerts), 0)

    def test_includes_overdue(self):
        transactions = [
            {
                "name": "TXN-LATE",
                "employee": "EMP-LATE",
                "employee_name": "Chong",
                "service_completion_date": "2026-02-20",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        alerts = get_transactions_needing_alerts(transactions, "2026-03-07")
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["is_overdue"])

    def test_empty_list(self):
        alerts = get_transactions_needing_alerts([], "2026-03-07")
        self.assertEqual(len(alerts), 0)


class TestGetOverdueTransactions(unittest.TestCase):
    """Test get_overdue_transactions()."""

    def test_finds_overdue(self):
        transactions = [
            {
                "name": "TXN-001",
                "employee": "EMP-001",
                "employee_name": "Ali",
                "service_completion_date": "2026-02-20",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
            {
                "name": "TXN-002",
                "employee": "EMP-002",
                "employee_name": "Bala",
                "service_completion_date": "2026-03-06",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        overdue = get_overdue_transactions(transactions, "2026-03-07")
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["transaction"], "TXN-001")

    def test_no_overdue(self):
        transactions = [
            {
                "name": "TXN-001",
                "service_completion_date": "2026-03-06",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        overdue = get_overdue_transactions(transactions, "2026-03-07")
        self.assertEqual(len(overdue), 0)

    def test_excludes_paid_transactions(self):
        transactions = [
            {
                "name": "TXN-001",
                "service_completion_date": "2026-02-20",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-01",
            },
        ]
        overdue = get_overdue_transactions(transactions, "2026-03-07")
        self.assertEqual(len(overdue), 0)


class TestGroupByDaysRemaining(unittest.TestCase):
    """Test group_by_days_remaining()."""

    def _make_txn(self, name, completion_date):
        return {
            "name": name,
            "employee": f"EMP-{name}",
            "service_completion_date": completion_date,
            "status": "Completed",
            "payment_schedule": None,
            "remittance_date": None,
        }

    def test_all_buckets(self):
        # Check date: 2026-03-08
        transactions = [
            self._make_txn("OVERDUE", "2026-02-25"),       # deadline 2026-03-04, -4 days
            self._make_txn("TODAY", "2026-03-01"),          # deadline 2026-03-08, 0 days
            self._make_txn("TOMORROW", "2026-03-02"),       # deadline 2026-03-09, 1 day
            self._make_txn("2DAYS", "2026-03-03"),          # deadline 2026-03-10, 2 days
            self._make_txn("ONTRACK", "2026-03-05"),        # deadline 2026-03-12, 4 days
        ]
        buckets = group_by_days_remaining(transactions, "2026-03-08")

        self.assertEqual(len(buckets[BUCKET_OVERDUE]), 1)
        self.assertEqual(len(buckets[BUCKET_DUE_TODAY]), 1)
        self.assertEqual(len(buckets[BUCKET_DUE_TOMORROW]), 1)
        self.assertEqual(len(buckets[BUCKET_DUE_2_3]), 1)
        self.assertEqual(len(buckets[BUCKET_ON_TRACK]), 1)

    def test_empty_transactions(self):
        buckets = group_by_days_remaining([], "2026-03-08")
        for bucket in buckets.values():
            self.assertEqual(len(bucket), 0)

    def test_skips_paid_transactions(self):
        transactions = [
            {
                "name": "PAID",
                "employee": "EMP-1",
                "service_completion_date": "2026-02-20",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-02-25",
            },
        ]
        buckets = group_by_days_remaining(transactions, "2026-03-08")
        total = sum(len(v) for v in buckets.values())
        self.assertEqual(total, 0)


class TestGetDashboardSummary(unittest.TestCase):
    """Test get_dashboard_summary()."""

    def test_summary_counts(self):
        transactions = [
            {
                "name": "TXN-1",
                "employee": "E1",
                "service_completion_date": "2026-02-25",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
            {
                "name": "TXN-2",
                "employee": "E2",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        summary = get_dashboard_summary(transactions, "2026-03-08")
        self.assertIn("total_tracked", summary)
        self.assertEqual(summary["total_tracked"], 2)

    def test_empty_summary(self):
        summary = get_dashboard_summary([], "2026-03-08")
        self.assertEqual(summary["total_tracked"], 0)


class TestGenerateComplianceReport(unittest.TestCase):
    """Test generate_compliance_report()."""

    def test_paid_on_time(self):
        transactions = [
            {
                "name": "TXN-001",
                "employee": "EMP-001",
                "employee_name": "Ali",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-05",
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-10")
        self.assertEqual(report["total_transactions"], 1)
        self.assertEqual(report["paid_on_time"], 1)
        self.assertEqual(report["paid_late"], 0)
        self.assertEqual(report["unpaid_overdue"], 0)
        self.assertEqual(len(report["records"]), 1)
        self.assertEqual(report["records"][0]["status"], "Paid On Time")

    def test_paid_late(self):
        transactions = [
            {
                "name": "TXN-002",
                "employee": "EMP-002",
                "employee_name": "Bala",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-12",
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-15")
        self.assertEqual(report["paid_late"], 1)
        self.assertEqual(report["records"][0]["status"], "Paid Late")
        self.assertEqual(report["records"][0]["days_overdue"], 4)

    def test_unpaid_overdue(self):
        transactions = [
            {
                "name": "TXN-003",
                "employee": "EMP-003",
                "employee_name": "Chong",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-15")
        self.assertEqual(report["unpaid_overdue"], 1)
        self.assertEqual(report["records"][0]["status"], "Unpaid Overdue")

    def test_unpaid_within_deadline(self):
        transactions = [
            {
                "name": "TXN-004",
                "employee": "EMP-004",
                "employee_name": "Devi",
                "service_completion_date": "2026-03-10",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-12")
        self.assertEqual(report["unpaid_within_deadline"], 1)
        self.assertEqual(report["records"][0]["status"], "Unpaid Within Deadline")

    def test_excludes_scheduled_transactions(self):
        transactions = [
            {
                "name": "TXN-005",
                "employee": "EMP-005",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": "Weekly every Friday",
                "remittance_date": None,
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-15")
        self.assertEqual(report["total_transactions"], 0)

    def test_excludes_non_completed(self):
        transactions = [
            {
                "name": "TXN-006",
                "employee": "EMP-006",
                "service_completion_date": "2026-03-01",
                "status": "Cancelled",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-15")
        self.assertEqual(report["total_transactions"], 0)

    def test_mixed_transactions(self):
        transactions = [
            {
                "name": "ON-TIME",
                "employee": "E1",
                "employee_name": "Ali",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-05",
            },
            {
                "name": "LATE",
                "employee": "E2",
                "employee_name": "Bala",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-12",
            },
            {
                "name": "OVERDUE",
                "employee": "E3",
                "employee_name": "Chong",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
            {
                "name": "WITHIN",
                "employee": "E4",
                "employee_name": "Devi",
                "service_completion_date": "2026-03-10",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": None,
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-15")
        self.assertEqual(report["total_transactions"], 4)
        self.assertEqual(report["paid_on_time"], 1)
        self.assertEqual(report["paid_late"], 1)
        self.assertEqual(report["unpaid_overdue"], 1)
        self.assertEqual(report["unpaid_within_deadline"], 1)

    def test_empty_transactions(self):
        report = generate_compliance_report([], "2026-03-15")
        self.assertEqual(report["total_transactions"], 0)
        self.assertEqual(len(report["records"]), 0)

    def test_record_fields(self):
        transactions = [
            {
                "name": "TXN-007",
                "employee": "EMP-007",
                "employee_name": "Farid",
                "service_completion_date": "2026-03-01",
                "status": "Completed",
                "payment_schedule": None,
                "remittance_date": "2026-03-06",
            },
        ]
        report = generate_compliance_report(transactions, "2026-03-10")
        rec = report["records"][0]
        self.assertEqual(rec["transaction"], "TXN-007")
        self.assertEqual(rec["employee"], "EMP-007")
        self.assertEqual(rec["employee_name"], "Farid")
        self.assertEqual(rec["service_completion_date"], "2026-03-01")
        self.assertEqual(rec["deadline"], "2026-03-08")
        self.assertEqual(rec["remittance_date"], "2026-03-06")
        self.assertEqual(rec["days_to_pay"], 5)
