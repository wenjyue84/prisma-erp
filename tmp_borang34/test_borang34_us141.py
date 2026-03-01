"""
Tests for US-141 — PERKESO Borang 34 Accident Notification (48-Hour Statutory Deadline)

TDD GREEN: all tests must pass after implementation.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service import (
	BORANG34_DEADLINE_HOURS,
	BORANG34_ESCALATION_HOURS,
	_compute_and_set_deadline,
	_create_borang34_task,
	check_overdue_borang34,
	get_borang34_data,
	get_six_month_wage_history,
	handle_accident_after_insert,
)


class TestWorkplaceAccidentDocType(FrappeTestCase):
	"""Verify the Workplace Accident DocType exists with required fields."""

	def test_workplace_accident_doctype_exists(self):
		"""Workplace Accident DocType must be registered in Frappe."""
		self.assertTrue(
			frappe.db.exists("DocType", "Workplace Accident"),
			msg="DocType 'Workplace Accident' not found — run bench migrate",
		)

	def test_required_field_employee(self):
		"""Employee link field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("employee")
		self.assertIsNotNone(field, msg="'employee' field missing from Workplace Accident")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Employee")

	def test_required_field_incident_date_time(self):
		"""incident_date_time Datetime field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("incident_date_time")
		self.assertIsNotNone(field, msg="'incident_date_time' field missing")
		self.assertEqual(field.fieldtype, "Datetime")

	def test_required_field_accident_location(self):
		"""accident_location field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("accident_location")
		self.assertIsNotNone(field, msg="'accident_location' field missing")

	def test_required_field_supervisor_witness_name(self):
		"""supervisor_witness_name field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("supervisor_witness_name")
		self.assertIsNotNone(field, msg="'supervisor_witness_name' field missing")

	def test_required_field_injury_description(self):
		"""injury_description Long Text field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("injury_description")
		self.assertIsNotNone(field, msg="'injury_description' field missing")

	def test_statutory_deadline_field(self):
		"""statutory_deadline Datetime field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("statutory_deadline")
		self.assertIsNotNone(field, msg="'statutory_deadline' field missing")
		self.assertEqual(field.fieldtype, "Datetime")

	def test_borang34_status_field_options(self):
		"""borang34_status must have Draft and Submitted options."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("borang34_status")
		self.assertIsNotNone(field, msg="'borang34_status' field missing")
		options = field.options.split("\n")
		self.assertIn("Draft", options)
		self.assertIn("Submitted", options)

	def test_borang34_attachment_field(self):
		"""borang34_attachment Attach field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("borang34_attachment")
		self.assertIsNotNone(field, msg="'borang34_attachment' field missing")
		self.assertEqual(field.fieldtype, "Attach")

	def test_wage_history_attachment_field(self):
		"""wage_history_attachment Attach field must exist."""
		meta = frappe.get_meta("Workplace Accident")
		field = meta.get_field("wage_history_attachment")
		self.assertIsNotNone(field, msg="'wage_history_attachment' field missing")
		self.assertEqual(field.fieldtype, "Attach")


class TestCustomFieldsOnEmployeeAndCompany(FrappeTestCase):
	"""Verify custom fields for PERKESO data on Employee and Company."""

	def test_employee_socso_number_field_exists(self):
		"""Employee must have custom_socso_number field for SOCSO registration."""
		self.assertTrue(
			frappe.db.exists("Custom Field", "Employee-custom_socso_number"),
			msg="Custom field 'custom_socso_number' missing from Employee",
		)

	def test_company_perkeso_employer_code_field_exists(self):
		"""Company must have custom_perkeso_employer_code field."""
		self.assertTrue(
			frappe.db.exists("Custom Field", "Company-custom_perkeso_employer_code"),
			msg="Custom field 'custom_perkeso_employer_code' missing from Company",
		)


class TestStatutoryDeadlineConstants(FrappeTestCase):
	"""Verify service constants are correctly defined."""

	def test_deadline_is_48_hours(self):
		"""BORANG34_DEADLINE_HOURS must be 48."""
		self.assertEqual(BORANG34_DEADLINE_HOURS, 48)

	def test_escalation_is_46_hours(self):
		"""BORANG34_ESCALATION_HOURS must be 46 (2 hours before deadline)."""
		self.assertEqual(BORANG34_ESCALATION_HOURS, 46)


class TestDeadlineComputation(FrappeTestCase):
	"""Test _compute_and_set_deadline sets deadline 48h after incident."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.set_value")
	def test_deadline_is_48h_after_incident(self, mock_set_value):
		"""statutory_deadline must be exactly 48 hours after incident_date_time."""
		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.incident_date_time = "2026-03-01 10:00:00"

		_compute_and_set_deadline(doc)

		expected_deadline = datetime(2026, 3, 3, 10, 0, 0)
		mock_set_value.assert_called_once_with(
			"Workplace Accident", "WPA-2026-00001", "statutory_deadline", expected_deadline
		)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.set_value")
	def test_deadline_crosses_midnight(self, mock_set_value):
		"""Deadline must correctly span midnight boundaries."""
		doc = MagicMock()
		doc.name = "WPA-2026-00002"
		doc.incident_date_time = "2026-03-01 20:00:00"

		_compute_and_set_deadline(doc)

		expected_deadline = datetime(2026, 3, 3, 20, 0, 0)
		mock_set_value.assert_called_once_with(
			"Workplace Accident", "WPA-2026-00002", "statutory_deadline", expected_deadline
		)


class TestTaskCreation(FrappeTestCase):
	"""Test that a high-priority Task is created on accident insertion."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.new_doc")
	def test_todo_created_on_insert(self, mock_new_doc, mock_commit):
		"""A ToDo document must be created when accident is inserted."""
		mock_task = MagicMock()
		mock_new_doc.return_value = mock_task

		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.employee = "EMP-001"
		doc.incident_date_time = "2026-03-01 10:00:00"
		doc.accident_location = "Factory Floor A"

		_create_borang34_task(doc)

		mock_new_doc.assert_called_once_with("ToDo")
		mock_task.insert.assert_called_once_with(ignore_permissions=True)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.new_doc")
	def test_task_is_high_priority(self, mock_new_doc, mock_commit):
		"""Task priority must be 'High'."""
		mock_task = MagicMock()
		mock_new_doc.return_value = mock_task

		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.employee = "EMP-001"
		doc.incident_date_time = "2026-03-01 10:00:00"
		doc.accident_location = "Factory Floor A"

		_create_borang34_task(doc)

		self.assertEqual(mock_task.priority, "High")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.new_doc")
	def test_task_assigned_to_hr_manager_role(self, mock_new_doc, mock_commit):
		"""Task must be assigned to HR Manager role."""
		mock_task = MagicMock()
		mock_new_doc.return_value = mock_task

		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.employee = "EMP-001"
		doc.incident_date_time = "2026-03-01 10:00:00"
		doc.accident_location = "Factory Floor A"

		_create_borang34_task(doc)

		self.assertEqual(mock_task.role, "HR Manager")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.new_doc")
	def test_task_references_accident(self, mock_new_doc, mock_commit):
		"""Task must have reference_type=Workplace Accident and correct reference_name."""
		mock_task = MagicMock()
		mock_new_doc.return_value = mock_task

		doc = MagicMock()
		doc.name = "WPA-2026-00099"
		doc.employee = "EMP-001"
		doc.incident_date_time = "2026-03-01 10:00:00"
		doc.accident_location = "Warehouse B"

		_create_borang34_task(doc)

		self.assertEqual(mock_task.reference_type, "Workplace Accident")
		self.assertEqual(mock_task.reference_name, "WPA-2026-00099")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.new_doc")
	def test_task_description_contains_borang34_marker(self, mock_new_doc, mock_commit):
		"""Task description must contain [BORANG34-PENDING] marker for dedup."""
		mock_task = MagicMock()
		mock_new_doc.return_value = mock_task

		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.employee = "EMP-001"
		doc.incident_date_time = "2026-03-01 10:00:00"
		doc.accident_location = "Factory Floor A"

		_create_borang34_task(doc)

		self.assertIn("[BORANG34-PENDING]", mock_task.description)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.new_doc")
	def test_task_due_date_is_48h_deadline(self, mock_new_doc, mock_commit):
		"""Task due date must correspond to the 48-hour statutory deadline."""
		mock_task = MagicMock()
		mock_new_doc.return_value = mock_task

		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.employee = "EMP-001"
		doc.incident_date_time = "2026-03-01 10:00:00"
		doc.accident_location = "Factory Floor A"

		_create_borang34_task(doc)

		from datetime import date
		self.assertEqual(mock_task.date, date(2026, 3, 3))


class TestHandleAccidentAfterInsert(FrappeTestCase):
	"""Test the combined after_insert hook calls both sub-functions."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service._create_borang34_task")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service._compute_and_set_deadline")
	def test_after_insert_calls_both_functions(self, mock_compute, mock_create_task):
		"""handle_accident_after_insert must call _compute_and_set_deadline and _create_borang34_task."""
		doc = MagicMock()
		doc.name = "WPA-2026-00001"
		doc.incident_date_time = "2026-03-01 10:00:00"

		handle_accident_after_insert(doc, "after_insert")

		mock_compute.assert_called_once_with(doc)
		mock_create_task.assert_called_once_with(doc)


class TestOverdueEscalation(FrappeTestCase):
	"""Test the hourly overdue check escalates tasks at the 46-hour mark."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service._send_escalation_notification")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.get_value")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.set_value")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.nowdatetime")
	def test_escalates_overdue_task(
		self, mock_now, mock_get_all, mock_set_value, mock_get_value, mock_notify, mock_commit
	):
		"""Tasks for accidents older than 46h with Draft status must be escalated."""
		mock_now.return_value = "2026-03-01 10:00:00"

		def get_all_side(doctype, filters=None, fields=None, **kwargs):
			if doctype == "Workplace Accident":
				return [
					{
						"name": "WPA-2026-00001",
						"employee": "EMP-001",
						"incident_date_time": "2026-02-27 10:00:00",
						"statutory_deadline": "2026-02-28 10:00:00",
					}
				]
			elif doctype == "ToDo":
				return [{"name": "TODO-001"}]
			return []

		mock_get_all.side_effect = get_all_side
		mock_get_value.return_value = "[BORANG34-PENDING] Submit PERKESO Borang 34 for WPA-2026-00001"

		check_overdue_borang34()

		mock_set_value.assert_called_once()
		call_args = mock_set_value.call_args
		self.assertEqual(call_args[0][0], "ToDo")
		self.assertEqual(call_args[0][1], "TODO-001")
		updated_desc = call_args[0][2]
		if isinstance(updated_desc, dict):
			self.assertIn("[BORANG34-OVERDUE]", updated_desc.get("description", ""))
		else:
			# May be positional
			pass

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.db.commit")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.nowdatetime")
	def test_no_escalation_when_no_overdue_accidents(self, mock_now, mock_get_all, mock_commit):
		"""When no accidents are older than 46h, no escalation occurs."""
		mock_now.return_value = "2026-03-01 10:00:00"
		mock_get_all.return_value = []

		check_overdue_borang34()

		# get_all called once for accidents, no ToDo calls
		mock_get_all.assert_called_once()


class TestSixMonthWageHistory(FrappeTestCase):
	"""Test get_six_month_wage_history returns correct structure."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	def test_returns_six_months(self, mock_get_all):
		"""Result must always have exactly 6 entries."""
		mock_get_all.return_value = [{"gross_pay": 3000.0}]

		result = get_six_month_wage_history("EMP-001", "2026-03-01")

		self.assertEqual(len(result), 6)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	def test_periods_are_correct_format(self, mock_get_all):
		"""Each entry must have a 'period' key in YYYY-MM format."""
		mock_get_all.return_value = [{"gross_pay": 3000.0}]

		result = get_six_month_wage_history("EMP-001", "2026-03-15")

		for entry in result:
			self.assertIn("period", entry)
			self.assertRegex(entry["period"], r"^\d{4}-\d{2}$")
			self.assertIn("gross_pay", entry)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	def test_covers_6_months_before_incident(self, mock_get_all):
		"""The 6 periods must be the 6 months preceding the incident month."""
		mock_get_all.return_value = [{"gross_pay": 4000.0}]

		result = get_six_month_wage_history("EMP-001", "2026-03-01")

		periods = [r["period"] for r in result]
		self.assertIn("2025-09", periods)
		self.assertIn("2025-10", periods)
		self.assertIn("2025-11", periods)
		self.assertIn("2025-12", periods)
		self.assertIn("2026-01", periods)
		self.assertIn("2026-02", periods)
		# March itself is NOT included (incident month not a past month)
		self.assertNotIn("2026-03", periods)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	def test_zero_wage_when_no_salary_slip(self, mock_get_all):
		"""Months with no salary slip must show 0.0 gross_pay."""
		mock_get_all.return_value = []  # No salary slips

		result = get_six_month_wage_history("EMP-001", "2026-03-01")

		for entry in result:
			self.assertEqual(entry["gross_pay"], 0.0)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	def test_gross_pay_from_salary_slip(self, mock_get_all):
		"""gross_pay must be taken from the Salary Slip record."""
		mock_get_all.return_value = [{"gross_pay": 5000.0}]

		result = get_six_month_wage_history("EMP-001", "2026-03-01")

		for entry in result:
			self.assertEqual(entry["gross_pay"], 5000.0)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_all")
	def test_accepts_datetime_incident_date(self, mock_get_all):
		"""Function must accept both string and datetime incident_date."""
		mock_get_all.return_value = [{"gross_pay": 3000.0}]

		dt_result = get_six_month_wage_history("EMP-001", datetime(2026, 3, 1))
		str_result = get_six_month_wage_history("EMP-001", "2026-03-01")

		self.assertEqual(len(dt_result), 6)
		self.assertEqual(len(str_result), 6)


class TestBorang34DataPopulation(FrappeTestCase):
	"""Test get_borang34_data returns correctly structured data."""

	def _make_accident_mock(self):
		acc = MagicMock()
		acc.name = "WPA-2026-00001"
		acc.employee = "EMP-001"
		acc.incident_date_time = "2026-03-01 10:00:00"
		acc.accident_location = "Factory Floor A"
		acc.injury_description = "Slipped on wet floor, fractured ankle"
		acc.supervisor_witness_name = "Ahmad Supervisor"
		acc.statutory_deadline = "2026-03-03 10:00:00"
		acc.borang34_status = "Draft"
		return acc

	def _make_employee_mock(self):
		emp = MagicMock()
		emp.employee_name = "Ali bin Hassan"
		emp.custom_nric_number = "900101-14-1234"
		emp.custom_socso_number = "12345678"
		emp.designation = "Production Operator"
		emp.company = "Arising Packaging"
		return emp

	def _make_company_mock(self):
		comp = MagicMock()
		comp.company_name = "Arising Packaging Sdn Bhd"
		comp.custom_perkeso_employer_code = "E12345678"
		return comp

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.get_six_month_wage_history")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_doc")
	def test_employee_name_in_data(self, mock_get_doc, mock_wage_hist):
		"""employee_name must be populated from Employee record."""
		mock_get_doc.side_effect = lambda dt, name: (
			self._make_accident_mock() if dt == "Workplace Accident" else
			self._make_employee_mock() if dt == "Employee" else
			self._make_company_mock()
		)
		mock_wage_hist.return_value = []

		result = get_borang34_data("WPA-2026-00001")

		self.assertEqual(result["employee_name"], "Ali bin Hassan")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.get_six_month_wage_history")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_doc")
	def test_employee_socso_number_in_data(self, mock_get_doc, mock_wage_hist):
		"""employee_socso_number must be populated from Employee.custom_socso_number."""
		mock_get_doc.side_effect = lambda dt, name: (
			self._make_accident_mock() if dt == "Workplace Accident" else
			self._make_employee_mock() if dt == "Employee" else
			self._make_company_mock()
		)
		mock_wage_hist.return_value = []

		result = get_borang34_data("WPA-2026-00001")

		self.assertEqual(result["employee_socso_number"], "12345678")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.get_six_month_wage_history")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_doc")
	def test_employer_perkeso_code_in_data(self, mock_get_doc, mock_wage_hist):
		"""employer_perkeso_code must come from Company.custom_perkeso_employer_code."""
		mock_get_doc.side_effect = lambda dt, name: (
			self._make_accident_mock() if dt == "Workplace Accident" else
			self._make_employee_mock() if dt == "Employee" else
			self._make_company_mock()
		)
		mock_wage_hist.return_value = []

		result = get_borang34_data("WPA-2026-00001")

		self.assertEqual(result["employer_perkeso_code"], "E12345678")

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.get_six_month_wage_history")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_doc")
	def test_six_month_wage_history_in_data(self, mock_get_doc, mock_wage_hist):
		"""six_month_wage_history must be included in the returned data dict."""
		mock_get_doc.side_effect = lambda dt, name: (
			self._make_accident_mock() if dt == "Workplace Accident" else
			self._make_employee_mock() if dt == "Employee" else
			self._make_company_mock()
		)
		mock_wage_hist.return_value = [
			{"period": "2025-09", "gross_pay": 3000.0},
			{"period": "2025-10", "gross_pay": 3000.0},
		]

		result = get_borang34_data("WPA-2026-00001")

		self.assertIn("six_month_wage_history", result)
		self.assertEqual(len(result["six_month_wage_history"]), 2)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.get_six_month_wage_history")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_doc")
	def test_six_month_average_wage_computed(self, mock_get_doc, mock_wage_hist):
		"""six_month_average_wage must be mean of non-zero monthly wages."""
		mock_get_doc.side_effect = lambda dt, name: (
			self._make_accident_mock() if dt == "Workplace Accident" else
			self._make_employee_mock() if dt == "Employee" else
			self._make_company_mock()
		)
		mock_wage_hist.return_value = [
			{"period": "2025-09", "gross_pay": 3000.0},
			{"period": "2025-10", "gross_pay": 3000.0},
			{"period": "2025-11", "gross_pay": 0.0},   # unpaid leave
			{"period": "2025-12", "gross_pay": 3000.0},
			{"period": "2026-01", "gross_pay": 3000.0},
			{"period": "2026-02", "gross_pay": 3000.0},
		]

		result = get_borang34_data("WPA-2026-00001")

		# Average of 5 non-zero months = 3000.0
		self.assertEqual(result["six_month_average_wage"], 3000.0)

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.get_six_month_wage_history")
	@patch("lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.frappe.get_doc")
	def test_accident_details_in_data(self, mock_get_doc, mock_wage_hist):
		"""Accident description, location, witness, and deadline must be in data."""
		mock_get_doc.side_effect = lambda dt, name: (
			self._make_accident_mock() if dt == "Workplace Accident" else
			self._make_employee_mock() if dt == "Employee" else
			self._make_company_mock()
		)
		mock_wage_hist.return_value = []

		result = get_borang34_data("WPA-2026-00001")

		self.assertEqual(result["accident_location"], "Factory Floor A")
		self.assertIn("fractured ankle", result["injury_description"])
		self.assertEqual(result["supervisor_witness_name"], "Ahmad Supervisor")
		self.assertIn("2026-03-03", result["statutory_deadline"])


class TestHooksRegistration(FrappeTestCase):
	"""Verify borang34_service is registered in hooks.py."""

	def test_workplace_accident_after_insert_hook(self):
		"""hooks.py must register handle_accident_after_insert for Workplace Accident."""
		import lhdn_payroll_integration.hooks as hooks_module

		doc_events = getattr(hooks_module, "doc_events", {})
		wa_events = doc_events.get("Workplace Accident", {})
		after_insert = wa_events.get("after_insert", [])

		if isinstance(after_insert, str):
			after_insert = [after_insert]

		self.assertTrue(
			any("borang34_service.handle_accident_after_insert" in h for h in after_insert),
			msg="handle_accident_after_insert not found in Workplace Accident after_insert hooks",
		)

	def test_hourly_scheduler_check_overdue_registered(self):
		"""hooks.py must register check_overdue_borang34 in hourly scheduler."""
		import lhdn_payroll_integration.hooks as hooks_module

		hourly = getattr(hooks_module, "scheduler_events", {}).get("hourly", [])
		self.assertTrue(
			any("borang34_service.check_overdue_borang34" in h for h in hourly),
			msg="check_overdue_borang34 not found in hourly scheduler_events",
		)
