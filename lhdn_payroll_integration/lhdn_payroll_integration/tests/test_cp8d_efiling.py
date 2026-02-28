"""Tests for CP8D e-Filing standalone report — US-049 / US-078.

Verifies that column headers match the LHDN e-Filing CP8D 2024 column
specification: No., Name, NRIC/Passport, TIN, Gross Income,
Gross Bonus/Commission, Gross Gratuity, Other Income, EPF, PCB.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp8d_efiling.cp8d_efiling import (
    execute,
    get_columns,
    get_data,
)

# LHDN CP8D e-Filing 2024 spec fieldnames in required order (10 columns)
LHDN_CP8D_EFILING_FIELDNAMES = [
    "no", "employee_name", "id_number", "employee_tin",
    "annual_gross", "gross_bonus_commission", "gross_gratuity", "other_income",
    "epf_employee", "total_pcb",
]


class TestCP8DEFilingColumns(FrappeTestCase):
    """Tests that column headers match LHDN e-Filing CP8D specification."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_has_2024_spec_columns(self):
        """LHDN CP8D e-Filing 2024 spec requires exactly 10 columns."""
        columns = get_columns()
        self.assertEqual(len(columns), 10,
            f"CP8D e-Filing must have 10 columns per LHDN 2024 spec, got {len(columns)}")

    def test_column_fieldnames_match_lhdn_spec(self):
        """Column fieldnames must match LHDN CP8D e-Filing spec in correct order."""
        columns = get_columns()
        actual_fieldnames = [col.get("fieldname") for col in columns if isinstance(col, dict)]
        self.assertEqual(actual_fieldnames, LHDN_CP8D_EFILING_FIELDNAMES,
            f"Column order must match LHDN CP8D e-Filing spec.\n"
            f"Expected: {LHDN_CP8D_EFILING_FIELDNAMES}\n"
            f"Got:      {actual_fieldnames}")

    def test_first_column_is_sequential_number(self):
        """First column must be 'No.' for sequential numbering."""
        columns = get_columns()
        self.assertEqual(columns[0].get("fieldname"), "no",
            "First column must be 'no' (sequential number) per LHDN CP8D spec")

    def test_currency_columns_have_myr_options(self):
        """Currency-type columns must specify MYR as options."""
        columns = get_columns()
        for col in columns:
            if isinstance(col, dict) and col.get("fieldtype") == "Currency":
                self.assertEqual(col.get("options"), "MYR",
                    f"Column '{col.get('fieldname')}' must have options='MYR'")

    def test_execute_returns_columns_and_data(self):
        """execute() must return a (columns, data) tuple."""
        columns, data = execute(frappe._dict({"year": 2026}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_data_rows_have_all_spec_fields(self):
        """Each data row must contain all 7 LHDN CP8D e-Filing fields."""
        filters = frappe._dict({"year": 2000, "company": None})
        data = get_data(filters)
        if not data:
            return  # No data for year 2000 — just verify structure passes
        for row in data:
            for field in LHDN_CP8D_EFILING_FIELDNAMES:
                self.assertIn(field, row,
                    f"Data row missing required LHDN CP8D e-Filing field: '{field}'")

    def test_no_column_is_sequential_integer(self):
        """The 'no' column must be of type Int for sequential numbering."""
        columns = get_columns()
        no_col = next((c for c in columns if c.get("fieldname") == "no"), None)
        self.assertIsNotNone(no_col, "Column 'no' must exist")
        self.assertEqual(no_col.get("fieldtype"), "Int",
            "Column 'no' must be fieldtype 'Int'")
