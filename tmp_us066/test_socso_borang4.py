"""Tests for SOCSO Borang 4 employee termination notification (PERKESO).

Verifies:
- Auto-creation when eligible employee status set to Left
- No auto-creation for foreign workers
- No auto-creation for non-Permanent/Contract employment types
- No auto-creation when status is not Left
- Filing deadline set to 30 days from date_of_termination
- Duplicate prevention
- Overdue status update via scheduler function
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.services.socso_service import (
	handle_employee_termination_socso,
	check_overdue_socso_borang4,
)


class TestSOCSOBorang4AutoCreation(FrappeTestCase):
	"""Tests for SOCSO Borang 4 auto-creation on eligible employee termination."""

	def _make_employee_mock(
		self,
		status="Left",
		is_foreign_worker=0,
		employment_type="Permanent",
		date_of_leaving=None,
	):
		mock = MagicMock()
		mock.name = "HR-EMP-99920"
		mock.employee_name = "Test Employee Termination"
		mock.status = status
		mock.custom_is_foreign_worker = is_foreign_worker
		mock.custom_employment_type = employment_type
		mock.date_of_leaving = date_of_leaving or today()
		mock.get = lambda field, default=None: getattr(mock, field, default)
		return mock

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_created_for_permanent_employee_left(self, mock_frappe):
		"""SOCSO Borang 4 should be created for Permanent employee with status Left."""
		mock_frappe.db.exists.return_value = False
		mock_b4 = MagicMock()
		mock_b4.name = "SOCSO-B4-2026-00001"
		mock_b4.filing_deadline = add_days(today(), 30)
		mock_frappe.new_doc.return_value = mock_b4

		emp = self._make_employee_mock(status="Left", is_foreign_worker=0, employment_type="Permanent")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_called_once_with("SOCSO Borang 4")
		mock_b4.insert.assert_called_once_with(ignore_permissions=True)

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_created_for_contract_employee_left(self, mock_frappe):
		"""SOCSO Borang 4 should be created for Contract employee with status Left."""
		mock_frappe.db.exists.return_value = False
		mock_b4 = MagicMock()
		mock_b4.name = "SOCSO-B4-2026-00002"
		mock_b4.filing_deadline = add_days(today(), 30)
		mock_frappe.new_doc.return_value = mock_b4

		emp = self._make_employee_mock(status="Left", is_foreign_worker=0, employment_type="Contract")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_called_once_with("SOCSO Borang 4")
		mock_b4.insert.assert_called_once_with(ignore_permissions=True)

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_not_created_for_active_employee(self, mock_frappe):
		"""SOCSO Borang 4 should NOT be created when employee status is Active."""
		emp = self._make_employee_mock(status="Active", employment_type="Permanent")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_not_created_for_on_leave_employee(self, mock_frappe):
		"""SOCSO Borang 4 should NOT be created when employee status is On Leave."""
		emp = self._make_employee_mock(status="On Leave", employment_type="Permanent")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_not_created_for_foreign_worker(self, mock_frappe):
		"""SOCSO Borang 4 should NOT be created for foreign workers."""
		emp = self._make_employee_mock(status="Left", is_foreign_worker=1, employment_type="Permanent")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_not_created_for_intern(self, mock_frappe):
		"""SOCSO Borang 4 should NOT be created for Intern employment type."""
		emp = self._make_employee_mock(status="Left", is_foreign_worker=0, employment_type="Intern")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_not_created_for_part_time(self, mock_frappe):
		"""SOCSO Borang 4 should NOT be created for Part-time employment type."""
		emp = self._make_employee_mock(status="Left", is_foreign_worker=0, employment_type="Part-time")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_not_duplicated(self, mock_frappe):
		"""SOCSO Borang 4 should not be created if one already exists for the employee."""
		mock_frappe.db.exists.return_value = True

		emp = self._make_employee_mock(status="Left", is_foreign_worker=0, employment_type="Permanent")
		handle_employee_termination_socso(emp, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_filing_deadline_30_days(self, mock_frappe):
		"""SOCSO Borang 4 filing_deadline should be 30 days from date_of_leaving."""
		mock_frappe.db.exists.return_value = False
		mock_b4 = MagicMock()
		mock_b4.name = "SOCSO-B4-2026-00003"
		mock_b4.filing_deadline = None
		mock_frappe.new_doc.return_value = mock_b4

		leaving_date = "2026-03-01"
		emp = self._make_employee_mock(status="Left", employment_type="Permanent", date_of_leaving=leaving_date)
		handle_employee_termination_socso(emp, "on_update")

		self.assertEqual(mock_b4.filing_deadline, add_days(leaving_date, 30))

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_date_of_termination_set_from_date_of_leaving(self, mock_frappe):
		"""SOCSO Borang 4 date_of_termination should equal employee date_of_leaving."""
		mock_frappe.db.exists.return_value = False
		mock_b4 = MagicMock()
		mock_b4.name = "SOCSO-B4-2026-00004"
		mock_frappe.new_doc.return_value = mock_b4

		leaving_date = "2026-03-15"
		emp = self._make_employee_mock(status="Left", employment_type="Permanent", date_of_leaving=leaving_date)
		handle_employee_termination_socso(emp, "on_update")

		self.assertEqual(mock_b4.date_of_termination, leaving_date)

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_borang4_status_defaults_to_pending(self, mock_frappe):
		"""SOCSO Borang 4 should be created with Pending status."""
		mock_frappe.db.exists.return_value = False
		mock_b4 = MagicMock()
		mock_b4.name = "SOCSO-B4-2026-00005"
		mock_frappe.new_doc.return_value = mock_b4

		emp = self._make_employee_mock(status="Left", is_foreign_worker=0, employment_type="Permanent")
		handle_employee_termination_socso(emp, "on_update")

		self.assertEqual(mock_b4.status, "Pending")


class TestSOCSOBorang4OverdueCheck(FrappeTestCase):
	"""Tests for the check_overdue_socso_borang4 daily scheduler function."""

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_overdue_records_status_updated(self, mock_frappe):
		"""Overdue SOCSO Borang 4 records should be set to Overdue status."""
		mock_frappe.get_all.return_value = [
			{
				"name": "SOCSO-B4-2026-00001",
				"employee_name": "Ahmad bin Abdullah",
				"filing_deadline": "2026-02-01",
			},
		]
		check_overdue_socso_borang4()

		mock_frappe.db.set_value.assert_called_once_with(
			"SOCSO Borang 4", "SOCSO-B4-2026-00001", "status", "Overdue"
		)

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_overdue_error_logged(self, mock_frappe):
		"""Overdue SOCSO Borang 4 should have an error logged."""
		mock_frappe.get_all.return_value = [
			{
				"name": "SOCSO-B4-2026-00001",
				"employee_name": "Ahmad bin Abdullah",
				"filing_deadline": "2026-02-01",
			},
		]
		check_overdue_socso_borang4()

		mock_frappe.log_error.assert_called_once()
		call_kwargs = mock_frappe.log_error.call_args[1]
		self.assertEqual(call_kwargs["title"], "Overdue SOCSO Borang 4 Filing")

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_no_overdue_records_no_updates(self, mock_frappe):
		"""No updates when there are no overdue records."""
		mock_frappe.get_all.return_value = []
		check_overdue_socso_borang4()

		mock_frappe.db.set_value.assert_not_called()
		mock_frappe.db.commit.assert_not_called()

	@patch("lhdn_payroll_integration.services.socso_service.frappe")
	def test_commit_called_when_overdue_records_exist(self, mock_frappe):
		"""db.commit() should be called when overdue records are updated."""
		mock_frappe.get_all.return_value = [
			{
				"name": "SOCSO-B4-2026-00002",
				"employee_name": "Lim Ah Kow",
				"filing_deadline": "2026-01-15",
			},
		]
		check_overdue_socso_borang4()

		mock_frappe.db.commit.assert_called_once()
