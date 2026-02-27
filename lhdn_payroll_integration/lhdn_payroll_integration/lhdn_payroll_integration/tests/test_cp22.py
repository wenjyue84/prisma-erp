"""Tests for CP22/CP22A new hire and retirement notification handling.

Verifies:
- CP22 auto-creation on Employee insert with custom_requires_self_billed_invoice
- CP22A auto-creation on Employee status change to Left for age >=55
- Filing deadline calculation (30 days from joining)
- Age calculation for CP22A eligibility
- Duplicate prevention
- Overdue status check
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today, getdate
from unittest.mock import patch, MagicMock


from lhdn_payroll_integration.services.cp22_service import (
    handle_employee_after_insert,
    handle_employee_status_change,
    check_overdue_cp22,
)


class TestCP22AutoCreation(FrappeTestCase):
    """Tests for CP22 auto-creation on employee insert."""

    def _make_employee_mock(self, requires_self_billed=1, date_of_joining=None, date_of_birth=None):
        mock = MagicMock()
        mock.name = "HR-EMP-99901"
        mock.employee_name = "Test Employee CP22"
        mock.custom_requires_self_billed_invoice = requires_self_billed
        mock.date_of_joining = date_of_joining or today()
        mock.date_of_birth = date_of_birth or "1990-01-01"
        mock.get = lambda field, default=None: getattr(mock, field, default)
        return mock

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_created_when_self_billed_flag_set(self, mock_frappe):
        """CP22 should be auto-created when custom_requires_self_billed_invoice = 1."""
        mock_frappe.db.exists.return_value = False
        mock_cp22 = MagicMock()
        mock_cp22.name = "CP22-2026-00001"
        mock_cp22.filing_deadline = add_days(today(), 30)
        mock_frappe.new_doc.return_value = mock_cp22

        emp = self._make_employee_mock(requires_self_billed=1)
        handle_employee_after_insert(emp, "after_insert")

        mock_frappe.new_doc.assert_called_once_with("LHDN CP22")
        mock_cp22.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_not_created_without_self_billed_flag(self, mock_frappe):
        """CP22 should NOT be created when custom_requires_self_billed_invoice = 0."""
        emp = self._make_employee_mock(requires_self_billed=0)
        handle_employee_after_insert(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_not_duplicated(self, mock_frappe):
        """CP22 should not be duplicated for the same employee."""
        mock_frappe.db.exists.return_value = True

        emp = self._make_employee_mock(requires_self_billed=1)
        handle_employee_after_insert(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_not_created_without_date_of_joining(self, mock_frappe):
        """CP22 should not be created if employee has no date_of_joining."""
        emp = self._make_employee_mock(requires_self_billed=1, date_of_joining=None)
        emp.date_of_joining = None
        handle_employee_after_insert(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22_sets_filing_deadline_30_days(self, mock_frappe):
        """CP22 filing_deadline should be 30 days from date_of_joining."""
        mock_frappe.db.exists.return_value = False
        mock_cp22 = MagicMock()
        mock_cp22.name = "CP22-2026-00001"
        mock_cp22.filing_deadline = None
        mock_frappe.new_doc.return_value = mock_cp22

        joining = "2026-03-01"
        emp = self._make_employee_mock(requires_self_billed=1, date_of_joining=joining)
        handle_employee_after_insert(emp, "after_insert")

        self.assertEqual(mock_cp22.filing_deadline, add_days(joining, 30))


class TestCP22AAutoCreation(FrappeTestCase):
    """Tests for CP22A auto-creation when employee age >=55 is set to Left."""

    def _make_employee_mock(self, status="Left", date_of_birth="1965-06-15", relieving_date=None):
        mock = MagicMock()
        mock.name = "HR-EMP-99902"
        mock.employee_name = "Senior Employee"
        mock.status = status
        mock.date_of_birth = date_of_birth
        mock.relieving_date = relieving_date
        mock.get = lambda field, default=None: getattr(mock, field, default)
        return mock

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_created_for_employee_age_55_plus(self, mock_frappe):
        """CP22A should be auto-created when employee >=55 is set to Left."""
        mock_frappe.db.exists.return_value = False
        mock_cp22a = MagicMock()
        mock_cp22a.name = "CP22A-2026-00001"
        mock_frappe.new_doc.return_value = mock_cp22a

        # Employee born 1965-06-15, leaving in 2026 = age 60
        emp = self._make_employee_mock(status="Left", date_of_birth="1965-06-15")
        handle_employee_status_change(emp, "on_update")

        mock_frappe.new_doc.assert_called_once_with("LHDN CP22A")
        mock_cp22a.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_created_for_young_employee(self, mock_frappe):
        """CP22A should NOT be created for employee under 55."""
        # Employee born 1990-01-01, leaving in 2026 = age 36
        emp = self._make_employee_mock(status="Left", date_of_birth="1990-01-01")
        handle_employee_status_change(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_created_for_active_employee(self, mock_frappe):
        """CP22A should NOT be created when employee status is not Left."""
        emp = self._make_employee_mock(status="Active", date_of_birth="1965-06-15")
        handle_employee_status_change(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_created_without_dob(self, mock_frappe):
        """CP22A should NOT be created if date_of_birth is missing."""
        emp = self._make_employee_mock(status="Left", date_of_birth=None)
        handle_employee_status_change(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_not_duplicated(self, mock_frappe):
        """CP22A should not be duplicated for the same employee."""
        mock_frappe.db.exists.return_value = True

        emp = self._make_employee_mock(status="Left", date_of_birth="1965-06-15")
        handle_employee_status_change(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_uses_relieving_date_when_available(self, mock_frappe):
        """CP22A should use relieving_date when set, not today()."""
        mock_frappe.db.exists.return_value = False
        mock_cp22a = MagicMock()
        mock_cp22a.name = "CP22A-2026-00001"
        mock_frappe.new_doc.return_value = mock_cp22a

        emp = self._make_employee_mock(
            status="Left",
            date_of_birth="1965-06-15",
            relieving_date="2026-03-15",
        )
        handle_employee_status_change(emp, "on_update")

        mock_frappe.new_doc.assert_called_once_with("LHDN CP22A")
        self.assertEqual(mock_cp22a.cessation_date, "2026-03-15")

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_cp22a_reason_defaults_to_retirement(self, mock_frappe):
        """CP22A reason should default to Retirement."""
        mock_frappe.db.exists.return_value = False
        mock_cp22a = MagicMock()
        mock_cp22a.name = "CP22A-2026-00001"
        mock_frappe.new_doc.return_value = mock_cp22a

        emp = self._make_employee_mock(status="Left", date_of_birth="1965-06-15")
        handle_employee_status_change(emp, "on_update")

        self.assertEqual(mock_cp22a.reason, "Retirement")


class TestCP22OverdueCheck(FrappeTestCase):
    """Tests for the check_overdue_cp22 daily scheduler function."""

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_overdue_records_status_updated(self, mock_frappe):
        """Overdue CP22 records should be set to Overdue status."""
        mock_frappe.get_all.return_value = [
            {"name": "CP22-2026-00001", "employee_name": "John", "filing_deadline": "2026-02-01"},
        ]
        check_overdue_cp22()

        mock_frappe.db.set_value.assert_called_once_with(
            "LHDN CP22", "CP22-2026-00001", "status", "Overdue"
        )

    @patch("lhdn_payroll_integration.services.cp22_service.frappe")
    def test_no_overdue_records_no_updates(self, mock_frappe):
        """No updates when there are no overdue records."""
        mock_frappe.get_all.return_value = []
        check_overdue_cp22()

        mock_frappe.db.set_value.assert_not_called()
        mock_frappe.db.commit.assert_not_called()
