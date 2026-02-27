"""Tests for SOCSO Borang 8A monthly contribution schedule script report.

Verifies output columns and row shape for SOCSO (PERKESO) Borang 8A.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.socso_borang_8a.socso_borang_8a import (
    execute,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee_name",
    "nric",
    "socso_member_number",
    "wages",
    "employee_socso",
    "employer_socso",
    "total_socso",
}


class TestSOCSOBorang8AColumns(FrappeTestCase):
    """Tests for get_columns() function."""

    def test_get_columns_returns_list(self):
        """get_columns() must return a list."""
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        """get_columns() must return at least 7 columns."""
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 7)

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

    def test_get_columns_socso_member_number_present(self):
        """get_columns() must include socso_member_number column."""
        columns = get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        self.assertIn("socso_member_number", fieldnames)

    def test_get_columns_total_socso_present(self):
        """get_columns() must include total_socso column."""
        columns = get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        self.assertIn("total_socso", fieldnames)


class TestSOCSOBorang8AData(FrappeTestCase):
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
            self.skipTest("No submitted SOCSO Salary Slips in test DB — shape test skipped")
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

    def test_get_data_socso_amounts_positive(self):
        """All rows must have at least one of employee_socso or employer_socso > 0."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — SOCSO amount test skipped")
        for row in rows:
            employee_socso = row.get("employee_socso", 0) or 0
            employer_socso = row.get("employer_socso", 0) or 0
            self.assertGreater(
                employee_socso + employer_socso, 0,
                f"Row {row.get('salary_slip')} has zero SOCSO amounts"
            )

    def test_get_data_total_socso_equals_sum(self):
        """total_socso must equal employee_socso + employer_socso."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — total_socso sum test skipped")
        for row in rows:
            expected = (row.get("employee_socso") or 0) + (row.get("employer_socso") or 0)
            actual = row.get("total_socso") or 0
            self.assertAlmostEqual(
                actual, expected, places=2,
                msg=f"Row {row.get('salary_slip')}: total_socso mismatch"
            )

    def test_get_data_socso_member_number_field_exists(self):
        """socso_member_number key must exist in each row (may be empty string)."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — socso_member_number field test skipped")
        for row in rows:
            self.assertIn("socso_member_number", row)

    def test_get_data_amounts_sourced_from_deduction_lines(self):
        """Employee SOCSO must come from salary deduction lines, not hardcoded."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — deduction source test skipped")
        # Verify each row references a real Salary Slip
        for row in rows:
            slip_name = row.get("salary_slip")
            self.assertTrue(
                frappe.db.exists("Salary Slip", slip_name),
                f"Salary slip {slip_name} not found in DB"
            )
            # Verify employee_socso matches actual deduction lines
            deduction_total = frappe.db.sql("""
                SELECT COALESCE(SUM(amount), 0)
                FROM `tabSalary Detail`
                WHERE parent = %(slip)s
                  AND parentfield = 'deductions'
                  AND salary_component IN (
                    'SOCSO', 'SOCSO Employee', 'PERKESO', 'PERKESO Employee'
                  )
            """, {"slip": slip_name})[0][0] or 0
            self.assertAlmostEqual(
                row.get("employee_socso") or 0, deduction_total, places=2,
                msg=f"employee_socso for {slip_name} doesn't match deduction lines"
            )


class TestSOCSOBorang8AExecute(FrappeTestCase):
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

    def test_custom_socso_member_number_field_on_employee(self):
        """custom_socso_member_number field must exist on Employee doctype."""
        field_exists = frappe.db.exists(
            "Custom Field",
            {"dt": "Employee", "fieldname": "custom_socso_member_number"}
        )
        self.assertTrue(
            field_exists,
            "custom_socso_member_number field not found on Employee doctype"
        )
