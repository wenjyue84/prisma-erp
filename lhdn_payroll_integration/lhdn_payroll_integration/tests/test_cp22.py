"""Tests for CP22/CP22A handling — US-033.

Tests:
1. CP22 auto-creation on Employee after_insert when custom_requires_self_billed_invoice = 1
2. CP22 NOT created when custom_requires_self_billed_invoice = 0
3. CP22 NOT created when date_of_joining is missing
4. CP22 duplicate prevention
5. CP22 filing_deadline set to 30 days after date_of_joining
6. CP22A auto-creation on Employee on_update when age >= 55 and status = Left
7. CP22A NOT created when age < 55
8. CP22A NOT created when status != Left
9. CP22A duplicate prevention
10. CP22A age_at_cessation calculation
11. check_overdue_cp22 marks overdue records
12. hooks.py registers after_insert and on_update for Employee
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch


class TestCP22AutoCreation(FrappeTestCase):
    """Test CP22 auto-creation on Employee after_insert."""

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_created_when_self_billed_required(self, mock_frappe):
        """CP22 is created when custom_requires_self_billed_invoice = 1."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_after_insert

        doc = MagicMock()
        doc.name = "HR-EMP-00099"
        doc.employee_name = "Test Employee"
        doc.date_of_joining = "2026-02-01"
        doc.date_of_birth = "1990-05-15"
        doc.get.return_value = 1  # custom_requires_self_billed_invoice

        mock_frappe.db.exists.return_value = False

        mock_cp22 = MagicMock()
        mock_frappe.new_doc.return_value = mock_cp22

        handle_employee_after_insert(doc, "after_insert")

        mock_frappe.new_doc.assert_called_once_with("LHDN CP22")
        self.assertEqual(mock_cp22.employee, "HR-EMP-00099")
        self.assertEqual(mock_cp22.date_of_joining, "2026-02-01")
        self.assertEqual(mock_cp22.status, "Pending")
        mock_cp22.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_not_created_when_self_billed_not_required(self, mock_frappe):
        """CP22 is NOT created when custom_requires_self_billed_invoice = 0."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_after_insert

        doc = MagicMock()
        doc.get.return_value = 0  # custom_requires_self_billed_invoice = 0

        handle_employee_after_insert(doc, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_not_created_when_no_joining_date(self, mock_frappe):
        """CP22 is NOT created when date_of_joining is missing."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_after_insert

        doc = MagicMock()
        doc.get.return_value = 1
        doc.date_of_joining = None

        handle_employee_after_insert(doc, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_duplicate_prevention(self, mock_frappe):
        """CP22 is NOT created if one already exists for the employee."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_after_insert

        doc = MagicMock()
        doc.name = "HR-EMP-00099"
        doc.date_of_joining = "2026-02-01"
        doc.get.return_value = 1

        mock_frappe.db.exists.return_value = True  # CP22 already exists

        handle_employee_after_insert(doc, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_filing_deadline_30_days(self, mock_frappe):
        """CP22 filing_deadline is set to 30 days after date_of_joining."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_after_insert

        doc = MagicMock()
        doc.name = "HR-EMP-00100"
        doc.employee_name = "Filing Test"
        doc.date_of_joining = "2026-02-01"
        doc.date_of_birth = "1990-01-01"
        doc.get.return_value = 1

        mock_frappe.db.exists.return_value = False

        mock_cp22 = MagicMock()
        mock_frappe.new_doc.return_value = mock_cp22

        handle_employee_after_insert(doc, "after_insert")

        # filing_deadline should be set to 30 days after joining
        self.assertEqual(mock_cp22.filing_deadline, "2026-03-03")


class TestCP22AAutoCreation(FrappeTestCase):
    """Test CP22A auto-creation on Employee on_update for age >= 55."""

    @patch("lhdn_payroll_integration.services.cp22_service.today", return_value="2026-02-27")
    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_created_for_employee_55_plus(self, mock_frappe, mock_today):
        """CP22A is created when employee age >= 55 and status = Left."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_status_change

        doc = MagicMock()
        doc.name = "HR-EMP-00200"
        doc.employee_name = "Senior Employee"
        doc.status = "Left"
        doc.date_of_birth = "1970-01-15"  # Age 56
        doc.relieving_date = "2026-02-27"

        mock_frappe.db.exists.return_value = False

        mock_cp22a = MagicMock()
        mock_frappe.new_doc.return_value = mock_cp22a

        handle_employee_status_change(doc, "on_update")

        mock_frappe.new_doc.assert_called_once_with("LHDN CP22A")
        self.assertEqual(mock_cp22a.employee, "HR-EMP-00200")
        self.assertEqual(mock_cp22a.reason, "Retirement")
        self.assertEqual(mock_cp22a.status, "Pending")
        mock_cp22a.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_created_for_young_employee(self, mock_frappe):
        """CP22A is NOT created when employee age < 55."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_status_change

        doc = MagicMock()
        doc.status = "Left"
        doc.date_of_birth = "1990-05-15"  # Age 35
        doc.relieving_date = "2026-02-27"

        handle_employee_status_change(doc, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_created_when_not_left(self, mock_frappe):
        """CP22A is NOT created when employee status != Left."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_status_change

        doc = MagicMock()
        doc.status = "Active"
        doc.date_of_birth = "1970-01-15"

        handle_employee_status_change(doc, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_created_when_no_dob(self, mock_frappe):
        """CP22A is NOT created when date_of_birth is missing."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_status_change

        doc = MagicMock()
        doc.status = "Left"
        doc.date_of_birth = None

        handle_employee_status_change(doc, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.today", return_value="2026-02-27")
    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_duplicate_prevention(self, mock_frappe, mock_today):
        """CP22A is NOT created if one already exists for the employee."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_status_change

        doc = MagicMock()
        doc.name = "HR-EMP-00200"
        doc.status = "Left"
        doc.date_of_birth = "1970-01-15"
        doc.relieving_date = "2026-02-27"

        mock_frappe.db.exists.return_value = True

        handle_employee_status_change(doc, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.today", return_value="2026-02-27")
    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_age_calculation(self, mock_frappe, mock_today):
        """CP22A correctly calculates age at cessation (birthday not yet passed this year)."""
        from lhdn_payroll_integration.services.cp22_service import handle_employee_status_change

        doc = MagicMock()
        doc.name = "HR-EMP-00201"
        doc.employee_name = "Age Test"
        doc.status = "Left"
        doc.date_of_birth = "1971-06-15"  # Birthday in June, cessation in Feb → age 54, not 55
        doc.relieving_date = "2026-02-27"

        mock_frappe.db.exists.return_value = False

        handle_employee_status_change(doc, "on_update")

        # Age 54 (birthday not yet passed) → should NOT create CP22A
        mock_frappe.new_doc.assert_not_called()


class TestCP22OverdueCheck(FrappeTestCase):
    """Test check_overdue_cp22 scheduler function."""

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_overdue_records_marked(self, mock_frappe):
        """Overdue CP22 records have status updated to Overdue."""
        from lhdn_payroll_integration.services.cp22_service import check_overdue_cp22

        mock_frappe.get_all.return_value = [
            {"name": "CP22-2026-001", "employee_name": "Late Filer", "filing_deadline": "2026-01-15"},
        ]

        check_overdue_cp22()

        mock_frappe.db.set_value.assert_called_once_with(
            "LHDN CP22", "CP22-2026-001", "status", "Overdue"
        )
        mock_frappe.db.commit.assert_called_once()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_no_overdue_records_no_commit(self, mock_frappe):
        """No commit when there are no overdue records."""
        from lhdn_payroll_integration.services.cp22_service import check_overdue_cp22

        mock_frappe.get_all.return_value = []

        check_overdue_cp22()

        mock_frappe.db.set_value.assert_not_called()
        mock_frappe.db.commit.assert_not_called()


class TestCP22HooksRegistration(FrappeTestCase):
    """Test that hooks.py correctly registers Employee events for CP22."""

    def test_employee_after_insert_registered(self):
        """hooks.py registers after_insert for Employee → cp22_service."""
        from lhdn_payroll_integration.hooks import doc_events

        employee_events = doc_events.get("Employee", {})
        after_insert = employee_events.get("after_insert", "")
        self.assertIn("cp22_service.handle_employee_after_insert", after_insert)

    def test_employee_on_update_includes_cp22(self):
        """hooks.py registers on_update for Employee including cp22_service."""
        from lhdn_payroll_integration.hooks import doc_events

        employee_events = doc_events.get("Employee", {})
        on_update = employee_events.get("on_update", [])
        # on_update is a list with both cp21 and cp22 handlers
        self.assertIsInstance(on_update, list)
        found = any("cp22_service.handle_employee_status_change" in handler for handler in on_update)
        self.assertTrue(found, "cp22_service.handle_employee_status_change not in on_update list")

    def test_daily_scheduler_includes_overdue_check(self):
        """hooks.py registers daily scheduler for check_overdue_cp22."""
        from lhdn_payroll_integration.hooks import scheduler_events

        daily = scheduler_events.get("daily", [])
        found = any("cp22_service.check_overdue_cp22" in handler for handler in daily)
        self.assertTrue(found, "check_overdue_cp22 not in daily scheduler")
