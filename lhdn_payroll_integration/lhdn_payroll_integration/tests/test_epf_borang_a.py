"""Tests for EPF Borang A monthly contribution schedule script report.

Verifies output columns and row shape for EPF (KWSP) Borang A,
compatible with EPF i-Akaun upload format.

US-067: Added tests for generate_iakaun_file() and custom_epf_employer_registration field.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
    execute,
    generate_iakaun_file,
    get_columns,
    get_data,
)

REQUIRED_FIELDNAMES = {
    "employee_name",
    "nric",
    "epf_member_number",
    "wages",
    "employee_epf",
    "employer_epf",
    "total_contribution",
}


class TestEPFBorangAColumns(FrappeTestCase):
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

    def test_get_columns_epf_member_number_present(self):
        """get_columns() must include epf_member_number column."""
        columns = get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        self.assertIn("epf_member_number", fieldnames)

    def test_get_columns_total_contribution_present(self):
        """get_columns() must include total_contribution column."""
        columns = get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        self.assertIn("total_contribution", fieldnames)


class TestEPFBorangAData(FrappeTestCase):
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
            self.skipTest("No submitted EPF Salary Slips in test DB — shape test skipped")
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

    def test_get_data_epf_amounts_positive(self):
        """All rows must have at least one of employee_epf or employer_epf > 0."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — EPF amount test skipped")
        for row in rows:
            employee_epf = row.get("employee_epf", 0) or 0
            employer_epf = row.get("employer_epf", 0) or 0
            self.assertGreater(
                employee_epf + employer_epf, 0,
                f"Row {row.get('salary_slip')} has zero EPF amounts"
            )

    def test_get_data_total_contribution_equals_sum(self):
        """total_contribution must equal employee_epf + employer_epf."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — total_contribution sum test skipped")
        for row in rows:
            expected = (row.get("employee_epf") or 0) + (row.get("employer_epf") or 0)
            actual = row.get("total_contribution") or 0
            self.assertAlmostEqual(
                actual, expected, places=2,
                msg=f"Row {row.get('salary_slip')}: total_contribution mismatch"
            )

    def test_get_data_month_filter(self):
        """Month filter must restrict results to the specified month."""
        filters = frappe._dict({"year": 2026, "month": "01"})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No January 2026 EPF slips — month filter test skipped")
        for row in rows:
            period = row.get("period", "")
            self.assertIn("2026-01", period, f"Row period {period!r} not in Jan 2026")

    def test_get_data_epf_member_number_field_exists(self):
        """epf_member_number key must exist in each row (may be empty string)."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — epf_member_number field test skipped")
        for row in rows:
            self.assertIn("epf_member_number", row)


class TestEPFBorangAExecute(FrappeTestCase):
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


class TestEPFIAkaunFile(FrappeTestCase):
    """Tests for generate_iakaun_file() — EPF i-Akaun electronic upload format.

    US-067: File structure correct for payroll; EPF registration number in header.
    """

    def _make_mock_rows(self, count=3):
        """Return a list of mock EPF row dicts for testing."""
        rows = []
        for i in range(1, count + 1):
            rows.append({
                "employee": f"HR-EMP-{i:05d}",
                "employee_name": f"Employee {i}",
                "nric": f"87010114{i:04d}",
                "epf_member_number": f"EPF{i:06d}",
                "wages": 5000.00 * i,
                "employee_epf": 550.00 * i,
                "employer_epf": 650.00 * i,
                "total_contribution": 1200.00 * i,
                "period": "2026-01",
                "salary_slip": f"Sal/00{i}",
                "epf_rate_warning": "",
            })
        return rows

    def test_generate_iakaun_file_returns_string(self):
        """generate_iakaun_file() must return a string."""
        content = generate_iakaun_file(frappe._dict())
        self.assertIsInstance(content, str)

    def test_generate_iakaun_file_has_header_line(self):
        """File must start with a header line beginning with 'H|'."""
        content = generate_iakaun_file(frappe._dict())
        lines = content.strip().split("\n")
        self.assertTrue(lines[0].startswith("H|"), f"Header line malformed: {lines[0]!r}")

    def test_generate_iakaun_file_has_trailer_line(self):
        """File must end with a trailer line beginning with 'T|'."""
        content = generate_iakaun_file(frappe._dict())
        lines = content.strip().split("\n")
        self.assertTrue(lines[-1].startswith("T|"), f"Trailer line malformed: {lines[-1]!r}")

    def test_generate_iakaun_file_header_contains_period(self):
        """Header line must contain the YYYYMM period."""
        filters = frappe._dict({"year": 2026, "month": "01"})
        content = generate_iakaun_file(filters)
        header = content.split("\n")[0]
        self.assertIn("202601", header, f"Period not found in header: {header!r}")

    def test_generate_iakaun_file_header_employee_count(self):
        """Header line must contain the total employee count."""
        filters = frappe._dict({"year": 2026})
        content = generate_iakaun_file(filters)
        lines = content.strip().split("\n")
        header = lines[0]
        parts = header.split("|")
        # H|EPF_REG|PERIOD|COUNT
        self.assertGreaterEqual(len(parts), 4, f"Header has too few fields: {header!r}")
        # Count must be an integer
        try:
            count = int(parts[3])
        except (ValueError, IndexError):
            self.fail(f"Header employee count not an integer: {header!r}")
        # Detail rows = total lines - header - trailer
        detail_count = len(lines) - 2
        self.assertEqual(count, detail_count, "Header count does not match detail row count")

    def test_generate_iakaun_file_detail_rows_pipe_delimited(self):
        """Detail lines must be pipe-delimited with at least 8 fields."""
        filters = frappe._dict({"year": 2026})
        content = generate_iakaun_file(filters)
        lines = content.strip().split("\n")
        detail_lines = [l for l in lines if l.startswith("D|")]
        if not detail_lines:
            self.skipTest("No EPF data — detail row format test skipped")
        for line in detail_lines:
            parts = line.split("|")
            self.assertGreaterEqual(
                len(parts), 8,
                f"Detail line has too few fields: {line!r}"
            )

    def test_generate_iakaun_file_nric_no_hyphens(self):
        """NRIC in detail rows must not contain hyphens."""
        filters = frappe._dict({"year": 2026})
        content = generate_iakaun_file(filters)
        lines = content.strip().split("\n")
        detail_lines = [l for l in lines if l.startswith("D|")]
        for line in detail_lines:
            parts = line.split("|")
            if len(parts) >= 3:
                nric = parts[2]
                self.assertNotIn("-", nric, f"NRIC contains hyphen in line: {line!r}")

    def test_generate_iakaun_file_epf_reg_in_header(self):
        """EPF employer registration number must appear in the header."""
        # Use a company that has EPF registration set, or verify field position
        content = generate_iakaun_file(frappe._dict())
        header = content.split("\n")[0]
        parts = header.split("|")
        # Second field (index 1) is EPF reg number (may be empty if not configured)
        # Must have at least 4 pipe-delimited fields: H|REG|PERIOD|COUNT
        self.assertGreaterEqual(len(parts), 4, f"Header missing EPF reg field: {header!r}")

    def test_generate_iakaun_file_employer_epf_registration_field_on_company(self):
        """custom_epf_employer_registration must be registered as Custom Field on Company."""
        exists = frappe.db.exists(
            "Custom Field",
            {"dt": "Company", "fieldname": "custom_epf_employer_registration"},
        )
        self.assertTrue(
            exists,
            "Custom Field 'custom_epf_employer_registration' not found on Company",
        )

    def test_generate_iakaun_file_employer_epf_registration_is_data_type(self):
        """custom_epf_employer_registration field type must be Data."""
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Company", "fieldname": "custom_epf_employer_registration"},
            "fieldtype",
        )
        self.assertEqual(field, "Data")
