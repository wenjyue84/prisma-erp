"""Tests for CP39 PCB Monthly Remittance Report — US-055.

Verifies the e-PCB Plus mandatory column structure, column ordering, and
data format requirements (Month/Year format, numeric amounts, employer E-Number).
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.cp39_pcb_remittance.cp39_pcb_remittance import (
    execute,
    get_columns,
    get_csv_data,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employer_e_number",
    "month_year",
    "employee_tin",
    "employee_nric",
    "employee_name",
    "pcb_category",
    "gross_remuneration",
    "epf_employee",
    "zakat_amount",
    "cp38_amount",
    "total_pcb",
}

REQUIRED_COLUMN_ORDER = [
    "employer_e_number",
    "month_year",
    "employee_tin",
    "employee_nric",
    "employee_name",
    "pcb_category",
    "gross_remuneration",
    "epf_employee",
    "zakat_amount",
    "cp38_amount",
    "total_pcb",
]


class TestCP39Columns(FrappeTestCase):
    """Verify column structure matches LHDN e-PCB Plus mandatory format."""

    def test_get_columns_returns_list(self):
        columns = get_columns()
        self.assertIsInstance(columns, list)

    def test_get_columns_minimum_count(self):
        columns = get_columns()
        self.assertGreaterEqual(len(columns), 11)

    def test_required_fieldnames_present(self):
        columns = get_columns()
        fieldnames = {col.get("fieldname") for col in columns if isinstance(col, dict)}
        for required in REQUIRED_FIELDNAMES:
            self.assertIn(required, fieldnames, f"Missing fieldname: {required}")

    def test_column_order_matches_lhdn_spec(self):
        """Verify mandatory e-PCB Plus column order is exactly correct."""
        columns = get_columns()
        fieldnames = [col.get("fieldname") for col in columns if isinstance(col, dict)]
        for i, name in enumerate(REQUIRED_COLUMN_ORDER):
            self.assertIn(name, fieldnames, f"Missing column: {name}")
            self.assertEqual(
                fieldnames.index(name),
                i,
                f"Column '{name}' at position {fieldnames.index(name)}, expected {i}",
            )

    def test_currency_columns_have_myr_options(self):
        columns = get_columns()
        for col in columns:
            if isinstance(col, dict) and col.get("fieldtype") == "Currency":
                self.assertEqual(
                    col.get("options"),
                    "MYR",
                    f"Column {col.get('fieldname')} missing MYR options",
                )

    def test_employer_e_number_is_data_column(self):
        columns = get_columns()
        emp_col = next(
            (c for c in columns if c.get("fieldname") == "employer_e_number"), None
        )
        self.assertIsNotNone(emp_col, "employer_e_number column missing")
        self.assertEqual(emp_col.get("fieldtype"), "Data")

    def test_month_year_is_data_column(self):
        columns = get_columns()
        col = next((c for c in columns if c.get("fieldname") == "month_year"), None)
        self.assertIsNotNone(col, "month_year column missing")
        self.assertEqual(col.get("fieldtype"), "Data")

    def test_epf_employee_is_currency_column(self):
        columns = get_columns()
        col = next((c for c in columns if c.get("fieldname") == "epf_employee"), None)
        self.assertIsNotNone(col, "epf_employee column missing")
        self.assertEqual(col.get("fieldtype"), "Currency")


class TestCP39Data(FrappeTestCase):
    """Verify data shape, types, employer header, and CSV export."""

    def _get_company(self):
        return (
            frappe.db.get_single_value("Global Defaults", "default_company")
            or frappe.db.get_value("Company", {}, "name")
        )

    def test_get_data_returns_list(self):
        result = get_data(frappe._dict({"company": None, "month": "01", "year": 2024}))
        self.assertIsInstance(result, list)

    def test_execute_returns_columns_and_data(self):
        columns, data = execute(frappe._dict({"month": "01", "year": 2024}))
        self.assertIsInstance(columns, list)
        self.assertIsInstance(data, list)

    def test_rows_have_all_required_keys(self):
        """Every data row must contain all mandatory LHDN e-PCB Plus field keys."""
        company = self._get_company()
        rows = get_data(frappe._dict({"company": company, "month": "01", "year": 2024}))
        if not rows:
            self.skipTest("No CP39 data rows for 2024-01 — required key test skipped")
        for row in rows:
            for key in REQUIRED_FIELDNAMES:
                self.assertIn(key, row, f"Row missing required key: {key}")

    def test_month_year_format(self):
        """month_year must be MM/YYYY format."""
        import re

        company = self._get_company()
        rows = get_data(frappe._dict({"company": company, "month": "01", "year": 2024}))
        if not rows:
            self.skipTest("No data rows — month_year format test skipped")
        for row in rows:
            month_year = row.get("month_year", "")
            self.assertRegex(
                month_year,
                r"^\d{2}/\d{4}$",
                f"month_year '{month_year}' does not match MM/YYYY format",
            )

    def test_employer_e_number_key_present_in_rows(self):
        """employer_e_number key must exist in each row (even if empty string)."""
        company = self._get_company()
        rows = get_data(frappe._dict({"company": company, "month": "01", "year": 2024}))
        if not rows:
            self.skipTest("No data rows — employer_e_number test skipped")
        for row in rows:
            self.assertIn("employer_e_number", row)
            # Value must be a string (may be empty if field not set on Company)
            self.assertIsInstance(row["employer_e_number"], str)

    def test_amounts_are_numeric(self):
        """Currency amounts must be numeric (formattable to 2 decimal places)."""
        company = self._get_company()
        rows = get_data(frappe._dict({"company": company, "month": "01", "year": 2024}))
        if not rows:
            self.skipTest("No data rows — amount format test skipped")
        currency_fields = [
            "gross_remuneration",
            "epf_employee",
            "zakat_amount",
            "cp38_amount",
            "total_pcb",
        ]
        for row in rows:
            for field in currency_fields:
                val = row.get(field, 0)
                try:
                    f"{float(val):.2f}"
                except (TypeError, ValueError):
                    self.fail(f"Field '{field}' value '{val}' is not numeric")

    def test_get_csv_data_returns_string(self):
        """get_csv_data() must return a UTF-8 compatible string."""
        company = self._get_company()
        result = get_csv_data(
            frappe._dict({"company": company, "month": "01", "year": 2024})
        )
        self.assertIsInstance(result, str)
        # Must encode to UTF-8 without error
        encoded = result.encode("utf-8")
        self.assertIsInstance(encoded, bytes)

    def test_get_csv_data_has_header_row(self):
        """CSV output must start with the LHDN mandatory column header row."""
        company = self._get_company()
        result = get_csv_data(
            frappe._dict({"company": company, "month": "01", "year": 2024})
        )
        first_line = result.split("\n")[0] if result else ""
        # Header must contain all mandatory column names
        for header in [
            "Employer E-Number",
            "Month/Year",
            "Employee TIN",
            "Employee NRIC",
            "Employee Name",
            "PCB Category",
            "Gross Remuneration",
            "EPF Employee",
            "Zakat Amount",
            "CP38 Additional",
            "Total PCB",
        ]:
            self.assertIn(
                header, first_line, f"CSV header missing: {header}"
            )

    def test_get_csv_data_amounts_formatted_to_2dp(self):
        """CSV amount columns must be formatted to 2 decimal places."""
        import csv
        import io

        company = self._get_company()
        rows = get_data(frappe._dict({"company": company, "month": "01", "year": 2024}))
        if not rows:
            self.skipTest("No data rows — CSV 2dp format test skipped")

        csv_text = get_csv_data(
            frappe._dict({"company": company, "month": "01", "year": 2024})
        )
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)  # skip header
        # Amount columns are at positions 6-10 (0-indexed)
        amount_positions = [6, 7, 8, 9, 10]
        for data_row in reader:
            for pos in amount_positions:
                if pos < len(data_row):
                    val = data_row[pos]
                    # Must match ##.## format (possibly with more digits before decimal)
                    self.assertRegex(
                        val,
                        r"^\d+\.\d{2}$",
                        f"Amount '{val}' at CSV position {pos} is not formatted to 2 d.p.",
                    )
