"""Tests for US-114: CP22 Submission Tracking on Employee DocType.

Covers:
1. Employee custom_cp22_submission_status field exists and defaults to Pending
2. check_pending_cp22_submissions creates ToDo at 25-day alert window
3. check_pending_cp22_submissions creates escalation ToDo at 28+ days
4. Duplicate ToDo prevention
5. Submitted employees excluded from alerts
6. Not Required employees excluded from alerts
7. Company custom_mytax_employer_rep_name field exists
8. Daily scheduler registered in hooks.py
9. Pending CP22 Submissions report exists
10. get_pending_cp22_employees helper returns correct data

NOTE on mock call order for check_pending_cp22_submissions:
  get_all call sequence:
    0 → pending_alert (Employee 25-day window)
    for each alert_emp:
      1 → dedup check (ToDo LIKE query)
    N → pending_escalate (Employee 28+ day query)
    for each escalate_emp:
      N+1 → dedup check (ToDo LIKE query)
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch


class TestCP22CustomFields(FrappeTestCase):
    """Test that custom fields exist on Employee and Company."""

    def test_employee_cp22_submission_status_field_exists(self):
        """Employee has custom_cp22_submission_status field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Employee", "fieldname": "custom_cp22_submission_status"},
            ),
            "custom_cp22_submission_status field missing from Employee",
        )

    def test_employee_cp22_status_is_select_with_correct_options(self):
        """custom_cp22_submission_status is Select with Pending/Submitted/Not Required."""
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_cp22_submission_status"},
            ["fieldtype", "options", "default"],
            as_dict=True,
        )
        self.assertEqual(field.fieldtype, "Select")
        options = [o.strip() for o in (field.options or "").split("\n") if o.strip()]
        self.assertIn("Pending", options)
        self.assertIn("Submitted", options)
        self.assertIn("Not Required", options)
        self.assertEqual(field.default, "Pending")

    def test_employee_cp22_submission_date_field_exists(self):
        """Employee has custom_cp22_submission_date Date field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Employee", "fieldname": "custom_cp22_submission_date"},
            )
        )

    def test_employee_cp22_reference_number_field_exists(self):
        """Employee has custom_cp22_reference_number Data field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Employee", "fieldname": "custom_cp22_reference_number"},
            )
        )

    def test_employee_cp22_not_required_reason_field_exists(self):
        """Employee has custom_cp22_not_required_reason Small Text field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Employee", "fieldname": "custom_cp22_not_required_reason"},
            )
        )

    def test_company_mytax_employer_rep_name_field_exists(self):
        """Company has custom_mytax_employer_rep_name Data field."""
        self.assertTrue(
            frappe.db.exists(
                "Custom Field",
                {"dt": "Company", "fieldname": "custom_mytax_employer_rep_name"},
            ),
            "custom_mytax_employer_rep_name field missing from Company",
        )


class TestCP22DailyCheck(FrappeTestCase):
    """Test check_pending_cp22_submissions daily scheduler function.

    get_all call order in the service:
      0: Employee pending_alert (25-day window)
      1: ToDo dedup check for each alert employee  (before escalation query)
      N: Employee pending_escalate (28+ days)
      N+1: ToDo dedup check for each escalate employee
    """

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_alert_created_for_employee_at_25_days(self, mock_today, mock_frappe):
        """Creates HR User ToDo for employee hired 25 days ago with Pending status."""
        from lhdn_payroll_integration.services.cp22_tracking_service import check_pending_cp22_submissions

        mock_frappe.utils.add_days = frappe.utils.add_days
        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.utils.date_diff = frappe.utils.date_diff

        # Employee hired 25 days before 2026-03-01 = 2026-02-04
        alert_emp = {
            "name": "HR-EMP-0025",
            "employee_name": "New Hire",
            "date_of_joining": "2026-02-04",
            "company": "Test Co",
        }

        # Call order:
        # 0 → pending_alert → [alert_emp]
        # 1 → dedup check for alert_emp → [] (no existing todo)
        # 2 → pending_escalate → []
        mock_frappe.get_all.side_effect = [
            [alert_emp],  # 0: alert window
            [],           # 1: dedup for alert_emp
            [],           # 2: escalate window
        ]
        mock_todo = MagicMock()
        mock_frappe.get_doc.return_value = mock_todo

        check_pending_cp22_submissions()

        mock_frappe.get_doc.assert_called_once()
        todo_args = mock_frappe.get_doc.call_args[0][0]
        self.assertEqual(todo_args["doctype"], "ToDo")
        self.assertEqual(todo_args["reference_name"], "HR-EMP-0025")
        self.assertEqual(todo_args["role"], "HR User")
        self.assertIn("[CP22-PENDING]", todo_args["description"])
        self.assertEqual(todo_args["priority"], "Medium")
        mock_frappe.db.commit.assert_called_once()

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_escalation_created_at_28_days(self, mock_today, mock_frappe):
        """Creates HR Manager ToDo for employee hired 28+ days ago with Pending status."""
        from lhdn_payroll_integration.services.cp22_tracking_service import check_pending_cp22_submissions

        mock_frappe.utils.add_days = frappe.utils.add_days
        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.utils.date_diff = frappe.utils.date_diff

        # Employee hired 28 days before 2026-03-01 = 2026-02-01
        escalate_emp = {
            "name": "HR-EMP-0028",
            "employee_name": "Overdue Hire",
            "date_of_joining": "2026-02-01",
            "company": "Test Co",
        }

        # Call order:
        # 0 → pending_alert → [] (no alert-window employees)
        # 1 → pending_escalate → [escalate_emp]
        # 2 → dedup for escalate_emp → []
        mock_frappe.get_all.side_effect = [
            [],              # 0: alert window empty
            [escalate_emp],  # 1: escalate window
            [],              # 2: dedup for escalate_emp
        ]
        mock_todo = MagicMock()
        mock_frappe.get_doc.return_value = mock_todo

        check_pending_cp22_submissions()

        mock_frappe.get_doc.assert_called_once()
        todo_args = mock_frappe.get_doc.call_args[0][0]
        self.assertEqual(todo_args["doctype"], "ToDo")
        self.assertEqual(todo_args["reference_name"], "HR-EMP-0028")
        self.assertEqual(todo_args["role"], "HR Manager")
        self.assertIn("[CP22-ESCALATION]", todo_args["description"])
        self.assertEqual(todo_args["priority"], "High")

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_no_duplicate_todos_created(self, mock_today, mock_frappe):
        """Does not create a ToDo if one already exists for the same employee and marker."""
        from lhdn_payroll_integration.services.cp22_tracking_service import check_pending_cp22_submissions

        mock_frappe.utils.add_days = frappe.utils.add_days
        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.utils.date_diff = frappe.utils.date_diff

        alert_emp = {
            "name": "HR-EMP-0025",
            "employee_name": "New Hire",
            "date_of_joining": "2026-02-04",
            "company": "Test Co",
        }

        # Call order:
        # 0 → pending_alert → [alert_emp]
        # 1 → dedup for alert_emp → [existing_todo] → dedup fires, no get_doc
        # 2 → pending_escalate → []
        mock_frappe.get_all.side_effect = [
            [alert_emp],                 # 0: alert window
            [{"name": "TODO-00001"}],    # 1: dedup → existing todo found
            [],                          # 2: escalate window empty
        ]

        check_pending_cp22_submissions()

        # get_doc for ToDo should NOT be called (dedup blocked it)
        mock_frappe.get_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_no_commit_when_no_pending(self, mock_today, mock_frappe):
        """db.commit is not called when no pending employees found."""
        from lhdn_payroll_integration.services.cp22_tracking_service import check_pending_cp22_submissions

        mock_frappe.utils.add_days = frappe.utils.add_days
        mock_frappe.utils.getdate = frappe.utils.getdate

        mock_frappe.get_all.side_effect = [
            [],   # 0: alert window
            [],   # 1: escalate window
        ]

        check_pending_cp22_submissions()

        mock_frappe.db.commit.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_submitted_employees_excluded(self, mock_today, mock_frappe):
        """Both queries filter on custom_cp22_submission_status = Pending."""
        from lhdn_payroll_integration.services.cp22_tracking_service import check_pending_cp22_submissions

        mock_frappe.utils.add_days = frappe.utils.add_days
        mock_frappe.utils.getdate = frappe.utils.getdate

        mock_frappe.get_all.side_effect = [[], []]

        check_pending_cp22_submissions()

        # Verify both Employee get_all calls use Pending filter
        employee_calls = [
            c for c in mock_frappe.get_all.call_args_list
            if c[0][0] == "Employee"
        ]
        for call_args in employee_calls:
            filters = call_args[1].get("filters", {}) if call_args[1] else {}
            self.assertIn("custom_cp22_submission_status", filters)
            self.assertEqual(filters["custom_cp22_submission_status"], "Pending")


class TestGetPendingCp22Employees(FrappeTestCase):
    """Test get_pending_cp22_employees helper (used by report)."""

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_returns_pending_employees_with_deadline_info(self, mock_today, mock_frappe):
        """Returns list with days_since_hire and days_remaining computed."""
        from lhdn_payroll_integration.services.cp22_tracking_service import get_pending_cp22_employees

        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.today = lambda: "2026-03-01"

        # Employee hired 10 days ago (2026-02-19)
        mock_frappe.get_all.return_value = [
            {
                "name": "HR-EMP-0010",
                "employee_name": "Ten Days In",
                "company": "Acme",
                "date_of_joining": "2026-02-19",
                "custom_cp22_submission_status": "Pending",
            }
        ]

        result = get_pending_cp22_employees()

        self.assertEqual(len(result), 1)
        emp = result[0]
        self.assertEqual(emp["employee"], "HR-EMP-0010")
        self.assertEqual(emp["days_since_hire"], 10)
        self.assertEqual(emp["days_remaining"], 20)
        self.assertEqual(emp["status"], "Pending")

    @patch("lhdn_payroll_integration.services.cp22_tracking_service.frappe")
    @patch("lhdn_payroll_integration.services.cp22_tracking_service.today", return_value="2026-03-01")
    def test_sorted_by_days_remaining(self, mock_today, mock_frappe):
        """Results are sorted by days_remaining ascending (most urgent first)."""
        from lhdn_payroll_integration.services.cp22_tracking_service import get_pending_cp22_employees

        mock_frappe.utils.getdate = frappe.utils.getdate
        mock_frappe.utils.date_diff = frappe.utils.date_diff
        mock_frappe.utils.today = lambda: "2026-03-01"

        mock_frappe.get_all.return_value = [
            {
                "name": "HR-EMP-0005",
                "employee_name": "Early Bird",
                "company": "Acme",
                "date_of_joining": "2026-02-24",  # 6 days ago → 24 remaining
                "custom_cp22_submission_status": "Pending",
            },
            {
                "name": "HR-EMP-0025",
                "employee_name": "Late One",
                "company": "Acme",
                "date_of_joining": "2026-02-04",  # 25 days ago → 5 remaining
                "custom_cp22_submission_status": "Pending",
            },
        ]

        result = get_pending_cp22_employees()

        # Late One (5 days remaining) should be first (sorted ascending)
        self.assertEqual(result[0]["employee"], "HR-EMP-0025")
        self.assertEqual(result[1]["employee"], "HR-EMP-0005")


class TestCP22SchedulerRegistration(FrappeTestCase):
    """Test that hooks.py registers the daily scheduler for CP22 tracking."""

    def test_daily_scheduler_includes_cp22_check(self):
        """hooks.py registers check_pending_cp22_submissions in daily scheduler."""
        from lhdn_payroll_integration.hooks import scheduler_events

        daily = scheduler_events.get("daily", [])
        found = any(
            "cp22_tracking_service.check_pending_cp22_submissions" in handler
            for handler in daily
        )
        self.assertTrue(
            found,
            "cp22_tracking_service.check_pending_cp22_submissions not found in daily scheduler",
        )


class TestPendingCp22SubmissionsReport(FrappeTestCase):
    """Test that the Pending CP22 Submissions report exists and is importable."""

    def test_report_exists_in_db(self):
        """Pending CP22 Submissions report is registered in Report doctype."""
        self.assertTrue(
            frappe.db.exists("Report", "Pending CP22 Submissions"),
            "Report 'Pending CP22 Submissions' not found — run bench migrate",
        )

    def test_report_module_is_correct(self):
        """Report is under LHDN Payroll Integration module."""
        module = frappe.db.get_value("Report", "Pending CP22 Submissions", "module")
        self.assertEqual(module, "LHDN Payroll Integration")

    def test_report_execute_is_importable(self):
        """pending_cp22_submissions.execute() is importable without errors."""
        from lhdn_payroll_integration.report.pending_cp22_submissions.pending_cp22_submissions import (
            execute,
        )
        self.assertTrue(callable(execute))

    def test_get_columns_returns_required_columns(self):
        """Report columns include employee, days_since_hire, days_remaining, status."""
        from lhdn_payroll_integration.report.pending_cp22_submissions.pending_cp22_submissions import (
            get_columns,
        )

        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("employee", fieldnames)
        self.assertIn("days_since_hire", fieldnames)
        self.assertIn("days_remaining", fieldnames)
        self.assertIn("status", fieldnames)
