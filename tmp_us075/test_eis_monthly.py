"""Tests for EIS Monthly Contribution Report Script Report.

US-017: Generate EIS monthly contribution report.

Acceptance criteria:
- New Script Report eis_monthly with filters: Company, Month, Year
- Columns: Employee Name, NRIC, Wages, EIS Employee, EIS Employer, Total
- Sources data from submitted Salary Slips with EIS deduction/earning lines
- Test verifies correct EIS amounts per employee
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee",
    "employee_name",
    "nric",
    "wages",
    "eis_employee",
    "eis_employer",
    "total_eis",
}


class TestEISMonthlyColumns(FrappeTestCase):
    """Tests for get_columns()."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 7)

    def test_get_columns_required_fieldnames(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing column: {required}")

    def test_wages_column_is_currency(self):
        columns = get_columns()
        wages_col = next((c for c in columns if c.get("fieldname") == "wages"), None)
        self.assertIsNotNone(wages_col, "wages column missing")
        self.assertEqual(wages_col.get("fieldtype"), "Currency")

    def test_total_eis_column_is_currency(self):
        columns = get_columns()
        total_col = next((c for c in columns if c.get("fieldname") == "total_eis"), None)
        self.assertIsNotNone(total_col, "total_eis column missing")
        self.assertEqual(total_col.get("fieldtype"), "Currency")


class TestEISMonthlyData(FrappeTestCase):
    """Tests for get_data()."""

    def test_get_data_returns_list(self):
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 2026})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_empty_for_distant_past(self):
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 1900})
        result = get_data(filters)
        self.assertEqual(result, [])

    def test_get_data_none_filters(self):
        result = get_data(None)
        self.assertIsInstance(result, list)

    def test_get_data_rows_have_total_eis(self):
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        for row in rows:
            expected = (row.get("eis_employee") or 0) + (row.get("eis_employer") or 0)
            self.assertAlmostEqual(
                row.get("total_eis", 0),
                expected,
                places=2,
                msg=f"total_eis mismatch for {row.get('employee_name')}",
            )

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"company": "_Test Company", "year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)


# ---------------------------------------------------------------------------
# US-075: EIS Contribution Validation in EIS Monthly Report
# ---------------------------------------------------------------------------
from datetime import date as _date_cls  # noqa: E402


class TestEisMonthlyValidation(FrappeTestCase):
    """Tests for get_eis_contribution_warning() — US-075."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.eis_monthly.eis_monthly import (
            get_eis_contribution_warning,
        )
        self.warn = get_eis_contribution_warning
        self.payroll_date = _date_cls(2025, 1, 1)

    def _dob_for_age(self, age):
        return _date_cls(self.payroll_date.year - age, self.payroll_date.month, self.payroll_date.day)

    def test_columns_include_eis_warning(self):
        """US-075: EIS monthly report must include eis_contribution_warning column."""
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("eis_contribution_warning", fieldnames)

    def test_foreign_worker_with_eis_warns(self):
        """Foreign worker incorrectly has EIS deducted -> warning issued."""
        dob = self._dob_for_age(30)
        warning = self.warn(
            wages=5000, date_of_birth=dob, is_foreign=True,
            actual_employee=10.0, actual_employer=10.0,
            payroll_date=self.payroll_date,
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("foreign", warning.lower())

    def test_foreign_worker_no_eis_no_warning(self):
        """Foreign worker with zero EIS -> no warning."""
        dob = self._dob_for_age(30)
        warning = self.warn(
            wages=5000, date_of_birth=dob, is_foreign=True,
            actual_employee=0.0, actual_employer=0.0,
            payroll_date=self.payroll_date,
        )
        self.assertEqual(warning, "")

    def test_age_17_with_eis_warns(self):
        """Employee aged 17 (exempt) incorrectly has EIS -> warning."""
        dob = self._dob_for_age(17)
        warning = self.warn(
            wages=3000, date_of_birth=dob, is_foreign=False,
            actual_employee=6.0, actual_employer=6.0,
            payroll_date=self.payroll_date,
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("exempt", warning.lower())

    def test_age_60_with_eis_warns(self):
        """Employee aged 60 (exempt) incorrectly has EIS -> warning."""
        dob = self._dob_for_age(60)
        warning = self.warn(
            wages=3000, date_of_birth=dob, is_foreign=False,
            actual_employee=6.0, actual_employer=6.0,
            payroll_date=self.payroll_date,
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("exempt", warning.lower())

    def test_wage_7000_correct_ceiling_no_warning(self):
        """Wages RM7,000 with EIS correctly on RM6,000 ceiling -> no warning."""
        dob = self._dob_for_age(30)
        correct_eis = round(6000 * 0.002, 2)  # 12.00
        warning = self.warn(
            wages=7000, date_of_birth=dob, is_foreign=False,
            actual_employee=correct_eis, actual_employer=correct_eis,
            payroll_date=self.payroll_date,
        )
        self.assertEqual(warning, "")

    def test_wage_7000_wrong_ceiling_warns(self):
        """Wages RM7,000 with EIS on full 7000 (uncapped) -> warning mentioning ceiling."""
        dob = self._dob_for_age(30)
        wrong_eis = round(7000 * 0.002, 2)  # 14.00 — should be 12.00
        warning = self.warn(
            wages=7000, date_of_birth=dob, is_foreign=False,
            actual_employee=wrong_eis, actual_employer=wrong_eis,
            payroll_date=self.payroll_date,
        )
        self.assertGreater(len(warning), 0)
        self.assertIn("ceiling", warning.lower())

    def test_correct_contribution_no_warning(self):
        """Correctly computed EIS -> no warning."""
        dob = self._dob_for_age(30)
        correct_eis = round(5000 * 0.002, 2)  # 10.00
        warning = self.warn(
            wages=5000, date_of_birth=dob, is_foreign=False,
            actual_employee=correct_eis, actual_employer=correct_eis,
            payroll_date=self.payroll_date,
        )
        self.assertEqual(warning, "")

    def test_no_dob_skips_validation(self):
        """Missing date_of_birth -> no warning (cannot validate)."""
        warning = self.warn(
            wages=5000, date_of_birth=None, is_foreign=False,
            actual_employee=10.0, actual_employer=10.0,
        )
        self.assertEqual(warning, "")
