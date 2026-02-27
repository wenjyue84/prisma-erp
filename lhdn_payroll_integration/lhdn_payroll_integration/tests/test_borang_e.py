"""Tests for Borang E (Form E) Script Report.

US-014: Generate Borang E (Form E) employer annual return.

Acceptance criteria:
- New Script Report borang_e with filters: Company, Year
- Output: company details, total employees, total gross remuneration,
  total PCB withheld, total EPF employer, total SOCSO employer
- CP8D employee list per employee included as sub-table
- Test verifies company-level totals match sum of individual EA Form data
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.borang_e.borang_e import (
    execute,
    get_columns,
    get_data,
)
from lhdn_payroll_integration.lhdn_payroll_integration.report.ea_form.ea_form import (
    get_data as get_ea_data,
)

REQUIRED_FIELDNAMES = {
    "row_type",
    "company",
    "year",
    "total_employees",
    "total_gross",
    "epf_employer",
    "socso_employer",
    "total_pcb",
}


class TestBorangEColumns(FrappeTestCase):
    """Tests for get_columns()."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 8)

    def test_get_columns_required_fieldnames(self):
        columns = get_columns()
        fieldnames = {col["fieldname"] for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing column: {required}")


class TestBorangEData(FrappeTestCase):
    """Tests for get_data()."""

    def test_get_data_returns_list(self):
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_empty_for_no_slips(self):
        """Report returns empty list when there are no salary slips for the year."""
        filters = frappe._dict({"company": "_Test Company", "year": 1900})
        result = get_data(filters)
        self.assertEqual(result, [])

    def test_get_data_none_filters(self):
        """get_data() accepts None filters without raising."""
        result = get_data(None)
        self.assertIsInstance(result, list)

    def test_first_row_is_summary_when_data_exists(self):
        """When rows are returned, first row must be the Summary row."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No Salary Slips in test DB — structure test skipped")
        self.assertEqual(rows[0].get("row_type"), "Summary")

    def test_summary_row_has_company(self):
        """Summary row must include the company name from filters."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No Salary Slips in test DB")
        self.assertEqual(rows[0].get("company"), "_Test Company")

    def test_cp8d_rows_follow_summary(self):
        """All rows after the first must have row_type == 'CP8D'."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        if len(rows) < 2:
            self.skipTest("No CP8D detail rows available")
        for row in rows[1:]:
            self.assertEqual(row.get("row_type"), "CP8D")

    def test_cp8d_rows_have_employee_fields(self):
        """CP8D rows must have employee and employee_name fields."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        if len(rows) < 2:
            self.skipTest("No CP8D detail rows available")
        for row in rows[1:]:
            self.assertIn("employee", row)
            self.assertIn("employee_name", row)

    def test_execute_returns_columns_and_data_tuple(self):
        """execute() must return (columns, data) tuple."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        result = execute(filters)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        columns, data = result
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_company_totals_match_ea_form_sum(self):
        """Company-level totals in Borang E must match sum of individual EA Form data.

        This is the key acceptance criterion for US-014.
        """
        filters = frappe._dict({"company": "_Test Company", "year": 2026})

        ea_rows = get_ea_data(filters)
        if not ea_rows:
            self.skipTest("No Salary Slips in test DB — totals test skipped")

        borang_rows = get_data(filters)
        self.assertTrue(borang_rows, "Borang E returned no rows despite EA Form having data")

        summary = borang_rows[0]

        # Totals from EA Form
        ea_total_gross = sum(float(r.get("total_gross") or 0) for r in ea_rows)
        ea_total_pcb = sum(float(r.get("pcb_total") or 0) for r in ea_rows)

        self.assertAlmostEqual(
            float(summary.get("total_gross") or 0),
            ea_total_gross,
            places=2,
            msg="Borang E total_gross must match sum of EA Form total_gross",
        )
        self.assertAlmostEqual(
            float(summary.get("total_pcb") or 0),
            ea_total_pcb,
            places=2,
            msg="Borang E total_pcb must match sum of EA Form pcb_total",
        )
        self.assertEqual(
            summary.get("total_employees"),
            len(ea_rows),
            "Borang E total_employees must equal count of EA Form rows",
        )

    def test_summary_total_employees_is_int(self):
        """total_employees in summary must be an integer."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No Salary Slips in test DB")
        val = rows[0].get("total_employees")
        self.assertIsInstance(val, int)

    def test_summary_total_gross_is_non_negative(self):
        """total_gross in summary must be >= 0."""
        filters = frappe._dict({"company": "_Test Company", "year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No Salary Slips in test DB")
        self.assertGreaterEqual(float(rows[0].get("total_gross") or 0), 0)
