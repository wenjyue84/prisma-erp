"""Tests for US-219 — TP3 30-Day Collection Deadline Compliance Alert.

Covers:
  - Constants validation
  - Mid-year hire eligibility (including January exclusion)
  - Deadline and alert date computation
  - Days-since-join and days-until-deadline
  - Single-employee status assessment
  - Salary Slip warning generation
  - Batch outstanding/overdue queries
  - Pending alert queries
  - Dashboard summary generation
  - Notification building (single and batch)
  - Auto-clear check
  - Compliance report generation
"""

from datetime import date, timedelta
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.tp3_deadline_alert_service import (
    # Constants
    TP3_COLLECTION_DEADLINE_DAYS,
    FIRST_ALERT_DAYS_AFTER_JOIN,
    JANUARY_EXCLUSION_MONTH,
    SEVERITY_OVERDUE,
    SEVERITY_APPROACHING,
    SEVERITY_OK,
    SEVERITY_EXEMPT,
    STATUS_TP3_MISSING,
    STATUS_TP3_RECEIVED,
    STATUS_EXEMPT_JANUARY,
    STATUS_EXEMPT_NOT_MID_YEAR,
    BUCKET_OVERDUE,
    BUCKET_ALERT_SENT,
    BUCKET_WITHIN_WINDOW,
    BUCKET_RECEIVED,
    BUCKET_EXEMPT,
    SALARY_SLIP_WARNING,
    # Functions
    is_mid_year_hire,
    compute_tp3_deadline,
    compute_first_alert_date,
    get_days_since_join,
    get_days_until_deadline,
    is_deadline_overdue,
    should_send_first_alert,
    check_employee_tp3_status,
    get_salary_slip_tp3_warning,
    get_outstanding_tp3_employees,
    get_pending_tp3_alerts,
    generate_tp3_dashboard_summary,
    build_notification,
    build_batch_notifications,
    is_alert_cleared,
    generate_compliance_report,
)


def _make_employee(
    employee_id="HR-EMP-00001",
    employee_name="Test Employee",
    join_date=None,
    tax_year=2026,
    has_tp3=False,
):
    """Helper to build an employee record dict."""
    return {
        "employee_id": employee_id,
        "employee_name": employee_name,
        "join_date": join_date,
        "tax_year": tax_year,
        "has_tp3": has_tp3,
    }


# ===========================================================================
# Constants
# ===========================================================================

class TestTP3DeadlineAlertConstants(FrappeTestCase):
    """Verify regulatory constants are correct."""

    def test_collection_deadline_is_30_days(self):
        self.assertEqual(TP3_COLLECTION_DEADLINE_DAYS, 30)

    def test_first_alert_is_14_days(self):
        self.assertEqual(FIRST_ALERT_DAYS_AFTER_JOIN, 14)

    def test_january_exclusion_month(self):
        self.assertEqual(JANUARY_EXCLUSION_MONTH, 1)

    def test_severity_constants_exist(self):
        self.assertEqual(SEVERITY_OVERDUE, "Overdue")
        self.assertEqual(SEVERITY_APPROACHING, "Approaching")
        self.assertEqual(SEVERITY_OK, "OK")
        self.assertEqual(SEVERITY_EXEMPT, "Exempt")

    def test_status_constants_exist(self):
        self.assertEqual(STATUS_TP3_MISSING, "TP3 Missing")
        self.assertEqual(STATUS_TP3_RECEIVED, "TP3 Received")
        self.assertEqual(STATUS_EXEMPT_JANUARY, "Exempt (January Joiner)")
        self.assertEqual(STATUS_EXEMPT_NOT_MID_YEAR, "Exempt (Not Mid-Year Hire)")

    def test_bucket_constants_exist(self):
        self.assertEqual(BUCKET_OVERDUE, "overdue")
        self.assertEqual(BUCKET_ALERT_SENT, "alert_sent")
        self.assertEqual(BUCKET_WITHIN_WINDOW, "within_window")
        self.assertEqual(BUCKET_RECEIVED, "received")
        self.assertEqual(BUCKET_EXEMPT, "exempt")

    def test_salary_slip_warning_not_empty(self):
        self.assertIn("TP3", SALARY_SLIP_WARNING)
        self.assertIn("PCB", SALARY_SLIP_WARNING)


# ===========================================================================
# is_mid_year_hire
# ===========================================================================

class TestIsMidYearHire(FrappeTestCase):
    """Test mid-year hire classification."""

    def test_february_joiner_is_mid_year(self):
        self.assertTrue(is_mid_year_hire(date(2026, 2, 15), 2026))

    def test_march_joiner_is_mid_year(self):
        self.assertTrue(is_mid_year_hire(date(2026, 3, 1), 2026))

    def test_june_joiner_is_mid_year(self):
        self.assertTrue(is_mid_year_hire(date(2026, 6, 30), 2026))

    def test_december_joiner_is_mid_year(self):
        self.assertTrue(is_mid_year_hire(date(2026, 12, 1), 2026))

    def test_january_1_joiner_is_excluded(self):
        self.assertFalse(is_mid_year_hire(date(2026, 1, 1), 2026))

    def test_january_15_joiner_is_excluded(self):
        self.assertFalse(is_mid_year_hire(date(2026, 1, 15), 2026))

    def test_january_31_joiner_is_excluded(self):
        self.assertFalse(is_mid_year_hire(date(2026, 1, 31), 2026))

    def test_different_year_is_not_mid_year(self):
        self.assertFalse(is_mid_year_hire(date(2025, 6, 15), 2026))

    def test_none_join_date_returns_false(self):
        self.assertFalse(is_mid_year_hire(None, 2026))

    def test_string_date_accepted(self):
        self.assertTrue(is_mid_year_hire("2026-03-15", 2026))

    def test_default_tax_year_uses_join_date_year(self):
        self.assertTrue(is_mid_year_hire(date(2026, 5, 10)))

    def test_january_joiner_default_tax_year(self):
        self.assertFalse(is_mid_year_hire(date(2026, 1, 20)))


# ===========================================================================
# Deadline computation
# ===========================================================================

class TestComputeTP3Deadline(FrappeTestCase):
    """Test TP3 collection deadline computation."""

    def test_deadline_is_30_days_from_join(self):
        result = compute_tp3_deadline(date(2026, 3, 1))
        self.assertEqual(result, date(2026, 3, 31))

    def test_deadline_crosses_month_boundary(self):
        result = compute_tp3_deadline(date(2026, 2, 15))
        self.assertEqual(result, date(2026, 3, 17))

    def test_deadline_with_string_date(self):
        result = compute_tp3_deadline("2026-06-01")
        self.assertEqual(result, date(2026, 7, 1))

    def test_deadline_year_boundary(self):
        result = compute_tp3_deadline(date(2026, 12, 10))
        self.assertEqual(result, date(2027, 1, 9))


class TestComputeFirstAlertDate(FrappeTestCase):
    """Test first alert date computation (14 days after join)."""

    def test_alert_is_14_days_from_join(self):
        result = compute_first_alert_date(date(2026, 3, 1))
        self.assertEqual(result, date(2026, 3, 15))

    def test_alert_with_string_date(self):
        result = compute_first_alert_date("2026-06-10")
        self.assertEqual(result, date(2026, 6, 24))


# ===========================================================================
# Days calculations
# ===========================================================================

class TestDaysSinceJoin(FrappeTestCase):
    """Test days elapsed since join date."""

    def test_same_day_is_zero(self):
        self.assertEqual(get_days_since_join(date(2026, 3, 1), date(2026, 3, 1)), 0)

    def test_10_days_after_join(self):
        self.assertEqual(get_days_since_join(date(2026, 3, 1), date(2026, 3, 11)), 10)

    def test_30_days_after_join(self):
        self.assertEqual(get_days_since_join(date(2026, 3, 1), date(2026, 3, 31)), 30)

    def test_string_dates(self):
        self.assertEqual(get_days_since_join("2026-03-01", "2026-03-16"), 15)


class TestDaysUntilDeadline(FrappeTestCase):
    """Test days remaining until 30-day deadline."""

    def test_on_join_day_30_remaining(self):
        self.assertEqual(get_days_until_deadline(date(2026, 3, 1), date(2026, 3, 1)), 30)

    def test_15_days_in_15_remaining(self):
        self.assertEqual(get_days_until_deadline(date(2026, 3, 1), date(2026, 3, 16)), 15)

    def test_on_deadline_day_zero_remaining(self):
        self.assertEqual(get_days_until_deadline(date(2026, 3, 1), date(2026, 3, 31)), 0)

    def test_one_day_overdue_is_negative(self):
        self.assertEqual(get_days_until_deadline(date(2026, 3, 1), date(2026, 4, 1)), -1)

    def test_ten_days_overdue(self):
        self.assertEqual(get_days_until_deadline(date(2026, 3, 1), date(2026, 4, 10)), -10)


class TestIsDeadlineOverdue(FrappeTestCase):
    """Test overdue flag."""

    def test_not_overdue_on_join_day(self):
        self.assertFalse(is_deadline_overdue(date(2026, 3, 1), date(2026, 3, 1)))

    def test_not_overdue_on_deadline_day(self):
        self.assertFalse(is_deadline_overdue(date(2026, 3, 1), date(2026, 3, 31)))

    def test_overdue_one_day_after_deadline(self):
        self.assertTrue(is_deadline_overdue(date(2026, 3, 1), date(2026, 4, 1)))


class TestShouldSendFirstAlert(FrappeTestCase):
    """Test first alert trigger logic."""

    def test_no_alert_on_day_13(self):
        self.assertFalse(should_send_first_alert(date(2026, 3, 1), date(2026, 3, 14)))

    def test_alert_on_day_14(self):
        self.assertTrue(should_send_first_alert(date(2026, 3, 1), date(2026, 3, 15)))

    def test_alert_on_day_20(self):
        self.assertTrue(should_send_first_alert(date(2026, 3, 1), date(2026, 3, 21)))

    def test_alert_on_day_31_overdue(self):
        self.assertTrue(should_send_first_alert(date(2026, 3, 1), date(2026, 4, 1)))


# ===========================================================================
# check_employee_tp3_status
# ===========================================================================

class TestCheckEmployeeTP3Status(FrappeTestCase):
    """Test single-employee status assessment."""

    def test_january_joiner_is_exempt(self):
        rec = _make_employee(join_date=date(2026, 1, 15), tax_year=2026)
        status = check_employee_tp3_status(rec, date(2026, 3, 1))
        self.assertFalse(status["is_mid_year_hire"])
        self.assertEqual(status["status"], STATUS_EXEMPT_JANUARY)
        self.assertEqual(status["bucket"], BUCKET_EXEMPT)
        self.assertIsNone(status["warning_message"])

    def test_mid_year_hire_with_tp3_is_ok(self):
        rec = _make_employee(join_date=date(2026, 3, 1), tax_year=2026, has_tp3=True)
        status = check_employee_tp3_status(rec, date(2026, 4, 15))
        self.assertTrue(status["is_mid_year_hire"])
        self.assertTrue(status["has_tp3"])
        self.assertEqual(status["status"], STATUS_TP3_RECEIVED)
        self.assertEqual(status["bucket"], BUCKET_RECEIVED)
        self.assertEqual(status["severity"], SEVERITY_OK)
        self.assertIsNone(status["warning_message"])
        self.assertFalse(status["should_alert"])

    def test_mid_year_hire_no_tp3_within_window(self):
        rec = _make_employee(join_date=date(2026, 3, 1), tax_year=2026, has_tp3=False)
        # 10 days after join — within window, before first alert
        status = check_employee_tp3_status(rec, date(2026, 3, 11))
        self.assertTrue(status["is_mid_year_hire"])
        self.assertFalse(status["has_tp3"])
        self.assertEqual(status["status"], STATUS_TP3_MISSING)
        self.assertEqual(status["bucket"], BUCKET_WITHIN_WINDOW)
        self.assertEqual(status["severity"], SEVERITY_OK)
        self.assertFalse(status["should_alert"])
        self.assertEqual(status["warning_message"], SALARY_SLIP_WARNING)

    def test_mid_year_hire_no_tp3_after_14_days(self):
        rec = _make_employee(join_date=date(2026, 3, 1), tax_year=2026, has_tp3=False)
        # 14 days after join — first alert fires
        status = check_employee_tp3_status(rec, date(2026, 3, 15))
        self.assertEqual(status["severity"], SEVERITY_APPROACHING)
        self.assertEqual(status["bucket"], BUCKET_ALERT_SENT)
        self.assertTrue(status["should_alert"])

    def test_mid_year_hire_no_tp3_overdue(self):
        rec = _make_employee(join_date=date(2026, 3, 1), tax_year=2026, has_tp3=False)
        # 31 days after join — overdue
        status = check_employee_tp3_status(rec, date(2026, 4, 1))
        self.assertEqual(status["severity"], SEVERITY_OVERDUE)
        self.assertEqual(status["bucket"], BUCKET_OVERDUE)
        self.assertTrue(status["should_alert"])
        self.assertTrue(status["is_overdue"])
        self.assertLess(status["days_until_deadline"], 0)

    def test_none_join_date_returns_exempt(self):
        rec = _make_employee(join_date=None, tax_year=2026)
        status = check_employee_tp3_status(rec, date(2026, 4, 1))
        self.assertFalse(status["is_mid_year_hire"])
        self.assertEqual(status["bucket"], BUCKET_EXEMPT)

    def test_deadline_field_populated(self):
        rec = _make_employee(join_date=date(2026, 4, 10), tax_year=2026, has_tp3=False)
        status = check_employee_tp3_status(rec, date(2026, 4, 20))
        self.assertEqual(status["deadline"], date(2026, 5, 10))

    def test_first_alert_date_field_populated(self):
        rec = _make_employee(join_date=date(2026, 4, 10), tax_year=2026, has_tp3=False)
        status = check_employee_tp3_status(rec, date(2026, 4, 20))
        self.assertEqual(status["first_alert_date"], date(2026, 4, 24))

    def test_string_join_date_accepted(self):
        rec = _make_employee(join_date="2026-05-01", tax_year=2026, has_tp3=False)
        status = check_employee_tp3_status(rec, date(2026, 6, 15))
        self.assertTrue(status["is_mid_year_hire"])
        self.assertTrue(status["is_overdue"])

    def test_different_year_not_mid_year(self):
        rec = _make_employee(join_date=date(2025, 6, 1), tax_year=2026)
        status = check_employee_tp3_status(rec, date(2026, 3, 1))
        self.assertFalse(status["is_mid_year_hire"])
        self.assertEqual(status["status"], STATUS_EXEMPT_NOT_MID_YEAR)


# ===========================================================================
# Salary Slip warning
# ===========================================================================

class TestGetSalarySlipTP3Warning(FrappeTestCase):
    """Test Salary Slip warning generation."""

    def test_warning_for_mid_year_no_tp3(self):
        rec = _make_employee(join_date=date(2026, 3, 1), tax_year=2026, has_tp3=False)
        warning = get_salary_slip_tp3_warning(rec, date(2026, 3, 15))
        self.assertIsNotNone(warning)
        self.assertIn("TP3", warning)

    def test_no_warning_for_mid_year_with_tp3(self):
        rec = _make_employee(join_date=date(2026, 3, 1), tax_year=2026, has_tp3=True)
        warning = get_salary_slip_tp3_warning(rec, date(2026, 3, 15))
        self.assertIsNone(warning)

    def test_no_warning_for_january_joiner(self):
        rec = _make_employee(join_date=date(2026, 1, 15), tax_year=2026, has_tp3=False)
        warning = get_salary_slip_tp3_warning(rec, date(2026, 2, 15))
        self.assertIsNone(warning)

    def test_no_warning_for_exempt_employee(self):
        rec = _make_employee(join_date=date(2025, 6, 1), tax_year=2026, has_tp3=False)
        warning = get_salary_slip_tp3_warning(rec, date(2026, 3, 1))
        self.assertIsNone(warning)


# ===========================================================================
# Batch: get_outstanding_tp3_employees
# ===========================================================================

class TestGetOutstandingTP3Employees(FrappeTestCase):
    """Test batch outstanding TP3 query."""

    def test_returns_only_overdue_employees(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 2, 1), 2026, False),  # Overdue by day 60
            _make_employee("EMP-002", "Bob", date(2026, 3, 25), 2026, False),   # Not yet overdue
            _make_employee("EMP-003", "Carol", date(2026, 1, 15), 2026, False),  # Jan exempt
            _make_employee("EMP-004", "Dave", date(2026, 2, 10), 2026, True),   # Has TP3
        ]
        result = get_outstanding_tp3_employees(employees, date(2026, 4, 5))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["employee_id"], "EMP-001")

    def test_empty_list_when_all_compliant(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 3, 1), 2026, True),
            _make_employee("EMP-002", "Bob", date(2026, 1, 15), 2026, False),  # Jan exempt
        ]
        result = get_outstanding_tp3_employees(employees, date(2026, 5, 1))
        self.assertEqual(len(result), 0)

    def test_sorted_by_most_overdue_first(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 3, 1), 2026, False),
            _make_employee("EMP-002", "Bob", date(2026, 2, 1), 2026, False),  # More overdue
        ]
        result = get_outstanding_tp3_employees(employees, date(2026, 5, 1))
        self.assertEqual(len(result), 2)
        # Bob (Feb 1) is more overdue than Alice (Mar 1)
        self.assertEqual(result[0]["employee_id"], "EMP-002")
        self.assertEqual(result[1]["employee_id"], "EMP-001")


# ===========================================================================
# Batch: get_pending_tp3_alerts
# ===========================================================================

class TestGetPendingTP3Alerts(FrappeTestCase):
    """Test batch pending alert query."""

    def test_returns_employees_needing_alert(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 3, 1), 2026, False),  # 14+ days
            _make_employee("EMP-002", "Bob", date(2026, 3, 12), 2026, False),   # <14 days
            _make_employee("EMP-003", "Carol", date(2026, 3, 1), 2026, True),   # Has TP3
        ]
        result = get_pending_tp3_alerts(employees, date(2026, 3, 16))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["employee_id"], "EMP-001")

    def test_overdue_employees_also_get_alerts(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 2, 1), 2026, False),  # Overdue
            _make_employee("EMP-002", "Bob", date(2026, 3, 1), 2026, False),    # 14+ days
        ]
        result = get_pending_tp3_alerts(employees, date(2026, 3, 20))
        self.assertEqual(len(result), 2)

    def test_empty_when_no_alerts_needed(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 3, 15), 2026, False),  # Only 5 days
        ]
        result = get_pending_tp3_alerts(employees, date(2026, 3, 20))
        self.assertEqual(len(result), 0)


# ===========================================================================
# Dashboard summary
# ===========================================================================

class TestGenerateTP3DashboardSummary(FrappeTestCase):
    """Test HR dashboard summary generation."""

    def _sample_employees(self):
        return [
            _make_employee("EMP-001", "Alice", date(2026, 2, 1), 2026, False),   # Overdue
            _make_employee("EMP-002", "Bob", date(2026, 3, 1), 2026, False),     # Alert sent (14+ days)
            _make_employee("EMP-003", "Carol", date(2026, 3, 18), 2026, False),  # Within window
            _make_employee("EMP-004", "Dave", date(2026, 3, 1), 2026, True),     # TP3 received
            _make_employee("EMP-005", "Eve", date(2026, 1, 15), 2026, False),    # Jan exempt
        ]

    def test_total_mid_year_hires(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(summary["total_mid_year_hires"], 4)  # Alice, Bob, Carol, Dave

    def test_total_tp3_received(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(summary["total_tp3_received"], 1)  # Dave

    def test_total_tp3_missing(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(summary["total_tp3_missing"], 3)  # Alice, Bob, Carol

    def test_total_overdue(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(summary["total_overdue"], 1)  # Alice

    def test_total_exempt(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(summary["total_exempt"], 1)  # Eve

    def test_compliance_rate(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        # 1 received / 4 mid-year = 25%
        self.assertEqual(summary["compliance_rate"], 25.0)

    def test_compliance_rate_all_received(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 3, 1), 2026, True),
            _make_employee("EMP-002", "Bob", date(2026, 4, 1), 2026, True),
        ]
        summary = generate_tp3_dashboard_summary(employees, date(2026, 5, 1))
        self.assertEqual(summary["compliance_rate"], 100.0)

    def test_compliance_rate_no_mid_year_is_zero(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 1, 15), 2026, False),
        ]
        summary = generate_tp3_dashboard_summary(employees, date(2026, 3, 1))
        self.assertEqual(summary["compliance_rate"], 0.0)

    def test_buckets_populated(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertIn(BUCKET_OVERDUE, summary["buckets"])
        self.assertIn(BUCKET_ALERT_SENT, summary["buckets"])
        self.assertIn(BUCKET_WITHIN_WINDOW, summary["buckets"])
        self.assertIn(BUCKET_RECEIVED, summary["buckets"])
        self.assertIn(BUCKET_EXEMPT, summary["buckets"])

    def test_overdue_employees_in_summary(self):
        summary = generate_tp3_dashboard_summary(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(len(summary["overdue_employees"]), 1)
        self.assertEqual(summary["overdue_employees"][0]["employee_id"], "EMP-001")


# ===========================================================================
# Notification building
# ===========================================================================

class TestBuildNotification(FrappeTestCase):
    """Test single notification construction."""

    def test_notification_for_approaching_employee(self):
        rec = _make_employee("EMP-001", "Alice Tan", date(2026, 3, 1), 2026, False)
        notif = build_notification(rec, date(2026, 3, 16))
        self.assertIsNotNone(notif)
        self.assertIn("Alice Tan", notif["subject"])
        self.assertIn("EMP-001", notif["subject"])
        self.assertIn("Alice Tan", notif["body"])
        self.assertIn("HR Manager", notif["recipients"])
        self.assertEqual(notif["severity"], SEVERITY_APPROACHING)
        self.assertFalse(notif["is_overdue"])

    def test_notification_for_overdue_employee(self):
        rec = _make_employee("EMP-002", "Bob Lee", date(2026, 2, 1), 2026, False)
        notif = build_notification(rec, date(2026, 3, 15))
        self.assertIsNotNone(notif)
        self.assertEqual(notif["severity"], SEVERITY_OVERDUE)
        self.assertTrue(notif["is_overdue"])
        self.assertIn("has passed", notif["body"])

    def test_no_notification_for_within_window(self):
        rec = _make_employee("EMP-003", "Carol", date(2026, 3, 10), 2026, False)
        notif = build_notification(rec, date(2026, 3, 15))
        self.assertIsNone(notif)

    def test_no_notification_for_tp3_received(self):
        rec = _make_employee("EMP-004", "Dave", date(2026, 3, 1), 2026, True)
        notif = build_notification(rec, date(2026, 4, 15))
        self.assertIsNone(notif)

    def test_no_notification_for_exempt(self):
        rec = _make_employee("EMP-005", "Eve", date(2026, 1, 15), 2026, False)
        notif = build_notification(rec, date(2026, 3, 1))
        self.assertIsNone(notif)

    def test_notification_has_deadline_field(self):
        rec = _make_employee("EMP-001", "Alice", date(2026, 3, 1), 2026, False)
        notif = build_notification(rec, date(2026, 3, 20))
        self.assertEqual(notif["deadline"], "2026-03-31")


class TestBuildBatchNotifications(FrappeTestCase):
    """Test batch notification building."""

    def test_batch_returns_only_alerts(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 2, 1), 2026, False),  # Overdue
            _make_employee("EMP-002", "Bob", date(2026, 3, 12), 2026, False),   # Within window
            _make_employee("EMP-003", "Carol", date(2026, 3, 1), 2026, True),   # Has TP3
            _make_employee("EMP-004", "Dave", date(2026, 1, 10), 2026, False),  # Jan exempt
        ]
        notifications = build_batch_notifications(employees, date(2026, 3, 20))
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["employee_id"], "EMP-001")

    def test_batch_sorted_by_deadline_proximity(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 3, 1), 2026, False),  # Alert sent
            _make_employee("EMP-002", "Bob", date(2026, 2, 1), 2026, False),    # Overdue (earlier)
        ]
        notifications = build_batch_notifications(employees, date(2026, 3, 20))
        self.assertEqual(len(notifications), 2)
        # Bob (overdue) should come first (more negative days_until_deadline)
        self.assertEqual(notifications[0]["employee_id"], "EMP-002")

    def test_empty_batch(self):
        employees = [
            _make_employee("EMP-001", "Alice", date(2026, 1, 15), 2026, False),
        ]
        notifications = build_batch_notifications(employees, date(2026, 3, 1))
        self.assertEqual(len(notifications), 0)


# ===========================================================================
# Auto-clear check
# ===========================================================================

class TestIsAlertCleared(FrappeTestCase):
    """Test alert auto-clear when TP3 is received."""

    def test_cleared_when_tp3_received(self):
        rec = _make_employee(has_tp3=True)
        self.assertTrue(is_alert_cleared(rec))

    def test_not_cleared_when_tp3_missing(self):
        rec = _make_employee(has_tp3=False)
        self.assertFalse(is_alert_cleared(rec))


# ===========================================================================
# Compliance report
# ===========================================================================

class TestGenerateComplianceReport(FrappeTestCase):
    """Test full compliance report generation."""

    def _sample_employees(self):
        return [
            _make_employee("EMP-001", "Alice", date(2026, 2, 1), 2026, False),   # Overdue
            _make_employee("EMP-002", "Bob", date(2026, 3, 1), 2026, False),     # Alert
            _make_employee("EMP-003", "Carol", date(2026, 3, 18), 2026, False),  # Within window
            _make_employee("EMP-004", "Dave", date(2026, 3, 1), 2026, True),     # Received
            _make_employee("EMP-005", "Eve", date(2026, 1, 15), 2026, False),    # Exempt
        ]

    def test_report_has_date(self):
        report = generate_compliance_report(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(report["report_date"], "2026-03-22")

    def test_report_has_summary(self):
        report = generate_compliance_report(self._sample_employees(), date(2026, 3, 22))
        self.assertIn("total_mid_year_hires", report["summary"])
        self.assertEqual(report["summary"]["total_mid_year_hires"], 4)

    def test_report_employees_sorted_by_severity(self):
        report = generate_compliance_report(self._sample_employees(), date(2026, 3, 22))
        employees = report["employees"]
        self.assertEqual(len(employees), 5)
        # First should be overdue
        self.assertEqual(employees[0]["severity"], SEVERITY_OVERDUE)

    def test_action_required_list(self):
        report = generate_compliance_report(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(len(report["action_required"]), 2)  # Alice (overdue) + Bob (alert)

    def test_section_107a_risk_list(self):
        report = generate_compliance_report(self._sample_employees(), date(2026, 3, 22))
        self.assertEqual(len(report["section_107a_risk"]), 1)  # Alice only
        self.assertEqual(report["section_107a_risk"][0]["employee_id"], "EMP-001")

    def test_empty_report(self):
        report = generate_compliance_report([], date(2026, 3, 22))
        self.assertEqual(report["summary"]["total_mid_year_hires"], 0)
        self.assertEqual(len(report["employees"]), 0)
        self.assertEqual(len(report["action_required"]), 0)

    def test_report_with_string_date(self):
        report = generate_compliance_report(self._sample_employees(), "2026-03-22")
        self.assertEqual(report["report_date"], "2026-03-22")
