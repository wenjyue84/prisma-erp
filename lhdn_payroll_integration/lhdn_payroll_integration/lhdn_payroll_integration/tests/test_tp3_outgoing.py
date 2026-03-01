"""Tests for US-143: Auto-Generate TP3 YTD Income Statement for Departing Employees.

Verifies:
- generate_outgoing_tp3() creates a record with correct YTD totals
- get_ytd_payroll_totals() aggregates correctly from submitted Salary Slips
- Employee with no submitted salary slips returns zero totals
- handle_employee_left_tp3() hook creates TP3 record when status set to 'Left'
- Duplicate TP3 creation is prevented for the same employee/year
- Employee set to non-'Left' status does not trigger TP3 generation
- DocType field validation: negative PCB raises error; invalid year raises error
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock, call

from lhdn_payroll_integration.services.tp3_outgoing_service import (
	generate_outgoing_tp3,
	get_ytd_payroll_totals,
	handle_employee_left_tp3,
)


class TestGetYTDPayrollTotals(FrappeTestCase):
	"""Tests for get_ytd_payroll_totals() — Salary Slip aggregation."""

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_aggregates_single_slip_totals(self, mock_frappe):
		"""Single submitted slip — all fields summed correctly."""
		mock_frappe.db.get_all.return_value = [
			{
				"gross_pay": 5000.0,
				"custom_ytd_basic_salary": 4000.0,
				"custom_bik_value": 200.0,
				"custom_epf_employee": 440.0,
				"custom_socso_employee": 10.90,
				"custom_eis_employee": 4.50,
				"custom_zakat_deducted": 0.0,
				"custom_cp38_deducted": 0.0,
				"custom_pcb_amount": 180.0,
				"total_deduction": 635.40,
			}
		]

		result = get_ytd_payroll_totals("HR-EMP-001", 2025, "2025-06-30")

		self.assertAlmostEqual(result["ytd_basic_salary"], 4000.0)
		self.assertAlmostEqual(result["ytd_gross_allowances"], 5000.0)
		self.assertAlmostEqual(result["ytd_bik_value"], 200.0)
		self.assertAlmostEqual(result["ytd_epf_employee"], 440.0)
		self.assertAlmostEqual(result["ytd_socso"], 10.90)
		self.assertAlmostEqual(result["ytd_eis"], 4.50)
		self.assertAlmostEqual(result["ytd_pcb"], 180.0)

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_aggregates_multiple_slips(self, mock_frappe):
		"""Multiple submitted slips — values summed across all months."""
		mock_frappe.db.get_all.return_value = [
			{
				"gross_pay": 5000.0,
				"custom_ytd_basic_salary": 4000.0,
				"custom_bik_value": 0.0,
				"custom_epf_employee": 440.0,
				"custom_socso_employee": 10.90,
				"custom_eis_employee": 4.50,
				"custom_zakat_deducted": 0.0,
				"custom_cp38_deducted": 0.0,
				"custom_pcb_amount": 180.0,
				"total_deduction": 635.40,
			},
			{
				"gross_pay": 5000.0,
				"custom_ytd_basic_salary": 4000.0,
				"custom_bik_value": 0.0,
				"custom_epf_employee": 440.0,
				"custom_socso_employee": 10.90,
				"custom_eis_employee": 4.50,
				"custom_zakat_deducted": 100.0,
				"custom_cp38_deducted": 0.0,
				"custom_pcb_amount": 180.0,
				"total_deduction": 735.40,
			},
		]

		result = get_ytd_payroll_totals("HR-EMP-002", 2025, "2025-08-31")

		self.assertAlmostEqual(result["ytd_basic_salary"], 8000.0)
		self.assertAlmostEqual(result["ytd_gross_allowances"], 10000.0)
		self.assertAlmostEqual(result["ytd_pcb"], 360.0)
		self.assertAlmostEqual(result["ytd_zakat"], 100.0)
		self.assertAlmostEqual(result["ytd_epf_employee"], 880.0)

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_returns_zeros_when_no_slips(self, mock_frappe):
		"""Employee with no submitted slips returns all-zero totals."""
		mock_frappe.db.get_all.return_value = []

		result = get_ytd_payroll_totals("HR-EMP-003", 2025, "2025-03-31")

		self.assertEqual(result["ytd_basic_salary"], 0.0)
		self.assertEqual(result["ytd_pcb"], 0.0)
		self.assertEqual(result["ytd_epf_employee"], 0.0)
		self.assertEqual(result["ytd_socso"], 0.0)
		self.assertEqual(result["ytd_eis"], 0.0)

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_queries_only_submitted_slips_in_date_range(self, mock_frappe):
		"""get_ytd_payroll_totals queries docstatus=1 and correct date range."""
		mock_frappe.db.get_all.return_value = []

		get_ytd_payroll_totals("HR-EMP-004", 2025, "2025-06-30")

		mock_frappe.db.get_all.assert_called_once()
		call_kwargs = mock_frappe.db.get_all.call_args
		filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
		self.assertEqual(filters["employee"], "HR-EMP-004")
		self.assertEqual(filters["docstatus"], 1)
		self.assertIn("2025-01-01", str(filters["start_date"]))
		self.assertIn("2025-06-30", str(filters["end_date"]))

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_handles_none_slip_fields_gracefully(self, mock_frappe):
		"""Slip with None fields treated as 0 — no TypeError."""
		mock_frappe.db.get_all.return_value = [
			{
				"gross_pay": None,
				"custom_ytd_basic_salary": None,
				"custom_bik_value": None,
				"custom_epf_employee": None,
				"custom_socso_employee": None,
				"custom_eis_employee": None,
				"custom_zakat_deducted": None,
				"custom_cp38_deducted": None,
				"custom_pcb_amount": None,
				"total_deduction": None,
			}
		]

		result = get_ytd_payroll_totals("HR-EMP-005", 2025)
		self.assertEqual(result["ytd_pcb"], 0.0)
		self.assertEqual(result["ytd_basic_salary"], 0.0)


class TestGenerateOutgoingTP3(FrappeTestCase):
	"""Tests for generate_outgoing_tp3() — document creation."""

	def _make_emp_doc(self):
		m = MagicMock()
		m.employee_name = "Ahmad bin Ali"
		m.company = "Arising Packaging"
		m.custom_nric_passport_no = "901201-05-1234"
		m.custom_employee_tax_file_number = "SG 12345678"
		return m

	def _make_company_doc(self):
		m = MagicMock()
		m.company_name = "Arising Packaging Sdn Bhd"
		m.custom_company_tin_number = "C12345678901"
		return m

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_creates_outgoing_tp3_document(self, mock_frappe):
		"""generate_outgoing_tp3 creates and inserts an Employee Outgoing TP3."""
		mock_frappe.db.get_value.side_effect = [
			None,  # relieving_date query (no relieving_date provided)
			self._make_emp_doc(),  # employee fields
			self._make_company_doc(),  # company fields
		]
		mock_frappe.db.get_all.return_value = []
		mock_doc = MagicMock()
		mock_doc.name = "LHDN-TP3-OUT-2025-00001"
		mock_frappe.new_doc.return_value = mock_doc

		result = generate_outgoing_tp3("HR-EMP-001", 2025, "2025-06-30")

		mock_frappe.new_doc.assert_called_once_with("Employee Outgoing TP3")
		mock_doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result, "LHDN-TP3-OUT-2025-00001")

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_ytd_totals_populated_on_document(self, mock_frappe):
		"""generate_outgoing_tp3 sets ytd fields from aggregated slip data."""
		mock_frappe.db.get_value.side_effect = [
			None,
			self._make_emp_doc(),
			self._make_company_doc(),
		]
		mock_frappe.db.get_all.return_value = [
			{
				"gross_pay": 6000.0,
				"custom_ytd_basic_salary": 5000.0,
				"custom_bik_value": 300.0,
				"custom_epf_employee": 550.0,
				"custom_socso_employee": 12.50,
				"custom_eis_employee": 5.00,
				"custom_zakat_deducted": 0.0,
				"custom_cp38_deducted": 0.0,
				"custom_pcb_amount": 250.0,
				"total_deduction": 817.50,
			}
		]
		mock_doc = MagicMock()
		mock_doc.name = "LHDN-TP3-OUT-2025-00002"
		mock_frappe.new_doc.return_value = mock_doc

		generate_outgoing_tp3("HR-EMP-002", 2025, "2025-09-30")

		self.assertAlmostEqual(mock_doc.ytd_pcb, 250.0)
		self.assertAlmostEqual(mock_doc.ytd_epf_employee, 550.0)
		self.assertAlmostEqual(mock_doc.ytd_basic_salary, 5000.0)
		self.assertEqual(mock_doc.tax_year, 2025)
		self.assertEqual(mock_doc.status, "Generated")

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_employer_details_populated_from_company(self, mock_frappe):
		"""generate_outgoing_tp3 fills employer_name and employer_tin from Company."""
		mock_frappe.db.get_value.side_effect = [
			None,
			self._make_emp_doc(),
			self._make_company_doc(),
		]
		mock_frappe.db.get_all.return_value = []
		mock_doc = MagicMock()
		mock_doc.name = "LHDN-TP3-OUT-2025-00003"
		mock_frappe.new_doc.return_value = mock_doc

		generate_outgoing_tp3("HR-EMP-003", 2025, "2025-07-31")

		self.assertEqual(mock_doc.employer_name, "Arising Packaging Sdn Bhd")
		self.assertEqual(mock_doc.employer_tin, "C12345678901")

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_notes_include_retention_warning(self, mock_frappe):
		"""Generated TP3 document includes 7-year retention and 'do not submit' note."""
		mock_frappe.db.get_value.side_effect = [
			None,
			self._make_emp_doc(),
			self._make_company_doc(),
		]
		mock_frappe.db.get_all.return_value = []
		mock_doc = MagicMock()
		mock_doc.name = "LHDN-TP3-OUT-2025-00004"
		mock_frappe.new_doc.return_value = mock_doc

		generate_outgoing_tp3("HR-EMP-004", 2025, "2025-05-31")

		notes = mock_doc.notes
		self.assertIn("7 years", notes)
		self.assertIn("Do NOT submit to LHDN", notes)


class TestHandleEmployeeLeftTP3(FrappeTestCase):
	"""Tests for handle_employee_left_tp3() hook."""

	def _make_doc(self, status="Left", relieving_date="2025-06-30", employee_name="Siti binti Rahmat"):
		doc = MagicMock()
		doc.name = "HR-EMP-90001"
		doc.employee_name = employee_name
		doc.status = status
		doc.relieving_date = relieving_date
		return doc

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.generate_outgoing_tp3")
	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_creates_tp3_when_status_left(self, mock_frappe, mock_generate):
		"""Hook creates outgoing TP3 when Employee status is set to 'Left'."""
		mock_frappe.db.exists.return_value = False
		mock_generate.return_value = "LHDN-TP3-OUT-2025-00010"

		doc = self._make_doc(status="Left")
		handle_employee_left_tp3(doc, "on_update")

		mock_generate.assert_called_once_with(
			employee="HR-EMP-90001",
			tax_year=2025,
			last_working_date="2025-06-30",
		)
		mock_frappe.msgprint.assert_called_once()
		msg_text = str(mock_frappe.msgprint.call_args)
		self.assertIn("LHDN-TP3-OUT-2025-00010", msg_text)

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.generate_outgoing_tp3")
	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_does_not_create_tp3_when_status_not_left(self, mock_frappe, mock_generate):
		"""Hook does nothing when Employee status is not 'Left'."""
		doc = self._make_doc(status="Active")
		handle_employee_left_tp3(doc, "on_update")

		mock_generate.assert_not_called()

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.generate_outgoing_tp3")
	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_prevents_duplicate_tp3_for_same_employee_year(self, mock_frappe, mock_generate):
		"""Hook skips creation when a TP3 already exists for this employee and year."""
		mock_frappe.db.exists.return_value = "LHDN-TP3-OUT-2025-00010"

		doc = self._make_doc(status="Left")
		handle_employee_left_tp3(doc, "on_update")

		mock_generate.assert_not_called()

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.generate_outgoing_tp3")
	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_uses_relieving_date_for_cutoff(self, mock_frappe, mock_generate):
		"""Hook passes relieving_date as last_working_date to generate_outgoing_tp3."""
		mock_frappe.db.exists.return_value = False
		mock_generate.return_value = "LHDN-TP3-OUT-2025-00011"

		doc = self._make_doc(status="Left", relieving_date="2025-09-15")
		handle_employee_left_tp3(doc, "on_update")

		call_kwargs = mock_generate.call_args[1]
		self.assertEqual(call_kwargs["last_working_date"], "2025-09-15")
		self.assertEqual(call_kwargs["tax_year"], 2025)

	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.generate_outgoing_tp3")
	@patch("lhdn_payroll_integration.services.tp3_outgoing_service.frappe")
	def test_logs_error_on_exception_without_raising(self, mock_frappe, mock_generate):
		"""Hook logs error gracefully when generate_outgoing_tp3 raises exception."""
		mock_frappe.db.exists.return_value = False
		mock_generate.side_effect = Exception("DB connection error")

		doc = self._make_doc(status="Left")
		# Should not raise
		handle_employee_left_tp3(doc, "on_update")

		mock_frappe.log_error.assert_called_once()
		error_msg = str(mock_frappe.log_error.call_args)
		self.assertIn("HR-EMP-90001", error_msg)


class TestEmployeeOutgoingTP3DocType(FrappeTestCase):
	"""Tests for Employee Outgoing TP3 DocType field validation."""

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_outgoing_tp3.employee_outgoing_tp3.frappe")
	def test_negative_pcb_raises_error(self, mock_frappe):
		"""DocType validate() raises frappe.throw for negative ytd_pcb."""
		from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_outgoing_tp3.employee_outgoing_tp3 import (
			EmployeeOutgoingTP3,
		)

		doc = EmployeeOutgoingTP3.__new__(EmployeeOutgoingTP3)
		doc.tax_year = 2025
		doc.ytd_pcb = -100.0
		doc.ytd_epf_employee = 0.0

		doc.validate()
		mock_frappe.throw.assert_called_once()
		self.assertIn("negative", str(mock_frappe.throw.call_args).lower())

	@patch("lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_outgoing_tp3.employee_outgoing_tp3.frappe")
	def test_invalid_year_raises_error(self, mock_frappe):
		"""DocType validate() raises frappe.throw for invalid tax_year (e.g. 99)."""
		from lhdn_payroll_integration.lhdn_payroll_integration.doctype.employee_outgoing_tp3.employee_outgoing_tp3 import (
			EmployeeOutgoingTP3,
		)

		doc = EmployeeOutgoingTP3.__new__(EmployeeOutgoingTP3)
		doc.tax_year = 99
		doc.ytd_pcb = 0.0
		doc.ytd_epf_employee = 0.0

		doc.validate()
		mock_frappe.throw.assert_called_once()
		self.assertIn("valid", str(mock_frappe.throw.call_args).lower())
