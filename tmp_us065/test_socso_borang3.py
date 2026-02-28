"""Tests for SOCSO Borang 3 new employee notification (PERKESO).

Verifies:
- Auto-creation on eligible employee (Malaysian/PR, Permanent/Contract)
- No auto-creation for foreign workers
- No auto-creation for non-Permanent/Contract employment types
- Filing deadline set to 30 days from date_of_joining
- Duplicate prevention
- Overdue status update via scheduler function
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.socso_service import (
    handle_new_employee_socso,
    check_overdue_socso_borang3,
)


class TestSOCSOBorang3AutoCreation(FrappeTestCase):
    """Tests for SOCSO Borang 3 auto-creation on eligible employee insert."""

    def _make_employee_mock(
        self,
        is_foreign_worker=0,
        employment_type="Permanent",
        date_of_joining=None,
    ):
        mock = MagicMock()
        mock.name = "HR-EMP-99910"
        mock.employee_name = "Test Employee SOCSO"
        mock.custom_is_foreign_worker = is_foreign_worker
        mock.custom_employment_type = employment_type
        mock.date_of_joining = date_of_joining or today()
        mock.get = lambda field, default=None: getattr(mock, field, default)
        return mock

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_created_for_permanent_employee(self, mock_frappe):
        """SOCSO Borang 3 should be created for Permanent Malaysian employee."""
        mock_frappe.db.exists.return_value = False
        mock_b3 = MagicMock()
        mock_b3.name = "SOCSO-B3-2026-00001"
        mock_b3.filing_deadline = add_days(today(), 30)
        mock_frappe.new_doc.return_value = mock_b3

        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Permanent")
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_called_once_with("SOCSO Borang 3")
        mock_b3.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_created_for_contract_employee(self, mock_frappe):
        """SOCSO Borang 3 should be created for Contract Malaysian employee."""
        mock_frappe.db.exists.return_value = False
        mock_b3 = MagicMock()
        mock_b3.name = "SOCSO-B3-2026-00002"
        mock_b3.filing_deadline = add_days(today(), 30)
        mock_frappe.new_doc.return_value = mock_b3

        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Contract")
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_called_once_with("SOCSO Borang 3")
        mock_b3.insert.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_not_created_for_foreign_worker(self, mock_frappe):
        """SOCSO Borang 3 should NOT be created for foreign workers (not eligible for Cat II)."""
        emp = self._make_employee_mock(is_foreign_worker=1, employment_type="Permanent")
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_not_created_for_intern(self, mock_frappe):
        """SOCSO Borang 3 should NOT be created for Intern employment type."""
        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Intern")
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_not_created_for_part_time(self, mock_frappe):
        """SOCSO Borang 3 should NOT be created for Part-time employment type."""
        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Part-time")
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_not_created_without_date_of_joining(self, mock_frappe):
        """SOCSO Borang 3 should NOT be created if employee has no date_of_joining."""
        emp = self._make_employee_mock(employment_type="Permanent", date_of_joining=None)
        emp.date_of_joining = None
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_not_duplicated(self, mock_frappe):
        """SOCSO Borang 3 should not be created if one already exists for the employee."""
        mock_frappe.db.exists.return_value = True

        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Permanent")
        handle_new_employee_socso(emp, "after_insert")

        mock_frappe.new_doc.assert_not_called()

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_filing_deadline_30_days(self, mock_frappe):
        """SOCSO Borang 3 filing_deadline should be 30 days from date_of_joining."""
        mock_frappe.db.exists.return_value = False
        mock_b3 = MagicMock()
        mock_b3.name = "SOCSO-B3-2026-00003"
        mock_b3.filing_deadline = None
        mock_frappe.new_doc.return_value = mock_b3

        joining = "2026-03-01"
        emp = self._make_employee_mock(employment_type="Permanent", date_of_joining=joining)
        handle_new_employee_socso(emp, "after_insert")

        self.assertEqual(mock_b3.filing_deadline, add_days(joining, 30))

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_scheme_category_defaults_to_category_ii(self, mock_frappe):
        """SOCSO Borang 3 should default to Category II for Malaysian employees."""
        mock_frappe.db.exists.return_value = False
        mock_b3 = MagicMock()
        mock_b3.name = "SOCSO-B3-2026-00004"
        mock_frappe.new_doc.return_value = mock_b3

        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Permanent")
        handle_new_employee_socso(emp, "after_insert")

        self.assertEqual(mock_b3.socso_scheme_category, "Category II")

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_borang3_status_defaults_to_pending(self, mock_frappe):
        """SOCSO Borang 3 should be created with Pending status."""
        mock_frappe.db.exists.return_value = False
        mock_b3 = MagicMock()
        mock_b3.name = "SOCSO-B3-2026-00005"
        mock_frappe.new_doc.return_value = mock_b3

        emp = self._make_employee_mock(is_foreign_worker=0, employment_type="Permanent")
        handle_new_employee_socso(emp, "after_insert")

        self.assertEqual(mock_b3.status, "Pending")


class TestSOCSOBorang3OverdueCheck(FrappeTestCase):
    """Tests for the check_overdue_socso_borang3 daily scheduler function."""

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_overdue_records_status_updated(self, mock_frappe):
        """Overdue SOCSO Borang 3 records should be set to Overdue status."""
        mock_frappe.get_all.return_value = [
            {
                "name": "SOCSO-B3-2026-00001",
                "employee_name": "Ahmad bin Abdullah",
                "filing_deadline": "2026-02-01",
            },
        ]
        check_overdue_socso_borang3()

        mock_frappe.db.set_value.assert_called_once_with(
            "SOCSO Borang 3", "SOCSO-B3-2026-00001", "status", "Overdue"
        )

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_overdue_error_logged(self, mock_frappe):
        """Overdue SOCSO Borang 3 should have an error logged."""
        mock_frappe.get_all.return_value = [
            {
                "name": "SOCSO-B3-2026-00001",
                "employee_name": "Ahmad bin Abdullah",
                "filing_deadline": "2026-02-01",
            },
        ]
        check_overdue_socso_borang3()

        mock_frappe.log_error.assert_called_once()
        call_kwargs = mock_frappe.log_error.call_args[1]
        self.assertEqual(call_kwargs["title"], "Overdue SOCSO Borang 3 Filing")

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_no_overdue_records_no_updates(self, mock_frappe):
        """No updates when there are no overdue records."""
        mock_frappe.get_all.return_value = []
        check_overdue_socso_borang3()

        mock_frappe.db.set_value.assert_not_called()
        mock_frappe.db.commit.assert_not_called()

    @patch("lhdn_payroll_integration.services.socso_service.frappe")
    def test_commit_called_when_overdue_records_exist(self, mock_frappe):
        """db.commit() should be called when overdue records are updated."""
        mock_frappe.get_all.return_value = [
            {
                "name": "SOCSO-B3-2026-00002",
                "employee_name": "Lim Ah Kow",
                "filing_deadline": "2026-01-15",
            },
        ]
        check_overdue_socso_borang3()

        mock_frappe.db.commit.assert_called_once()
