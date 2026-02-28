"""Tests for Payroll Wage Register report and archive deletion lock — US-107.

Employment Act 1955 Section 61 and Income Tax Act 1967 Section 82 require
employers to maintain wage records for 6 and 7 years respectively.

Test coverage:
- get_columns() returns all required fieldnames
- get_data() queries Salary Slips and returns per-slip rows
- check_deletion_lock() blocks deletion of archived records
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from lhdn_payroll_integration.lhdn_payroll_integration.report.payroll_wage_register.payroll_wage_register import (
    get_columns,
    get_data,
    execute,
)
from lhdn_payroll_integration.services.retention_service import check_deletion_lock

REQUIRED_COLUMN_FIELDNAMES = {
    "employee",
    "employee_name",
    "posting_date",
    "start_date",
    "end_date",
    "gross_pay",
    "total_deductions",
    "net_pay",
}

_MOCK_SLIP_ROW = {
    "employee": "EMP-001",
    "employee_name": "Ahmad bin Abdullah",
    "company": "Test Company",
    "posting_date": "2026-01-31",
    "start_date": "2026-01-01",
    "end_date": "2026-01-31",
    "gross_pay": 5000.0,
    "total_deductions": 800.0,
    "net_pay": 4200.0,
    "epf_employee": 550.0,
    "socso_employee": 19.75,
    "eis_employee": 5.0,
    "pcb_amount": 200.0,
    "lhdn_status": "Valid",
}


class TestWageRegisterColumns(FrappeTestCase):
    """Tests for get_columns() in payroll_wage_register."""

    def test_get_columns_returns_list(self):
        """get_columns() must return a list."""
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        """get_columns() must return at least 8 columns for a valid wage register."""
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 8,
            "Wage register must have at least 8 columns")

    def test_get_columns_required_fieldnames(self):
        """get_columns() must include all required fieldnames."""
        columns = get_columns()
        fieldnames = {c.get("fieldname") for c in columns if isinstance(c, dict)}
        for fn in REQUIRED_COLUMN_FIELDNAMES:
            self.assertIn(fn, fieldnames,
                f"Missing required column fieldname: {fn}")

    def test_get_columns_includes_statutory_deductions(self):
        """get_columns() must include EPF, SOCSO, EIS, and PCB columns."""
        columns = get_columns()
        fieldnames = {c.get("fieldname") for c in columns if isinstance(c, dict)}
        required_statutory = {"epf_employee", "socso_employee", "eis_employee", "pcb_amount"}
        for fn in required_statutory:
            self.assertIn(fn, fieldnames,
                f"Missing statutory deduction column: {fn}")

    def test_get_columns_includes_lhdn_status(self):
        """get_columns() must include lhdn_status for audit traceability."""
        columns = get_columns()
        fieldnames = {c.get("fieldname") for c in columns if isinstance(c, dict)}
        self.assertIn("lhdn_status", fieldnames,
            "Wage register must include LHDN status column")


class TestWageRegisterData(FrappeTestCase):
    """Tests for get_data() in payroll_wage_register."""

    def test_get_data_no_filters_returns_empty(self):
        """get_data({}) must return an empty list when filters are missing."""
        result = get_data({})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_data_missing_company_returns_empty(self):
        """get_data must return [] when company filter is absent."""
        result = get_data({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_data_missing_date_returns_empty(self):
        """get_data must return [] when date filters are absent."""
        result = get_data({"company": "Test Company"})
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration"
        ".report.payroll_wage_register.payroll_wage_register.frappe"
    )
    def test_get_data_queries_salary_slips(self, mock_frappe):
        """get_data() must call frappe.db.sql once and return rows from the query."""
        mock_frappe.db = MagicMock()
        mock_frappe.db.sql.return_value = [dict(_MOCK_SLIP_ROW)]
        mock_frappe.utils = MagicMock()

        result = get_data({
            "company": "Test Company",
            "from_date": "2026-01-01",
            "to_date": "2026-12-31",
        })

        mock_frappe.db.sql.assert_called_once()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["employee"], "EMP-001")
        self.assertEqual(result[0]["gross_pay"], 5000.0)

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration"
        ".report.payroll_wage_register.payroll_wage_register.frappe"
    )
    def test_get_data_includes_all_required_fields(self, mock_frappe):
        """Each row returned by get_data() must contain all required fieldnames."""
        mock_frappe.db = MagicMock()
        mock_frappe.db.sql.return_value = [
            {
                "employee": "EMP-002",
                "employee_name": "Siti binti Azman",
                "company": "Test Company",
                "posting_date": "2026-02-28",
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "gross_pay": 4000.0,
                "total_deductions": 600.0,
                "net_pay": 3400.0,
                "epf_employee": 440.0,
                "socso_employee": 15.80,
                "eis_employee": 4.0,
                "pcb_amount": 120.0,
                "lhdn_status": "",
            }
        ]
        mock_frappe.utils = MagicMock()

        result = get_data({
            "company": "Test Company",
            "from_date": "2026-01-01",
            "to_date": "2026-12-31",
        })

        self.assertEqual(len(result), 1)
        row = result[0]
        for fn in REQUIRED_COLUMN_FIELDNAMES:
            self.assertIn(fn, row,
                f"Missing required field in result row: {fn}")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration"
        ".report.payroll_wage_register.payroll_wage_register.frappe"
    )
    def test_get_data_returns_multiple_slips(self, mock_frappe):
        """get_data() must return one row per Salary Slip in the date range."""
        mock_frappe.db = MagicMock()
        mock_frappe.db.sql.return_value = [
            dict(_MOCK_SLIP_ROW),
            {
                **_MOCK_SLIP_ROW,
                "posting_date": "2026-02-28",
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
            },
        ]
        mock_frappe.utils = MagicMock()

        result = get_data({
            "company": "Test Company",
            "from_date": "2026-01-01",
            "to_date": "2026-12-31",
        })

        self.assertEqual(len(result), 2,
            "get_data must return one row per Salary Slip")

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration"
        ".report.payroll_wage_register.payroll_wage_register.frappe"
    )
    def test_get_data_net_pay_is_float(self, mock_frappe):
        """Net pay values in result rows must be floats rounded to 2 decimal places."""
        mock_frappe.db = MagicMock()
        mock_frappe.db.sql.return_value = [dict(_MOCK_SLIP_ROW)]
        mock_frappe.utils = MagicMock()

        result = get_data({
            "company": "Test Company",
            "from_date": "2026-01-01",
            "to_date": "2026-12-31",
        })

        self.assertIsInstance(result[0]["net_pay"], float,
            "net_pay must be a float")
        self.assertIsInstance(result[0]["gross_pay"], float,
            "gross_pay must be a float")
        self.assertIsInstance(result[0]["total_deductions"], float,
            "total_deductions must be a float")

    def test_execute_returns_columns_and_data_tuple(self):
        """execute() must return a 2-tuple of (columns, data)."""
        cols, data = execute({})
        self.assertIsInstance(cols, list)
        self.assertIsInstance(data, list)

    def test_execute_columns_matches_get_columns(self):
        """Columns from execute() must match get_columns()."""
        cols_exec, _ = execute({})
        cols_direct = get_columns()
        self.assertEqual(len(cols_exec), len(cols_direct),
            "execute() must return same columns as get_columns()")


class TestWageRegisterDeletionLock(FrappeTestCase):
    """Tests for archive-based deletion lock on Salary Slip — US-107.

    The before_delete hook must prevent permanent deletion of LHDN-archived
    records in line with ITA 1967 Section 82 (7-year retention requirement).
    """

    def test_archived_salary_slip_cannot_be_deleted(self):
        """Salary Slip with custom_lhdn_archived=1 must raise ValidationError
        when check_deletion_lock is called."""
        doc = MagicMock()
        doc.custom_lhdn_archived = 1
        doc.doctype = "Salary Slip"
        doc.name = "SAL-SLP-2018-00001"

        with self.assertRaises(frappe.ValidationError,
                msg="Archived Salary Slip must not be deletable"):
            check_deletion_lock(doc)

    def test_non_archived_salary_slip_can_be_deleted(self):
        """Salary Slip with custom_lhdn_archived=0 must not raise ValidationError."""
        doc = MagicMock()
        doc.custom_lhdn_archived = 0
        doc.doctype = "Salary Slip"
        doc.name = "SAL-SLP-2026-00001"

        try:
            check_deletion_lock(doc)
        except frappe.ValidationError:
            self.fail(
                "Non-archived Salary Slip (custom_lhdn_archived=0) "
                "must not raise ValidationError on before_delete"
            )

    def test_archived_expense_claim_cannot_be_deleted(self):
        """Expense Claim with custom_lhdn_archived=1 must also raise ValidationError."""
        doc = MagicMock()
        doc.custom_lhdn_archived = 1
        doc.doctype = "Expense Claim"
        doc.name = "EXP-2018-00001"

        with self.assertRaises(frappe.ValidationError,
                msg="Archived Expense Claim must not be deletable"):
            check_deletion_lock(doc)

    def test_deletion_lock_error_message_mentions_retention(self):
        """The ValidationError raised by check_deletion_lock must reference retention policy."""
        doc = MagicMock()
        doc.custom_lhdn_archived = 1
        doc.doctype = "Salary Slip"
        doc.name = "SAL-SLP-2016-00001"

        try:
            check_deletion_lock(doc)
            self.fail("Expected ValidationError was not raised")
        except frappe.ValidationError as exc:
            self.assertTrue(
                "7-year" in str(exc) or "retention" in str(exc).lower()
                or "archived" in str(exc).lower(),
                f"Error message should mention retention policy: {exc}",
            )
