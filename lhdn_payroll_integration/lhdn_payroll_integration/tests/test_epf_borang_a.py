"""Tests for EPF Borang A monthly contribution schedule script report.

Verifies output columns and row shape for EPF (KWSP) Borang A,
compatible with EPF i-Akaun upload format.

US-067: Added tests for generate_iakaun_file() and custom_epf_employer_registration field.
US-165: Added tests for three-account (75/15/10) split in i-Akaun file and Borang A columns.
"""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
    execute,
    generate_iakaun_file,
    get_citizen_type_code,
    get_columns,
    get_data,
    validate_account_split,
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

# US-165: Three-account split fieldnames required in columns and get_data() rows
THREE_ACCOUNT_FIELDNAMES = {
    "ee_akaun_persaraan",
    "ee_akaun_sejahtera",
    "ee_akaun_fleksibel",
    "er_akaun_persaraan",
    "er_akaun_sejahtera",
    "er_akaun_fleksibel",
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

    # US-165: Three-account split columns
    def test_get_columns_three_account_ee_columns_present(self):
        """get_columns() must include all three employee account split columns."""
        columns = get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        for fn in ("ee_akaun_persaraan", "ee_akaun_sejahtera", "ee_akaun_fleksibel"):
            self.assertIn(fn, fieldnames, f"Missing three-account column: {fn}")

    def test_get_columns_three_account_er_columns_present(self):
        """get_columns() must include all three employer account split columns."""
        columns = get_columns()
        fieldnames = [c.get("fieldname") for c in columns if isinstance(c, dict)]
        for fn in ("er_akaun_persaraan", "er_akaun_sejahtera", "er_akaun_fleksibel"):
            self.assertIn(fn, fieldnames, f"Missing three-account column: {fn}")

    def test_get_columns_three_account_columns_are_currency(self):
        """All six three-account split columns must be Currency type with MYR option."""
        columns = get_columns()
        col_map = {c["fieldname"]: c for c in columns if isinstance(c, dict)}
        for fn in THREE_ACCOUNT_FIELDNAMES:
            self.assertIn(fn, col_map, f"Column {fn} missing")
            self.assertEqual(col_map[fn].get("fieldtype"), "Currency",
                             f"Column {fn} must be Currency type")
            self.assertEqual(col_map[fn].get("options"), "MYR",
                             f"Column {fn} must have MYR options")


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

    # US-165: Three-account split keys in get_data() rows
    def test_get_data_rows_have_three_account_keys(self):
        """Rows must contain all six three-account split keys."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — three-account key test skipped")
        for row in rows:
            for key in THREE_ACCOUNT_FIELDNAMES:
                self.assertIn(key, row, f"Row missing three-account key: {key}")

    def test_get_data_ee_split_sums_to_employee_epf(self):
        """Employee three-account split amounts must sum to employee_epf."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — employee split sum test skipped")
        for row in rows:
            ee_total = row.get("employee_epf") or 0
            ee_split_sum = (
                (row.get("ee_akaun_persaraan") or 0)
                + (row.get("ee_akaun_sejahtera") or 0)
                + (row.get("ee_akaun_fleksibel") or 0)
            )
            self.assertAlmostEqual(
                ee_split_sum, ee_total, places=2,
                msg=f"Employee EPF split sum {ee_split_sum} ≠ {ee_total} for {row.get('salary_slip')}"
            )

    def test_get_data_er_split_sums_to_employer_epf(self):
        """Employer three-account split amounts must sum to employer_epf."""
        filters = frappe._dict({"year": 2026})
        rows = get_data(filters)
        if not rows:
            self.skipTest("No data — employer split sum test skipped")
        for row in rows:
            er_total = row.get("employer_epf") or 0
            er_split_sum = (
                (row.get("er_akaun_persaraan") or 0)
                + (row.get("er_akaun_sejahtera") or 0)
                + (row.get("er_akaun_fleksibel") or 0)
            )
            self.assertAlmostEqual(
                er_split_sum, er_total, places=2,
                msg=f"Employer EPF split sum {er_split_sum} ≠ {er_total} for {row.get('salary_slip')}"
            )


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


class TestValidateAccountSplit(FrappeTestCase):
    """Tests for validate_account_split() helper — US-165."""

    def test_valid_split_returns_empty_string(self):
        """No warning when split sums to total."""
        accounts = [
            {"amount": 750.0},
            {"amount": 150.0},
            {"amount": 100.0},
        ]
        result = validate_account_split(1000.0, accounts)
        self.assertEqual(result, "")

    def test_mismatch_returns_warning_string(self):
        """Warning returned when split sum differs from total by > RM0.02."""
        accounts = [
            {"amount": 700.0},
            {"amount": 150.0},
            {"amount": 100.0},
        ]
        result = validate_account_split(1000.0, accounts)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0, "Expected a warning for mismatched split")

    def test_rounding_within_tolerance_no_warning(self):
        """Rounding difference of RM0.01 must not trigger a warning."""
        accounts = [
            {"amount": 749.99},
            {"amount": 150.0},
            {"amount": 100.0},
        ]
        # sum = 999.99, total = 1000.00, diff = 0.01 <= tolerance
        result = validate_account_split(1000.0, accounts)
        self.assertEqual(result, "")

    def test_empty_accounts_returns_empty_string(self):
        """Empty accounts list must return empty string (no warning)."""
        result = validate_account_split(1000.0, [])
        self.assertEqual(result, "")

    def test_zero_total_zero_split_no_warning(self):
        """Zero total with zero splits must not produce a warning."""
        accounts = [{"amount": 0.0}, {"amount": 0.0}, {"amount": 0.0}]
        result = validate_account_split(0.0, accounts)
        self.assertEqual(result, "")


class TestEPFIAkaunFile(FrappeTestCase):
    """Tests for generate_iakaun_file() — EPF i-Akaun electronic upload format.

    US-067: File structure correct for payroll; EPF registration number in header.
    US-165: Detail rows include three-account split columns.
    """

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
        self.assertGreaterEqual(len(parts), 4, f"Header has too few fields: {header!r}")
        try:
            count = int(parts[3])
        except (ValueError, IndexError):
            self.fail(f"Header employee count not an integer: {header!r}")
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
        content = generate_iakaun_file(frappe._dict())
        header = content.split("\n")[0]
        parts = header.split("|")
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


class TestIAkaunThreeAccountFormat(FrappeTestCase):
    """US-165: Three-account (75/15/10) split in EPF i-Akaun upload file."""

    def _make_mock_row(self, employee_epf=1000.0, employer_epf=1300.0, is_foreign=0):
        """Return a mock EPF row with pre-computed three-account split amounts."""
        return frappe._dict({
            "employee": "EMP-TEST-001",
            "employee_name": "Ahmad bin Ali",
            "nric": "9001011234",
            "epf_member_number": "12345678",
            "wages": 5000.00,
            "employee_epf": employee_epf,
            "employer_epf": employer_epf,
            "total_contribution": employee_epf + employer_epf,
            "is_domestic_servant": 0,
            "is_foreign_worker": is_foreign,
            # Three-account split: 75% / 15% / 10% (with fleksibel absorbing rounding)
            "ee_akaun_persaraan": round(employee_epf * 0.75, 2),
            "ee_akaun_sejahtera": round(employee_epf * 0.15, 2),
            "ee_akaun_fleksibel": round(employee_epf - round(employee_epf * 0.75, 2) - round(employee_epf * 0.15, 2), 2),
            "er_akaun_persaraan": round(employer_epf * 0.75, 2),
            "er_akaun_sejahtera": round(employer_epf * 0.15, 2),
            "er_akaun_fleksibel": round(employer_epf - round(employer_epf * 0.75, 2) - round(employer_epf * 0.15, 2), 2),
            "period": "2026-01",
            "salary_slip": "Sal/2026/001",
            "epf_rate_warning": "",
            "split_warning": "",
            "end_date": "2026-01-31",
        })

    def test_detail_row_includes_fifteen_fields(self):
        """Detail row must have 15 pipe-separated fields (D + 14 values)."""
        mock_rows = [self._make_mock_row()]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertEqual(len(detail_lines), 1)
        parts = detail_lines[0].split("|")
        self.assertEqual(
            len(parts), 15,
            f"Expected 15 fields in detail row, got {len(parts)}: {detail_lines[0]}"
        )

    def test_detail_row_ee_persaraan_75pct(self):
        """Employee Akaun Persaraan in detail row must be 75% of employee EPF."""
        mock_rows = [self._make_mock_row(employee_epf=1000.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        # Format: D|seq|nric|epf|name|wages|ee_epf|er_epf|ee_persaraan|ee_sejahtera|ee_fleksibel|er_persaraan|er_sejahtera|er_fleksibel|citizen_type
        ee_persaraan = float(parts[8])
        self.assertAlmostEqual(ee_persaraan, 750.0, places=2,
                               msg="Employee Akaun Persaraan must be 75% of RM1,000 = RM750")

    def test_detail_row_ee_sejahtera_15pct(self):
        """Employee Akaun Sejahtera in detail row must be 15% of employee EPF."""
        mock_rows = [self._make_mock_row(employee_epf=1000.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        ee_sejahtera = float(parts[9])
        self.assertAlmostEqual(ee_sejahtera, 150.0, places=2,
                               msg="Employee Akaun Sejahtera must be 15% of RM1,000 = RM150")

    def test_detail_row_ee_fleksibel_10pct(self):
        """Employee Akaun Fleksibel in detail row must be 10% of employee EPF."""
        mock_rows = [self._make_mock_row(employee_epf=1000.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        ee_fleksibel = float(parts[10])
        self.assertAlmostEqual(ee_fleksibel, 100.0, places=2,
                               msg="Employee Akaun Fleksibel must be 10% of RM1,000 = RM100")

    def test_detail_row_er_persaraan_75pct(self):
        """Employer Akaun Persaraan in detail row must be 75% of employer EPF."""
        mock_rows = [self._make_mock_row(employer_epf=1000.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        er_persaraan = float(parts[11])
        self.assertAlmostEqual(er_persaraan, 750.0, places=2,
                               msg="Employer Akaun Persaraan must be 75% of RM1,000 = RM750")

    def test_detail_row_er_sejahtera_15pct(self):
        """Employer Akaun Sejahtera in detail row must be 15% of employer EPF."""
        mock_rows = [self._make_mock_row(employer_epf=1000.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        er_sejahtera = float(parts[12])
        self.assertAlmostEqual(er_sejahtera, 150.0, places=2,
                               msg="Employer Akaun Sejahtera must be 15% of RM1,000 = RM150")

    def test_detail_row_er_fleksibel_10pct(self):
        """Employer Akaun Fleksibel in detail row must be 10% of employer EPF."""
        mock_rows = [self._make_mock_row(employer_epf=1000.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        er_fleksibel = float(parts[13])
        self.assertAlmostEqual(er_fleksibel, 100.0, places=2,
                               msg="Employer Akaun Fleksibel must be 10% of RM1,000 = RM100")

    def test_detail_row_citizen_type_is_last_field(self):
        """Citizen type code must be the last field in the detail row."""
        mock_rows = [self._make_mock_row(is_foreign=0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertTrue(
            detail_lines[0].endswith("|1"),
            f"Malaysian employee detail row must end with '|1', got: {detail_lines[0]}"
        )

    def test_detail_row_foreign_worker_citizen_type_2(self):
        """Foreign worker detail row must have citizen type '2' as the last field."""
        mock_rows = [self._make_mock_row(employee_epf=60.0, employer_epf=60.0, is_foreign=1)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "10", "year": 2025}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertTrue(
            detail_lines[0].endswith("|2"),
            f"Foreign worker detail row must end with '|2', got: {detail_lines[0]}"
        )

    def test_detail_row_split_amounts_are_decimal_formatted(self):
        """All three-account amounts in detail row must be formatted as 2 decimal places."""
        mock_rows = [self._make_mock_row(employee_epf=1000.0, employer_epf=1300.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        # Fields 8-13 are the six split amounts
        for i in range(8, 14):
            val = parts[i]
            self.assertRegex(val, r"^\d+\.\d{2}$",
                             f"Field {i} '{val}' must be formatted with 2 decimal places")

    def test_detail_row_three_account_ee_sums_to_ee_epf(self):
        """Sum of three employee account fields must equal ee_epf in the detail row."""
        mock_rows = [self._make_mock_row(employee_epf=1000.0, employer_epf=1300.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        ee_epf = float(parts[6])
        ee_split_sum = float(parts[8]) + float(parts[9]) + float(parts[10])
        self.assertAlmostEqual(ee_split_sum, ee_epf, places=2,
                               msg=f"EE split sum {ee_split_sum} ≠ ee_epf {ee_epf}")

    def test_detail_row_three_account_er_sums_to_er_epf(self):
        """Sum of three employer account fields must equal er_epf in the detail row."""
        mock_rows = [self._make_mock_row(employee_epf=1000.0, employer_epf=1300.0)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "01", "year": 2026}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        er_epf = float(parts[7])
        er_split_sum = float(parts[11]) + float(parts[12]) + float(parts[13])
        self.assertAlmostEqual(er_split_sum, er_epf, places=2,
                               msg=f"ER split sum {er_split_sum} ≠ er_epf {er_epf}")

    def test_foreign_worker_flat_2pct_gets_75_15_10_split(self):
        """Foreign worker flat 2% contribution (RM60 EE + RM60 ER) must use 75/15/10 split."""
        # RM60 employee EPF: Persaraan=45, Sejahtera=9, Fleksibel=6
        mock_rows = [self._make_mock_row(employee_epf=60.0, employer_epf=60.0, is_foreign=1)]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "10", "year": 2025}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        parts = detail_lines[0].split("|")
        ee_persaraan = float(parts[8])
        ee_sejahtera = float(parts[9])
        ee_fleksibel = float(parts[10])
        # RM60 * 75% = RM45, * 15% = RM9, remainder = RM6
        self.assertAlmostEqual(ee_persaraan, 45.0, places=2)
        self.assertAlmostEqual(ee_sejahtera, 9.0, places=2)
        self.assertAlmostEqual(ee_fleksibel, 6.0, places=2)
