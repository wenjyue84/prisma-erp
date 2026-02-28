"""Tests for CP107 Foreign Employee Tax Clearance Workflow.

Verifies:
- CP107 auto-creation when foreign worker status set to Left
- CP107 not created for local (non-foreign) employees
- CP107 not created when employee status is not Left
- CP107 not duplicated for same employee with open record
- Salary Slip warning triggered for foreign employee with open CP107
- Salary Slip warning NOT shown when no open CP107 exists
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.cp107_service import (
    handle_foreign_employee_left,
    get_open_cp107_for_employee,
    check_salary_slip_cp107_warning,
)


def _make_employee_mock(status="Left", is_foreign=1, relieving_date=None, name="HR-EMP-CP107-001"):
    """Helper: build a mock Employee doc."""
    mock = MagicMock()
    mock.name = name
    mock.employee_name = "Test Foreign Worker"
    mock.status = status
    mock.custom_is_foreign_worker = is_foreign
    mock.relieving_date = relieving_date
    mock.get = lambda field, default=None: getattr(mock, field, default)
    return mock


def _make_salary_slip_mock(employee="HR-EMP-CP107-001", employee_name="Test Foreign Worker"):
    """Helper: build a mock Salary Slip doc."""
    mock = MagicMock()
    mock.employee = employee
    mock.employee_name = employee_name
    return mock


class TestCP107AutoCreation(FrappeTestCase):
    """Tests for CP107 auto-creation on foreign employee termination."""

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_cp107_created_on_foreign_worker_termination(self, mock_frappe):
        """CP107 should be auto-created when a foreign worker status is set to Left."""
        mock_frappe.db.exists.return_value = None
        mock_cp107 = MagicMock()
        mock_cp107.name = "CP107-2026-00001"
        mock_frappe.new_doc.return_value = mock_cp107

        emp = _make_employee_mock(status="Left", is_foreign=1)
        handle_foreign_employee_left(emp, "on_update")

        mock_frappe.new_doc.assert_called_once_with("LHDN CP107")
        mock_cp107.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_cp107_not_created_for_local_employee(self, mock_frappe):
        """CP107 should NOT be created for employees who are not foreign workers."""
        emp = _make_employee_mock(status="Left", is_foreign=0)
        handle_foreign_employee_left(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_cp107_not_created_when_status_not_left(self, mock_frappe):
        """CP107 should NOT be created when employee status is still Active."""
        emp = _make_employee_mock(status="Active", is_foreign=1)
        handle_foreign_employee_left(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_cp107_not_duplicated_for_same_employee(self, mock_frappe):
        """CP107 should not be duplicated when an open record already exists."""
        mock_frappe.db.exists.return_value = "CP107-2026-00001"

        emp = _make_employee_mock(status="Left", is_foreign=1)
        handle_foreign_employee_left(emp, "on_update")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_cp107_uses_relieving_date_when_set(self, mock_frappe):
        """CP107 last_working_date should use employee relieving_date when available."""
        mock_frappe.db.exists.return_value = None
        mock_cp107 = MagicMock()
        mock_cp107.name = "CP107-2026-00002"
        mock_frappe.new_doc.return_value = mock_cp107

        emp = _make_employee_mock(status="Left", is_foreign=1, relieving_date="2026-03-31")
        handle_foreign_employee_left(emp, "on_update")

        self.assertEqual(mock_cp107.last_working_date, "2026-03-31")

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_cp107_status_set_to_draft(self, mock_frappe):
        """CP107 should be created with status = Draft."""
        mock_frappe.db.exists.return_value = None
        mock_cp107 = MagicMock()
        mock_cp107.name = "CP107-2026-00003"
        mock_frappe.new_doc.return_value = mock_cp107

        emp = _make_employee_mock(status="Left", is_foreign=1)
        handle_foreign_employee_left(emp, "on_update")

        self.assertEqual(mock_cp107.status, "Draft")


class TestCP107SalarySlipWarning(FrappeTestCase):
    """Tests for Salary Slip warning when foreign employee has open CP107."""

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_warning_shown_for_foreign_employee_with_open_cp107(self, mock_frappe):
        """Warning should be shown when a foreign employee has an open CP107."""
        mock_frappe.db.get_value.side_effect = [1, "CP107-2026-00001"]

        slip = _make_salary_slip_mock()
        check_salary_slip_cp107_warning(slip, "validate")

        mock_frappe.msgprint.assert_called_once()
        call_kwargs = mock_frappe.msgprint.call_args
        # Verify the warning mentions the CP107 record
        msg_content = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("msg", "")
        self.assertIn("CP107-2026-00001", msg_content)

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_no_warning_for_local_employee(self, mock_frappe):
        """No warning when employee is not a foreign worker."""
        mock_frappe.db.get_value.return_value = 0

        slip = _make_salary_slip_mock()
        check_salary_slip_cp107_warning(slip, "validate")

        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_no_warning_when_no_open_cp107(self, mock_frappe):
        """No warning when foreign employee has no open CP107 (already cleared)."""
        mock_frappe.db.get_value.side_effect = [1, None]

        slip = _make_salary_slip_mock()
        check_salary_slip_cp107_warning(slip, "validate")

        mock_frappe.msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_no_warning_when_no_employee_on_slip(self, mock_frappe):
        """No warning when Salary Slip has no employee set."""
        slip = _make_salary_slip_mock(employee=None)
        slip.employee = None

        check_salary_slip_cp107_warning(slip, "validate")

        mock_frappe.db.get_value.assert_not_called()


class TestGetOpenCP107(FrappeTestCase):
    """Tests for get_open_cp107_for_employee utility."""

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_returns_cp107_name_when_open_record_exists(self, mock_frappe):
        """Should return the CP107 doc name when an open record exists."""
        mock_frappe.db.get_value.return_value = "CP107-2026-00001"

        result = get_open_cp107_for_employee("HR-EMP-001")

        self.assertEqual(result, "CP107-2026-00001")

    @patch("lhdn_payroll_integration.services.cp107_service.frappe")
    def test_returns_none_when_no_open_record(self, mock_frappe):
        """Should return None when no open CP107 exists."""
        mock_frappe.db.get_value.return_value = None

        result = get_open_cp107_for_employee("HR-EMP-001")

        self.assertIsNone(result)
