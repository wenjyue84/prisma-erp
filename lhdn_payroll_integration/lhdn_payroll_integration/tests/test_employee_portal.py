"""
Tests for US-087: Employee Self-Service Portal

Covers:
- _get_employee_for_user(): returns employee for session user
- _check_employee_permission(): blocks cross-employee access
- get_my_payslips(): returns payslips for logged-in employee
- get_my_ea_forms(): returns distinct tax years
- get_my_ytd_summary(): returns aggregated YTD figures
- get_my_tp1_declarations(): returns current-year TP1 records
- submit_tp1_form(): creates/updates Employee TP1 Relief
- Employee isolation: employee A cannot access employee B records
"""

from unittest.mock import MagicMock, patch, call
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.api.employee_portal import (
    _get_employee_for_user,
    _check_employee_permission,
    get_my_payslips,
    get_my_ea_forms,
    get_my_ytd_summary,
    get_my_tp1_declarations,
    submit_tp1_form,
)


class TestGetEmployeeForUser(FrappeTestCase):
    """Tests for _get_employee_for_user() helper."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.session")
    def test_returns_employee_for_valid_user(self, mock_session, mock_get_value):
        mock_session.user = "alice@example.com"
        mock_get_value.return_value = "EMP-ALICE"

        result = _get_employee_for_user()

        self.assertEqual(result, "EMP-ALICE")
        mock_get_value.assert_called_once_with(
            "Employee", {"user_id": "alice@example.com"}, "name"
        )

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.throw")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.session")
    def test_throws_when_no_employee_linked(self, mock_session, mock_get_value, mock_throw):
        mock_session.user = "stranger@example.com"
        mock_get_value.return_value = None

        _get_employee_for_user()

        mock_throw.assert_called_once()
        args = mock_throw.call_args[0]
        self.assertIn("No Employee record", str(args[0]))


class TestCheckEmployeePermission(FrappeTestCase):
    """Tests for _check_employee_permission() guard."""

    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_allows_own_employee(self, mock_get_emp):
        mock_get_emp.return_value = "EMP-001"

        # Should not raise
        _check_employee_permission("EMP-001")

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.throw")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_blocks_other_employee(self, mock_get_emp, mock_throw):
        mock_get_emp.return_value = "EMP-ALICE"

        _check_employee_permission("EMP-BOB")

        mock_throw.assert_called_once()
        args = mock_throw.call_args[0]
        self.assertIn("not permitted", str(args[0]).lower())


class TestGetMyPayslips(FrappeTestCase):
    """Tests for get_my_payslips()."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_payslips_for_logged_in_employee(self, mock_get_emp, mock_get_list):
        mock_get_emp.return_value = "EMP-001"
        mock_slips = [
            {
                "name": "SAL-2025-001",
                "employee": "EMP-001",
                "employee_name": "Alice",
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
                "gross_pay": 5000.0,
                "net_pay": 4200.0,
                "total_deduction": 800.0,
            }
        ]
        mock_get_list.return_value = mock_slips

        result = get_my_payslips()

        self.assertEqual(result, mock_slips)
        mock_get_list.assert_called_once_with(
            "Salary Slip",
            filters={"employee": "EMP-001", "docstatus": 1},
            fields=[
                "name",
                "employee",
                "employee_name",
                "start_date",
                "end_date",
                "gross_pay",
                "net_pay",
                "total_deduction",
            ],
            order_by="end_date desc",
        )

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_empty_list_when_no_payslips(self, mock_get_emp, mock_get_list):
        mock_get_emp.return_value = "EMP-001"
        mock_get_list.return_value = []

        result = get_my_payslips()

        self.assertEqual(result, [])

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_only_fetches_own_employee_payslips(self, mock_get_emp, mock_get_list):
        """Verifies payslips are filtered by the logged-in employee, not another."""
        mock_get_emp.return_value = "EMP-ALICE"
        mock_get_list.return_value = []

        get_my_payslips()

        # Ensure the filter uses the logged-in employee
        call_filters = mock_get_list.call_args[1]["filters"]
        self.assertEqual(call_filters["employee"], "EMP-ALICE")


class TestGetMyEAForms(FrappeTestCase):
    """Tests for get_my_ea_forms()."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.sql")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_tax_years_for_employee(self, mock_get_emp, mock_sql):
        mock_get_emp.return_value = "EMP-001"
        mock_sql.return_value = [{"tax_year": 2025}, {"tax_year": 2024}]

        result = get_my_ea_forms()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["tax_year"], 2025)
        # Verify employee param passed to SQL
        sql_params = mock_sql.call_args[0][1]
        self.assertEqual(sql_params["employee"], "EMP-001")

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.sql")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_empty_when_no_payslips(self, mock_get_emp, mock_sql):
        mock_get_emp.return_value = "EMP-001"
        mock_sql.return_value = []

        result = get_my_ea_forms()

        self.assertEqual(result, [])


class TestGetMyYTDSummary(FrappeTestCase):
    """Tests for get_my_ytd_summary()."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.sql")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_ytd_totals(self, mock_get_emp, mock_sql):
        mock_get_emp.return_value = "EMP-001"
        mock_sql.return_value = [
            {
                "ytd_gross": 60000.0,
                "ytd_net": 50000.0,
                "ytd_deductions": 10000.0,
                "slip_count": 12,
            }
        ]

        result = get_my_ytd_summary()

        self.assertEqual(result["ytd_gross"], 60000.0)
        self.assertEqual(result["ytd_net"], 50000.0)
        self.assertEqual(result["ytd_deductions"], 10000.0)
        self.assertEqual(result["slip_count"], 12)

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.sql")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_zeros_when_no_slips(self, mock_get_emp, mock_sql):
        mock_get_emp.return_value = "EMP-001"
        mock_sql.return_value = []

        result = get_my_ytd_summary()

        self.assertEqual(result["ytd_gross"], 0)
        self.assertEqual(result["ytd_net"], 0)
        self.assertEqual(result["ytd_deductions"], 0)
        self.assertEqual(result["slip_count"], 0)

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.sql")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_uses_current_year_date_range(self, mock_get_emp, mock_sql):
        mock_get_emp.return_value = "EMP-001"
        mock_sql.return_value = [{"ytd_gross": 0, "ytd_net": 0, "ytd_deductions": 0, "slip_count": 0}]

        get_my_ytd_summary()

        sql_params = mock_sql.call_args[0][1]
        self.assertIn("year_start", sql_params)
        self.assertIn("today", sql_params)
        # year_start should be January 1 of current year
        self.assertTrue(sql_params["year_start"].endswith("-01-01"))


class TestGetMyTP1Declarations(FrappeTestCase):
    """Tests for get_my_tp1_declarations()."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_tp1_for_current_year(self, mock_get_emp, mock_get_list):
        mock_get_emp.return_value = "EMP-001"
        mock_records = [
            {
                "name": "TP1-2025-001",
                "employee": "EMP-001",
                "tax_year": 2025,
                "total_reliefs": 15000.0,
                "self_relief": 9000.0,
            }
        ]
        mock_get_list.return_value = mock_records

        result = get_my_tp1_declarations()

        self.assertEqual(result, mock_records)
        call_filters = mock_get_list.call_args[1]["filters"]
        self.assertEqual(call_filters["employee"], "EMP-001")
        # Should filter by current year
        from frappe.utils import getdate, nowdate
        current_year = getdate(nowdate()).year
        self.assertEqual(call_filters["tax_year"], current_year)

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_returns_empty_when_no_declarations(self, mock_get_emp, mock_get_list):
        mock_get_emp.return_value = "EMP-001"
        mock_get_list.return_value = []

        result = get_my_tp1_declarations()

        self.assertEqual(result, [])


class TestSubmitTP1Form(FrappeTestCase):
    """Tests for submit_tp1_form()."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.new_doc")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_creates_new_tp1_record(self, mock_get_emp, mock_get_value, mock_new_doc):
        mock_get_emp.return_value = "EMP-001"
        mock_get_value.return_value = None  # No existing record

        mock_doc = MagicMock()
        mock_doc.name = "TP1-2025-001"
        mock_new_doc.return_value = mock_doc

        data = {"tax_year": 2025, "self_relief": 9000.0, "life_insurance": 3000.0}
        result = submit_tp1_form(data)

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["name"], "TP1-2025-001")
        mock_doc.insert.assert_called_once()
        self.assertEqual(mock_doc.employee, "EMP-001")
        self.assertEqual(mock_doc.tax_year, 2025)

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.get_doc")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_updates_existing_tp1_record(self, mock_get_emp, mock_get_value, mock_get_doc):
        mock_get_emp.return_value = "EMP-001"
        mock_get_value.return_value = "TP1-2025-001"  # Existing record

        mock_doc = MagicMock()
        mock_doc.name = "TP1-2025-001"
        mock_get_doc.return_value = mock_doc

        data = {"tax_year": 2025, "self_relief": 9000.0, "spouse_relief": 4000.0}
        result = submit_tp1_form(data)

        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["name"], "TP1-2025-001")
        mock_doc.save.assert_called_once()

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.new_doc")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_action_is_created_for_new_record(self, mock_get_emp, mock_get_value, mock_new_doc):
        mock_get_emp.return_value = "EMP-001"
        mock_get_value.return_value = None

        mock_doc = MagicMock()
        mock_doc.name = "TP1-NEW"
        mock_new_doc.return_value = mock_doc

        result = submit_tp1_form({"tax_year": 2025})
        self.assertEqual(result["action"], "created")

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.get_doc")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_action_is_updated_for_existing_record(self, mock_get_emp, mock_get_value, mock_get_doc):
        mock_get_emp.return_value = "EMP-001"
        mock_get_value.return_value = "TP1-2025-EXISTING"

        mock_doc = MagicMock()
        mock_doc.name = "TP1-2025-EXISTING"
        mock_get_doc.return_value = mock_doc

        result = submit_tp1_form({"tax_year": 2025})
        self.assertEqual(result["action"], "updated")

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.new_doc")
    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_accepts_json_string_input(self, mock_get_emp, mock_get_value, mock_new_doc):
        """submit_tp1_form should accept a JSON string as well as a dict."""
        mock_get_emp.return_value = "EMP-001"
        mock_get_value.return_value = None
        mock_doc = MagicMock()
        mock_doc.name = "TP1-JSON"
        mock_new_doc.return_value = mock_doc

        import json
        data_str = json.dumps({"tax_year": 2025, "self_relief": 9000.0})
        result = submit_tp1_form(data_str)

        self.assertEqual(result["action"], "created")


class TestEmployeeIsolation(FrappeTestCase):
    """Tests verifying employee A cannot access employee B's records."""

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.throw")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_employee_a_cannot_access_employee_b_via_permission_check(
        self, mock_get_emp, mock_throw
    ):
        """_check_employee_permission blocks access to another employee's data."""
        mock_get_emp.return_value = "EMP-ALICE"

        # Employee Alice tries to access Employee Bob's data
        _check_employee_permission("EMP-BOB")

        mock_throw.assert_called_once()
        error_msg = str(mock_throw.call_args[0][0]).lower()
        self.assertIn("not permitted", error_msg)

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_get_my_payslips_uses_session_user_employee(self, mock_get_emp, mock_get_list):
        """get_my_payslips always queries for the session user's own employee."""
        mock_get_emp.return_value = "EMP-ALICE"
        mock_get_list.return_value = []

        get_my_payslips()

        # Even if the user tries to pass different args, the employee is determined
        # by _get_employee_for_user (which uses frappe.session.user)
        call_filters = mock_get_list.call_args[1]["filters"]
        self.assertEqual(call_filters["employee"], "EMP-ALICE")

    @patch("lhdn_payroll_integration.api.employee_portal.frappe.db.get_list")
    @patch("lhdn_payroll_integration.api.employee_portal._get_employee_for_user")
    def test_get_my_tp1_uses_session_user_employee(self, mock_get_emp, mock_get_list):
        """get_my_tp1_declarations always queries for the session user's own employee."""
        mock_get_emp.return_value = "EMP-BOB"
        mock_get_list.return_value = []

        get_my_tp1_declarations()

        call_filters = mock_get_list.call_args[1]["filters"]
        self.assertEqual(call_filters["employee"], "EMP-BOB")
