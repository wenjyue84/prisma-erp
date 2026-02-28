"""Tests for CP39 PCB Remittance script report.

Verifies output columns and row shape for the monthly PCB remittance
file compatible with LHDN's e-PCB portal.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee_tin",
    "id_number",
    "employee_name",
    "gross_salary",
    "pcb_amount",
    "pcb_amount",
    "zakat_amount",
    "period",
}


class TestCP39ReportColumns(FrappeTestCase):
    """Tests for get_columns() function."""

    def test_get_columns_returns_list(self):
        """get_columns() must return a list."""
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        """get_columns() must return at least 6 columns."""
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 6)

    def test_get_columns_required_fieldnames(self):
        """get_columns() must include all required fieldnames."""
        columns = get_columns()
        fieldnames = set()
        for col in columns:
            if isinstance(col, dict):
                fieldnames.add(col.get("fieldname"))
            elif isinstance(col, str):
                parts = col.split(":")
                if len(parts) >= 2:
                    fn = parts[1].split("/")[-1] if "/" in parts[1] else parts[1]
                    fieldnames.add(fn)
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing fieldname: {required}")

    def test_get_columns_currency_fields_have_options(self):
        """Currency columns must declare MYR as options."""
        columns = get_columns()
        for col in columns:
            if isinstance(col, dict) and col.get("fieldtype") == "Currency":
                self.assertEqual(
                    col.get("options"), "MYR",
                    f"Column {col.get('fieldname')} missing MYR options"
                )


class TestCP39ReportData(FrappeTestCase):
    """Tests for get_data() function."""

    def test_get_data_returns_list_empty_filters(self):
        """get_data() must return a list with no filters."""
        result = get_data(frappe._dict())
        self.assertIsInstance(result, list)

    def test_get_data_returns_list_with_year_filter(self):
        """get_data() must return a list when filtered by year."""
        filters = frappe._dict({"year": 2026})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_rows_have_required_keys(self):
        """Rows must contain all required fieldnames."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No submitted PCB Salary Slips in test DB — shape test skipped")
        row = rows[0]
        for key in REQUIRED_FIELDNAMES:
            self.assertIn(key, row, f"Row missing required key: {key}")

    def test_get_data_only_submitted_slips(self):
        """All rows must come from submitted (docstatus=1) Salary Slips."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — docstatus test skipped")
        slip_names = [r["salary_slip"] for r in rows]
        for name in slip_names:
            docstatus = frappe.db.get_value("Salary Slip", name, "docstatus")
            self.assertEqual(docstatus, 1, f"Salary Slip {name} is not submitted")

    def test_get_data_pcb_amount_positive(self):
        """All rows must have pcb_amount > 0."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — pcb_amount test skipped")
        for row in rows:
            self.assertGreater(
                row.get("pcb_amount", 0), 0,
                f"Row {row.get('salary_slip')} has zero PCB amount"
            )

    def test_get_data_month_filter(self):
        """Month filter must restrict results to the specified month."""
        filters = frappe._dict({"year": 2026, "month": "01"})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No January 2026 PCB slips — month filter test skipped")
        for row in rows:
            period = row.get("period", "")
            self.assertIn("2026-01", period, f"Row period {period!r} not in Jan 2026")


class TestCP39ReportExecute(FrappeTestCase):
    """Tests for execute() function (the entrypoint called by Frappe)."""

    def test_execute_returns_tuple(self):
        """execute() must return a (columns, data) tuple."""
        result = execute(frappe._dict())
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_execute_columns_is_list(self):
        """First element of execute() result must be a list."""
        columns, _ = execute(frappe._dict())
        self.assertIsInstance(columns, list)

    def test_execute_data_is_list(self):
        """Second element of execute() result must be a list."""
        _, data = execute(frappe._dict())
        self.assertIsInstance(data, list)
