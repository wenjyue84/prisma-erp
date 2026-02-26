"""Tests for LHDN Payroll Compliance script report.

TDD RED phase: these tests fail because the report module does not exist yet.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.lhdn_payroll_compliance.lhdn_payroll_compliance import (
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "document_type",
    "document_name",
    "employee",
    "period",
    "amount",
    "lhdn_status",
    "uuid",
    "submitted_at",
    "validated_at",
}


class TestComplianceReportColumns(FrappeTestCase):
    """Tests for get_columns() function."""

    def test_get_columns_returns_list(self):
        """get_columns() must return a list."""
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        """get_columns() must return at least 8 columns."""
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 8)

    def test_get_columns_required_fieldnames(self):
        """get_columns() must include all required fieldnames."""
        columns = get_columns()
        fieldnames = set()
        for col in columns:
            if isinstance(col, dict):
                fieldnames.add(col.get("fieldname"))
            elif isinstance(col, str):
                # Handle "Label:fieldtype/fieldname:width" format
                parts = col.split(":")
                if len(parts) >= 2:
                    fieldnames.add(parts[1].split("/")[-1] if "/" in parts[1] else parts[1])
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing fieldname: {required}")


class TestComplianceReportData(FrappeTestCase):
    """Tests for get_data() function."""

    def test_get_data_returns_list(self):
        """get_data() must return a list (even if empty)."""
        filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        result = get_data(filters)
        self.assertIsInstance(result, list)

    def test_get_data_rows_have_required_keys(self):
        """Rows returned by get_data() must contain expected keys."""
        filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No Salary Slips in test DB — data shape test skipped")
        row = rows[0]
        for key in ["document_type", "document_name", "lhdn_status"]:
            self.assertIn(key, row, f"Row missing key: {key}")

    def test_get_data_document_type_is_salary_slip(self):
        """All rows from get_data() must have document_type == 'Salary Slip'."""
        filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No Salary Slips in test DB")
        for row in rows:
            self.assertEqual(row.get("document_type"), "Salary Slip")
