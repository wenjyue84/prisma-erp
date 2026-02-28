"""Tests for US-070: Foreign Worker Levy Tracking.

Covers:
  - Report shows correct levy status (Paid / Overdue / Due Soon / Upcoming)
  - Overdue detection logic (is_levy_overdue_or_due_soon)
  - _levy_status helper
  - get_data returns correct rows for foreign workers
  - Paid levy lookup from Foreign Worker Levy Payment
"""
from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from lhdn_payroll_integration.lhdn_payroll_integration.report.foreign_worker_levy.foreign_worker_levy import (
    _levy_status,
    get_columns,
    get_data,
    execute,
)
from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import (
    is_levy_overdue_or_due_soon,
    check_overdue_fw_levy,
)

# Pre-compute test dates at module load time — outside all patches so frappe.today() works normally
_TODAY = today()
_DUE_PAST = add_days(_TODAY, -5)       # overdue
_DUE_SOON = add_days(_TODAY, 15)       # due within 30 days
_DUE_FUTURE = add_days(_TODAY, 60)     # upcoming
_DUE_YESTERDAY = add_days(_TODAY, -1)  # overdue
_DUE_TODAY = _TODAY
_DUE_30D = add_days(_TODAY, 30)        # boundary — due soon
_DUE_31D = add_days(_TODAY, 31)        # beyond window — upcoming

_REPORT_MODULE = (
    "lhdn_payroll_integration.lhdn_payroll_integration"
    ".report.foreign_worker_levy.foreign_worker_levy"
)
_SERVICE_MODULE = (
    "lhdn_payroll_integration.lhdn_payroll_integration"
    ".services.fw_levy_service"
)


class TestLevyStatusHelper(FrappeTestCase):
    """Unit tests for the _levy_status() helper."""

    def test_paid_when_paid_amount_ge_levy_rate(self):
        status = _levy_status(_DUE_PAST, paid_amount=500.0, levy_rate=410.0)
        self.assertEqual(status, "Paid")

    def test_overdue_when_due_date_in_past_and_unpaid(self):
        status = _levy_status(_DUE_PAST, paid_amount=0, levy_rate=410.0)
        self.assertEqual(status, "Overdue")

    def test_due_soon_when_due_within_30_days(self):
        status = _levy_status(_DUE_SOON, paid_amount=0, levy_rate=410.0)
        self.assertEqual(status, "Due Soon")

    def test_upcoming_when_due_after_30_days(self):
        status = _levy_status(_DUE_FUTURE, paid_amount=0, levy_rate=410.0)
        self.assertEqual(status, "Upcoming")

    def test_not_set_when_no_due_date(self):
        status = _levy_status(None, paid_amount=0, levy_rate=410.0)
        self.assertEqual(status, "Not Set")

    def test_paid_exact_amount_matches(self):
        """Paying exactly the levy rate counts as paid."""
        status = _levy_status(_DUE_PAST, paid_amount=410.0, levy_rate=410.0)
        self.assertEqual(status, "Paid")


class TestIsLevyOverdueOrDueSoon(FrappeTestCase):
    """Unit tests for the is_levy_overdue_or_due_soon() service helper."""

    def test_overdue_returns_true(self):
        self.assertTrue(is_levy_overdue_or_due_soon(_DUE_YESTERDAY))

    def test_today_returns_true(self):
        self.assertTrue(is_levy_overdue_or_due_soon(_DUE_TODAY))

    def test_within_window_returns_true(self):
        self.assertTrue(is_levy_overdue_or_due_soon(_DUE_SOON))

    def test_at_boundary_returns_true(self):
        self.assertTrue(is_levy_overdue_or_due_soon(_DUE_30D))

    def test_beyond_window_returns_false(self):
        self.assertFalse(is_levy_overdue_or_due_soon(_DUE_31D))

    def test_none_date_returns_false(self):
        self.assertFalse(is_levy_overdue_or_due_soon(None))

    def test_custom_window(self):
        due_5d = add_days(_TODAY, 5)
        due_10d = add_days(_TODAY, 10)
        self.assertTrue(is_levy_overdue_or_due_soon(due_5d, days=7))
        self.assertFalse(is_levy_overdue_or_due_soon(due_10d, days=7))


class TestGetColumns(FrappeTestCase):
    """get_columns() returns expected column set."""

    def test_column_fieldnames_present(self):
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("employee", fieldnames)
        self.assertIn("levy_due_date", fieldnames)
        self.assertIn("levy_status", fieldnames)
        self.assertIn("paid_amount", fieldnames)

    def test_returns_list(self):
        self.assertIsInstance(get_columns(), list)
        self.assertGreater(len(get_columns()), 0)


class TestGetData(FrappeTestCase):
    """get_data() returns correct rows based on mocked helper functions."""

    def _mock_employees(self):
        return [
            {
                "employee": "EMP-001",
                "employee_name": "Ahmad Rizal",
                "nationality_code": "BD",
                "levy_rate": 410.0,
                "levy_due_date": _DUE_PAST,
                "receipt_ref": "",
            },
            {
                "employee": "EMP-002",
                "employee_name": "Jose Santos",
                "nationality_code": "PH",
                "levy_rate": 1200.0,
                "levy_due_date": _DUE_SOON,
                "receipt_ref": "RCPT-2025-001",
            },
            {
                "employee": "EMP-003",
                "employee_name": "Priya Nair",
                "nationality_code": "IN",
                "levy_rate": 800.0,
                "levy_due_date": _DUE_FUTURE,
                "receipt_ref": "",
            },
        ]

    @patch(f"{_REPORT_MODULE}._get_paid_levies")
    @patch(f"{_REPORT_MODULE}._get_employees")
    def test_get_data_returns_correct_statuses(self, mock_emp, mock_paid):
        mock_emp.return_value = self._mock_employees()
        mock_paid.return_value = {"EMP-002": {"paid_amount": 1200.0, "payment_date": "2025-01-15"}}

        rows = get_data({"company": "Test Company", "year": 2025})

        self.assertEqual(len(rows), 3)
        statuses = {r["employee"]: r["levy_status"] for r in rows}
        self.assertEqual(statuses["EMP-001"], "Overdue")
        self.assertEqual(statuses["EMP-002"], "Paid")
        self.assertEqual(statuses["EMP-003"], "Upcoming")

    @patch(f"{_REPORT_MODULE}._get_paid_levies")
    @patch(f"{_REPORT_MODULE}._get_employees")
    def test_get_data_no_company_returns_empty(self, mock_emp, mock_paid):
        rows = get_data({"company": "", "year": 2025})
        self.assertEqual(rows, [])
        mock_emp.assert_not_called()

    @patch(f"{_REPORT_MODULE}._get_paid_levies")
    @patch(f"{_REPORT_MODULE}._get_employees")
    def test_get_data_no_year_returns_empty(self, mock_emp, mock_paid):
        rows = get_data({"company": "Test Company", "year": None})
        self.assertEqual(rows, [])
        mock_emp.assert_not_called()

    @patch(f"{_REPORT_MODULE}._get_paid_levies")
    @patch(f"{_REPORT_MODULE}._get_employees")
    def test_get_data_empty_employees(self, mock_emp, mock_paid):
        mock_emp.return_value = []
        mock_paid.return_value = {}
        rows = get_data({"company": "Test Company", "year": 2025})
        self.assertEqual(rows, [])

    @patch(f"{_REPORT_MODULE}._get_paid_levies")
    @patch(f"{_REPORT_MODULE}._get_employees")
    def test_get_data_due_soon_status(self, mock_emp, mock_paid):
        mock_emp.return_value = [
            {
                "employee": "EMP-999",
                "employee_name": "Worker X",
                "nationality_code": "ID",
                "levy_rate": 600.0,
                "levy_due_date": _DUE_SOON,
                "receipt_ref": "",
            }
        ]
        mock_paid.return_value = {}
        rows = get_data({"company": "Test Company", "year": 2025})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["levy_status"], "Due Soon")


class TestExecute(FrappeTestCase):
    """execute() returns (columns, data) tuple."""

    @patch(f"{_REPORT_MODULE}.get_data")
    def test_execute_returns_tuple(self, mock_get_data):
        mock_get_data.return_value = []
        cols, data = execute({"company": "Test", "year": 2025})
        self.assertIsInstance(cols, list)
        self.assertIsInstance(data, list)


class TestCheckOverdueFwLevy(FrappeTestCase):
    """check_overdue_fw_levy() scheduler task — unit test with mocks."""

    @patch(f"{_SERVICE_MODULE}._get_overdue_employees")
    def test_no_employees_returns_early(self, mock_overdue):
        mock_overdue.return_value = []
        check_overdue_fw_levy()  # must not raise

    @patch(f"{_SERVICE_MODULE}._get_hr_manager_emails")
    @patch(f"{_SERVICE_MODULE}.frappe.sendmail")
    @patch(f"{_SERVICE_MODULE}._get_overdue_employees")
    def test_overdue_employees_sends_email(self, mock_overdue, mock_mail, mock_emails):
        mock_overdue.return_value = [
            {
                "employee": "EMP-001",
                "employee_name": "Ahmad Rizal",
                "company": "Test Co",
                "levy_due_date": _DUE_PAST,
                "levy_rate": 410.0,
            }
        ]
        mock_emails.return_value = ["hr@test.com"]
        check_overdue_fw_levy()
        mock_mail.assert_called_once()
        call_kwargs = mock_mail.call_args[1]
        self.assertIn("hr@test.com", call_kwargs["recipients"])

    @patch(f"{_SERVICE_MODULE}._get_hr_manager_emails")
    @patch(f"{_SERVICE_MODULE}.frappe.sendmail")
    @patch(f"{_SERVICE_MODULE}._get_overdue_employees")
    def test_due_soon_employees_sends_email(self, mock_overdue, mock_mail, mock_emails):
        mock_overdue.return_value = [
            {
                "employee": "EMP-002",
                "employee_name": "Jose Santos",
                "company": "Test Co",
                "levy_due_date": _DUE_SOON,
                "levy_rate": 1200.0,
            }
        ]
        mock_emails.return_value = ["hr@test.com"]
        check_overdue_fw_levy()
        mock_mail.assert_called_once()
