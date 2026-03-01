"""Tests for US-115: Auto-Submit CP21/CP22A via e-SPC MyTax at Cessation or Departure.

Acceptance criteria:
1. Employee has cessation fields: Cessation Type, Cessation Date, SPC Reference Number, SPC Status
2. Correct form determined: CP22A for resignation/retirement; CP21 for departure from Malaysia
3. Alert sent 35 days before Cessation Date if SPC Status still Pending
4. Salary Slip blocked if cessation date set and SPC not Cleared / Not Required
5. SPC Reference Number and clearance date stored on Employee
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call


class TestSPCCessationCustomFields(FrappeTestCase):
	"""Test that Employee custom fields for cessation/SPC tracking exist in DB."""

	def test_cessation_type_field_exists(self):
		"""Employee has custom_cessation_type Select field with required options."""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Employee", "fieldname": "custom_cessation_type"},
			["fieldname", "fieldtype", "options"],
			as_dict=True,
		)
		self.assertIsNotNone(field, "custom_cessation_type must exist on Employee")
		self.assertEqual(field["fieldtype"], "Select")
		options = field["options"] or ""
		for opt in ["Resignation", "Retirement", "Termination", "Departure from Malaysia", "Death"]:
			self.assertIn(opt, options, f"'{opt}' must be in custom_cessation_type options")

	def test_cessation_date_field_exists(self):
		"""Employee has custom_cessation_date Date field."""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Employee", "fieldname": "custom_cessation_date"},
			"fieldtype",
		)
		self.assertIsNotNone(field, "custom_cessation_date must exist on Employee")
		self.assertEqual(field, "Date")

	def test_spc_reference_number_field_exists(self):
		"""Employee has custom_spc_reference_number Data field."""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Employee", "fieldname": "custom_spc_reference_number"},
			"fieldtype",
		)
		self.assertIsNotNone(field, "custom_spc_reference_number must exist on Employee")
		self.assertEqual(field, "Data")

	def test_spc_status_field_exists(self):
		"""Employee has custom_spc_status Select field with Pending/Submitted/Cleared/Not Required."""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Employee", "fieldname": "custom_spc_status"},
			["fieldname", "fieldtype", "options"],
			as_dict=True,
		)
		self.assertIsNotNone(field, "custom_spc_status must exist on Employee")
		self.assertEqual(field["fieldtype"], "Select")
		options = field["options"] or ""
		for opt in ["Pending", "Submitted", "Cleared", "Not Required"]:
			self.assertIn(opt, options, f"'{opt}' must be in custom_spc_status options")

	def test_spc_clearance_date_field_exists(self):
		"""Employee has custom_spc_clearance_date Date field for audit trail."""
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": "Employee", "fieldname": "custom_spc_clearance_date"},
			"fieldtype",
		)
		self.assertIsNotNone(field, "custom_spc_clearance_date must exist on Employee")
		self.assertEqual(field, "Date")


class TestCessationFormDetermination(FrappeTestCase):
	"""Test automatic form determination (CP21 vs CP22A) based on cessation type."""

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_cp21_created_for_departure_from_malaysia(self, mock_frappe):
		"""CP21 is created when cessation type is 'Departure from Malaysia'."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00201"
		doc.employee_name = "John Expat"
		doc.date_of_birth = "1985-06-15"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": "2026-04-30",
			"custom_cessation_type": "Departure from Malaysia",
			"custom_spc_status": "Pending",
			"custom_is_foreign_worker": 0,
		}.get(key, default)

		mock_frappe.db.exists.return_value = False
		mock_cp21 = MagicMock()
		mock_cp21.name = "CP21-2026-00001"
		mock_frappe.new_doc.return_value = mock_cp21

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_called_once_with("LHDN CP21")
		self.assertEqual(mock_cp21.employee, "HR-EMP-00201")
		self.assertEqual(mock_cp21.last_working_date, "2026-04-30")
		self.assertEqual(mock_cp21.reason, "Departure from Malaysia")
		mock_cp21.insert.assert_called_once_with(ignore_permissions=True)

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_cp22a_created_for_resignation(self, mock_frappe):
		"""CP22A is created when cessation type is 'Resignation'."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00202"
		doc.employee_name = "Siti Resigns"
		doc.date_of_birth = "1988-03-10"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": "2026-04-30",
			"custom_cessation_type": "Resignation",
			"custom_spc_status": "Pending",
			"custom_is_foreign_worker": 0,
		}.get(key, default)

		mock_frappe.db.exists.return_value = False
		mock_cp22a = MagicMock()
		mock_cp22a.name = "CP22A-2026-00001"
		mock_frappe.new_doc.return_value = mock_cp22a

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_called_once_with("LHDN CP22A")
		self.assertEqual(mock_cp22a.employee, "HR-EMP-00202")
		self.assertEqual(mock_cp22a.cessation_date, "2026-04-30")
		self.assertEqual(mock_cp22a.reason, "Resignation")
		mock_cp22a.insert.assert_called_once_with(ignore_permissions=True)

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_cp22a_created_for_retirement(self, mock_frappe):
		"""CP22A is created when cessation type is 'Retirement'."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00206"
		doc.employee_name = "Ahmad Retired"
		doc.date_of_birth = "1966-01-15"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": "2026-04-30",
			"custom_cessation_type": "Retirement",
			"custom_spc_status": None,
			"custom_is_foreign_worker": 0,
		}.get(key, default)

		mock_frappe.db.exists.return_value = False
		mock_cp22a = MagicMock()
		mock_frappe.new_doc.return_value = mock_cp22a

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_called_once_with("LHDN CP22A")
		self.assertEqual(mock_cp22a.reason, "Retirement")

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_no_form_created_without_cessation_date(self, mock_frappe):
		"""No form created when cessation date is not set."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00203"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": None,
			"custom_cessation_type": "Resignation",
		}.get(key, default)

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_no_form_created_without_cessation_type(self, mock_frappe):
		"""No form created when cessation type is not set (only date set)."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00207"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": "2026-04-30",
			"custom_cessation_type": None,
		}.get(key, default)

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_no_duplicate_cp21_created(self, mock_frappe):
		"""CP21 is not created if one already exists for the employee."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00204"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": "2026-04-30",
			"custom_cessation_type": "Departure from Malaysia",
			"custom_spc_status": "Pending",
			"custom_is_foreign_worker": 0,
		}.get(key, default)

		mock_frappe.db.exists.return_value = True  # already exists

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_not_called()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_cp21_created_for_foreign_worker_regardless_of_cessation_type(self, mock_frappe):
		"""Foreign workers get CP21 regardless of cessation type (e.g. Termination)."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			handle_employee_cessation_update,
		)

		doc = MagicMock()
		doc.name = "HR-EMP-00205"
		doc.employee_name = "Foreign Worker"
		doc.date_of_birth = "1990-01-01"
		doc.get.side_effect = lambda key, default=None: {
			"custom_cessation_date": "2026-04-30",
			"custom_cessation_type": "Termination",
			"custom_spc_status": "Pending",
			"custom_is_foreign_worker": 1,
		}.get(key, default)

		mock_frappe.db.exists.return_value = False
		mock_cp21 = MagicMock()
		mock_frappe.new_doc.return_value = mock_cp21

		handle_employee_cessation_update(doc, "on_update")

		mock_frappe.new_doc.assert_called_once_with("LHDN CP21")


class TestSPCAlertScheduler(FrappeTestCase):
	"""Test 35-day SPC alert scheduler check_pending_spc_alerts."""

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	@patch("lhdn_payroll_integration.services.spc_cessation_service.today")
	@patch("lhdn_payroll_integration.services.spc_cessation_service.add_days")
	def test_alert_triggered_for_pending_employee_within_35_days(
		self, mock_add_days, mock_today, mock_frappe
	):
		"""Employees with cessation within 35 days and Pending SPC trigger an error log."""
		from lhdn_payroll_integration.services.spc_cessation_service import check_pending_spc_alerts

		mock_today.return_value = "2026-03-25"
		mock_add_days.return_value = "2026-04-29"

		mock_frappe.get_all.side_effect = [
			# First call: employees with pending SPC
			[
				{
					"name": "HR-EMP-00301",
					"employee_name": "Ahmad Cessation",
					"custom_cessation_date": "2026-04-20",
					"custom_cessation_type": "Resignation",
					"company": "Arising Packaging",
				}
			],
			# Second call: HR managers for notification
			[{"parent": "hr.manager@test.com"}],
		]
		mock_frappe.get_doc.return_value = MagicMock()

		check_pending_spc_alerts()

		mock_frappe.log_error.assert_called_once()
		log_call = mock_frappe.log_error.call_args
		self.assertIn("SPC Submission Alert", str(log_call))
		self.assertIn("Ahmad Cessation", str(log_call))

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	@patch("lhdn_payroll_integration.services.spc_cessation_service.today")
	@patch("lhdn_payroll_integration.services.spc_cessation_service.add_days")
	def test_no_alert_when_no_pending_employees(self, mock_add_days, mock_today, mock_frappe):
		"""No alerts when no employees have pending SPC within 35 days."""
		from lhdn_payroll_integration.services.spc_cessation_service import check_pending_spc_alerts

		mock_today.return_value = "2026-03-25"
		mock_add_days.return_value = "2026-04-29"
		mock_frappe.get_all.return_value = []

		check_pending_spc_alerts()

		mock_frappe.log_error.assert_not_called()


class TestSalarySlipSPCBlocking(FrappeTestCase):
	"""Test Salary Slip before_submit blocking when SPC not cleared."""

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_salary_slip_blocked_when_spc_pending(self, mock_frappe):
		"""Salary Slip submit is blocked when employee has cessation date and SPC is Pending."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			block_salary_slip_if_spc_pending,
		)

		doc = MagicMock()
		doc.get.side_effect = lambda key, default=None: {
			"employee": "HR-EMP-00401",
			"employee_name": "Ahmad Block",
		}.get(key, default)

		mock_frappe.db.get_value.return_value = {
			"custom_cessation_date": "2026-04-30",
			"custom_spc_status": "Pending",
		}

		block_salary_slip_if_spc_pending(doc, "before_submit")

		mock_frappe.throw.assert_called_once()
		call_args = mock_frappe.throw.call_args[0][0]
		self.assertIn("SPC", call_args)
		self.assertIn("Pending", call_args)

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_salary_slip_blocked_when_spc_submitted(self, mock_frappe):
		"""Salary Slip submit is blocked when SPC Status is 'Submitted' (not yet cleared)."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			block_salary_slip_if_spc_pending,
		)

		doc = MagicMock()
		doc.get.side_effect = lambda key, default=None: {
			"employee": "HR-EMP-00405",
			"employee_name": "Waiting Clearance",
		}.get(key, default)

		mock_frappe.db.get_value.return_value = {
			"custom_cessation_date": "2026-04-30",
			"custom_spc_status": "Submitted",
		}

		block_salary_slip_if_spc_pending(doc, "before_submit")

		mock_frappe.throw.assert_called_once()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_salary_slip_allowed_when_spc_cleared(self, mock_frappe):
		"""Salary Slip submit proceeds when SPC Status is 'Cleared'."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			block_salary_slip_if_spc_pending,
		)

		doc = MagicMock()
		doc.get.side_effect = lambda key, default=None: {
			"employee": "HR-EMP-00402",
			"employee_name": "Siti Cleared",
		}.get(key, default)

		mock_frappe.db.get_value.return_value = {
			"custom_cessation_date": "2026-04-30",
			"custom_spc_status": "Cleared",
		}

		block_salary_slip_if_spc_pending(doc, "before_submit")

		mock_frappe.throw.assert_not_called()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_salary_slip_allowed_when_spc_not_required(self, mock_frappe):
		"""Salary Slip submit proceeds when SPC Status is 'Not Required'."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			block_salary_slip_if_spc_pending,
		)

		doc = MagicMock()
		doc.get.side_effect = lambda key, default=None: {
			"employee": "HR-EMP-00403",
			"employee_name": "Abu Not Required",
		}.get(key, default)

		mock_frappe.db.get_value.return_value = {
			"custom_cessation_date": "2026-04-30",
			"custom_spc_status": "Not Required",
		}

		block_salary_slip_if_spc_pending(doc, "before_submit")

		mock_frappe.throw.assert_not_called()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_salary_slip_not_blocked_without_cessation_date(self, mock_frappe):
		"""Salary Slip submit proceeds when employee has no cessation date."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			block_salary_slip_if_spc_pending,
		)

		doc = MagicMock()
		doc.get.side_effect = lambda key, default=None: {
			"employee": "HR-EMP-00404",
			"employee_name": "Normal Employee",
		}.get(key, default)

		mock_frappe.db.get_value.return_value = {
			"custom_cessation_date": None,
			"custom_spc_status": None,
		}

		block_salary_slip_if_spc_pending(doc, "before_submit")

		mock_frappe.throw.assert_not_called()

	@patch("lhdn_payroll_integration.services.spc_cessation_service.frappe")
	def test_salary_slip_not_blocked_when_employee_has_no_cessation_data(self, mock_frappe):
		"""Salary Slip proceeds when db.get_value returns None (no custom fields yet)."""
		from lhdn_payroll_integration.services.spc_cessation_service import (
			block_salary_slip_if_spc_pending,
		)

		doc = MagicMock()
		doc.get.side_effect = lambda key, default=None: {
			"employee": "HR-EMP-00406",
			"employee_name": "New Employee",
		}.get(key, default)

		mock_frappe.db.get_value.return_value = None

		block_salary_slip_if_spc_pending(doc, "before_submit")

		mock_frappe.throw.assert_not_called()


class TestHooksRegistration(FrappeTestCase):
	"""Test that hooks.py registers SPC cessation handlers correctly."""

	def test_employee_on_update_includes_spc_handler(self):
		"""hooks.py Employee on_update includes spc_cessation_service handler."""
		import lhdn_payroll_integration.lhdn_payroll_integration.hooks as hooks

		on_update = hooks.doc_events.get("Employee", {}).get("on_update", [])
		if isinstance(on_update, str):
			on_update = [on_update]

		spc_handlers = [h for h in on_update if "spc_cessation" in h]
		self.assertTrue(
			len(spc_handlers) > 0,
			"spc_cessation_service.handle_employee_cessation_update must be in Employee on_update",
		)

	def test_salary_slip_before_submit_includes_spc_block(self):
		"""hooks.py Salary Slip before_submit includes SPC blocking handler."""
		import lhdn_payroll_integration.lhdn_payroll_integration.hooks as hooks

		before_submit = hooks.doc_events.get("Salary Slip", {}).get("before_submit", [])
		if isinstance(before_submit, str):
			before_submit = [before_submit]

		spc_handlers = [h for h in before_submit if "spc_cessation" in h]
		self.assertTrue(
			len(spc_handlers) > 0,
			"spc_cessation_service.block_salary_slip_if_spc_pending must be in Salary Slip before_submit",
		)

	def test_scheduler_daily_includes_spc_alert(self):
		"""hooks.py scheduler_events daily includes check_pending_spc_alerts."""
		import lhdn_payroll_integration.lhdn_payroll_integration.hooks as hooks

		daily = hooks.scheduler_events.get("daily", [])
		spc_schedulers = [h for h in daily if "spc_cessation" in h]
		self.assertTrue(
			len(spc_schedulers) > 0,
			"check_pending_spc_alerts must be in daily scheduler",
		)
