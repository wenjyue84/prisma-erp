"""Tests for LHDN Payroll Compliance script report.

Covers Salary Slip + Expense Claim UNION ALL report (US-026).
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

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

VALID_DOCUMENT_TYPES = {"Salary Slip", "Expense Claim"}


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
            self.skipTest("No records in test DB — data shape test skipped")
        row = rows[0]
        for key in ["document_type", "document_name", "lhdn_status"]:
            self.assertIn(key, row, f"Row missing key: {key}")

    def test_get_data_document_types_are_valid(self):
        """All rows must have document_type of 'Salary Slip' or 'Expense Claim'."""
        filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No records in test DB")
        for row in rows:
            # document_type is never modified by indicator logic; only lhdn_status is
            self.assertIn(
                row.get("document_type"),
                VALID_DOCUMENT_TYPES,
                f"Unexpected document_type: {row.get('document_type')}",
            )


class TestComplianceReportExpenseClaims(FrappeTestCase):
    """Tests verifying Expense Claim rows appear in report output alongside Salary Slip rows."""

    def test_expense_claim_rows_appear_in_report(self):
        """Report must return both Expense Claim and Salary Slip rows when mock data contains them."""
        mock_rows = [
            frappe._dict({
                "document_type": "Expense Claim",
                "document_name": "EXP-TEST-001",
                "employee": "EMP-TEST-001",
                "period": "2026-01-15",
                "amount": 500.0,
                "lhdn_status": "Pending",
                "uuid": None,
                "submitted_at": None,
                "validated_at": None,
            }),
            frappe._dict({
                "document_type": "Salary Slip",
                "document_name": "SS-TEST-001",
                "employee": "EMP-TEST-001",
                "period": "2026-01-01 - 2026-01-31",
                "amount": 5000.0,
                "lhdn_status": "Valid",
                "uuid": "uuid-1234",
                "submitted_at": None,
                "validated_at": None,
            }),
        ]
        with patch("frappe.db.sql", return_value=mock_rows):
            filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
            rows = get_data(filters)

        doc_types = {r.get("document_type") for r in rows}
        self.assertIn("Expense Claim", doc_types, "Expense Claim rows missing from report")
        self.assertIn("Salary Slip", doc_types, "Salary Slip rows missing from report")

    def test_expense_claim_rows_have_correct_keys(self):
        """Expense Claim rows must contain all required output keys."""
        mock_rows = [
            frappe._dict({
                "document_type": "Expense Claim",
                "document_name": "EXP-TEST-002",
                "employee": "EMP-TEST-001",
                "period": "2026-01-20",
                "amount": 250.0,
                "lhdn_status": "Pending",
                "uuid": None,
                "submitted_at": None,
                "validated_at": None,
            }),
        ]
        with patch("frappe.db.sql", return_value=mock_rows):
            filters = frappe._dict({"from_date": "2026-01-01", "to_date": "2026-12-31"})
            rows = get_data(filters)

        ec_rows = [r for r in rows if r.get("document_type") == "Expense Claim"]
        self.assertEqual(len(ec_rows), 1)
        row = ec_rows[0]
        for key in ["document_type", "document_name", "employee", "period", "amount", "lhdn_status"]:
            self.assertIn(key, row, f"Expense Claim row missing key: {key}")
        self.assertEqual(row["document_type"], "Expense Claim")
        self.assertEqual(row["document_name"], "EXP-TEST-002")
