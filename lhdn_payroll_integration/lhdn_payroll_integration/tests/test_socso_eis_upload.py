"""Tests for US-068: SOCSO and EIS e-Caruman Upload File Generator.

Acceptance criteria:
- Combined file: employer SOCSO number, employee NRIC, SOCSO number, wages,
  SOCSO employee, SOCSO employer, EIS employee, EIS employer
- SOCSO uses bracketed table lookup (US-074)
- EIS capped at RM6,000 wage ceiling (US-075)
- Tests: file structure correct; ceiling enforcement visible in export
"""
import io
from datetime import date
from unittest.mock import patch, MagicMock

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service import (
    ECARUMAN_DELIMITER,
    ECARUMAN_HEADERS,
    generate_ecaruman_file,
    get_ecaruman_data,
)


class TestEcarumanConstants(FrappeTestCase):
    """Verify module-level constants for PERKESO ASSIST format."""

    def test_delimiter_is_pipe(self):
        """PERKESO ASSIST e-Caruman uses pipe delimiter."""
        self.assertEqual(ECARUMAN_DELIMITER, "|")

    def test_headers_include_required_columns(self):
        """Required columns must be present in the header list."""
        required = {
            "Employer SOCSO No",
            "Employee NRIC",
            "SOCSO No",
            "Monthly Wages",
            "Employee SOCSO",
            "Employer SOCSO",
            "Employee EIS",
            "Employer EIS",
        }
        header_set = set(ECARUMAN_HEADERS)
        for col in required:
            self.assertIn(col, header_set, f"Missing header column: {col}")

    def test_headers_has_eight_columns(self):
        """Combined SOCSO+EIS file must have exactly 8 header columns."""
        self.assertEqual(len(ECARUMAN_HEADERS), 8)


class TestGenerateEcarumanFileStructure(FrappeTestCase):
    """Verify the file structure output by generate_ecaruman_file()."""

    def test_empty_filters_returns_header_only(self):
        """With no data, output contains only the header line."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = []
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(frappe._dict({"month": "01", "year": 1900}))

        lines = [ln for ln in content.splitlines() if ln]
        self.assertEqual(len(lines), 1, "Empty data should produce header line only")
        header = lines[0]
        self.assertIn("|", header)

    def test_header_line_contains_all_columns(self):
        """Header line must have all 8 required column labels."""
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = []
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(None)

        header_line = content.splitlines()[0]
        header_cols = header_line.split("|")
        self.assertEqual(len(header_cols), 8)
        self.assertIn("Employee SOCSO", header_line)
        self.assertIn("Employer SOCSO", header_line)
        self.assertIn("Employee EIS", header_line)
        self.assertIn("Employer EIS", header_line)

    def test_data_row_has_eight_pipe_separated_fields(self):
        """Each data row must have exactly 8 pipe-separated fields."""
        mock_row = {
            "salary_slip": "SS-0001",
            "company": "Test Co",
            "employee": "HR-EMP-001",
            "employee_name": "Ahmad Ali",
            "nric": "901010101234",
            "socso_member_number": "12345678",
            "wages": 3000.00,
            "date_of_birth": date(1990, 1, 1),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = "SB1234567"
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(None)

        lines = [ln for ln in content.splitlines() if ln]
        self.assertEqual(len(lines), 2, "Should have header + 1 data row")
        data_fields = lines[1].split("|")
        self.assertEqual(len(data_fields), 8)

    def test_amounts_formatted_to_two_decimal_places(self):
        """Monetary amounts in the file must be formatted to 2 d.p."""
        mock_row = {
            "salary_slip": "SS-0002",
            "company": "Test Co",
            "employee": "HR-EMP-002",
            "employee_name": "Siti Binti",
            "nric": "850505056789",
            "socso_member_number": "87654321",
            "wages": 2500.00,
            "date_of_birth": date(1985, 5, 5),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = "SB9876543"
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(None)

        lines = [ln for ln in content.splitlines() if ln]
        data_line = lines[1]
        fields = data_line.split("|")
        # fields[3] is wages, [4..7] are amounts
        for i in range(3, 8):
            val = fields[i]
            self.assertRegex(
                val, r"^\d+\.\d{2}$",
                f"Field {i} '{val}' should be formatted to 2 d.p."
            )

    def test_employer_socso_number_in_first_field(self):
        """First field of each data row must be the employer SOCSO number."""
        mock_row = {
            "salary_slip": "SS-0003",
            "company": "Test Co Sdn Bhd",
            "employee": "HR-EMP-003",
            "employee_name": "Tan Ah Kow",
            "nric": "770707077890",
            "socso_member_number": "11223344",
            "wages": 4000.00,
            "date_of_birth": date(1977, 7, 7),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = "SB5551234"
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(None)

        data_line = content.splitlines()[1]
        first_field = data_line.split("|")[0]
        self.assertEqual(first_field, "SB5551234")


class TestSocsoContributionInUploadFile(FrappeTestCase):
    """Verify SOCSO contributions use the bracketed table (US-074)."""

    def test_wages_3000_socso_amounts_from_bracket_table(self):
        """Wages RM3,000 → SOCSO from First Schedule bracket, not flat rate."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_socso_contribution,
        )
        expected = calculate_socso_contribution(3000)

        mock_row = {
            "salary_slip": "SS-0010",
            "company": "Test Co",
            "employee": "HR-EMP-010",
            "employee_name": "Test Employee",
            "nric": "900101015555",
            "socso_member_number": "55556666",
            "wages": 3000.00,
            "date_of_birth": date(1990, 1, 1),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = ""
            mock_frappe._dict = frappe._dict
            rows = get_ecaruman_data(None)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["socso_employee"], expected["employee"], places=2)
        self.assertAlmostEqual(row["socso_employer"], expected["employer"], places=2)

    def test_wages_above_6000_capped_at_ceiling(self):
        """Wages RM8,000 → SOCSO uses RM6,000 ceiling bracket amounts."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_socso_contribution,
        )
        expected_at_ceiling = calculate_socso_contribution(6000)
        expected_uncapped = calculate_socso_contribution(8000)  # would also give ceiling if capped

        mock_row = {
            "salary_slip": "SS-0011",
            "company": "Test Co",
            "employee": "HR-EMP-011",
            "employee_name": "High Earner",
            "nric": "800101015555",
            "socso_member_number": "99998888",
            "wages": 8000.00,
            "date_of_birth": date(1980, 1, 1),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = ""
            mock_frappe._dict = frappe._dict
            rows = get_ecaruman_data(None)

        row = rows[0]
        # SOCSO ceiling: RM6,000. Amounts should match RM6,000 bracket.
        self.assertAlmostEqual(row["socso_employee"], expected_at_ceiling["employee"], places=2)
        self.assertAlmostEqual(row["socso_employer"], expected_at_ceiling["employer"], places=2)

    def test_wages_above_6000_ceiling_visible_in_file(self):
        """In generated file, wages > RM6,000 shows capped SOCSO amounts."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_socso_contribution,
        )
        ceiling_socso = calculate_socso_contribution(6000)

        mock_row = {
            "salary_slip": "SS-0012",
            "company": "Test Co",
            "employee": "HR-EMP-012",
            "employee_name": "Senior Staff",
            "nric": "750101015555",
            "socso_member_number": "77778888",
            "wages": 10000.00,
            "date_of_birth": date(1975, 1, 1),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = "SB1000001"
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(None)

        data_line = content.splitlines()[1]
        fields = data_line.split("|")
        # fields[3]=wages, [4]=emp_socso, [5]=emr_socso
        emp_socso_in_file = float(fields[4])
        emr_socso_in_file = float(fields[5])
        self.assertAlmostEqual(emp_socso_in_file, ceiling_socso["employee"], places=2)
        self.assertAlmostEqual(emr_socso_in_file, ceiling_socso["employer"], places=2)


class TestEisContributionInUploadFile(FrappeTestCase):
    """Verify EIS contributions respect RM6,000 ceiling and exemptions (US-075)."""

    def test_wages_7000_eis_capped_at_6000(self):
        """Wages RM7,000 → EIS computed on RM6,000 ceiling (= RM12.00 each)."""
        mock_row = {
            "salary_slip": "SS-0020",
            "company": "Test Co",
            "employee": "HR-EMP-020",
            "employee_name": "Cap Test",
            "nric": "850505051234",
            "socso_member_number": "12121212",
            "wages": 7000.00,
            "date_of_birth": date(1985, 5, 5),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = ""
            mock_frappe._dict = frappe._dict
            rows = get_ecaruman_data(None)

        row = rows[0]
        # EIS ceiling RM6,000 × 0.2% = 12.00
        self.assertAlmostEqual(row["eis_employee"], 12.00, places=2)
        self.assertAlmostEqual(row["eis_employer"], 12.00, places=2)

    def test_eis_ceiling_visible_in_generated_file(self):
        """File for high-earner shows EIS capped at ceiling (RM12.00)."""
        mock_row = {
            "salary_slip": "SS-0021",
            "company": "Test Co",
            "employee": "HR-EMP-021",
            "employee_name": "High Earner EIS",
            "nric": "880808081234",
            "socso_member_number": "13131313",
            "wages": 9000.00,
            "date_of_birth": date(1988, 8, 8),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = "SB2000001"
            mock_frappe._dict = frappe._dict
            content = generate_ecaruman_file(None)

        data_line = content.splitlines()[1]
        fields = data_line.split("|")
        # fields[6]=eis_employee, fields[7]=eis_employer
        eis_emp_in_file = float(fields[6])
        eis_emr_in_file = float(fields[7])
        self.assertAlmostEqual(eis_emp_in_file, 12.00, places=2)
        self.assertAlmostEqual(eis_emr_in_file, 12.00, places=2)

    def test_foreign_worker_eis_is_zero(self):
        """Foreign worker → EIS employee and employer = 0.00 in file."""
        mock_row = {
            "salary_slip": "SS-0022",
            "company": "Test Co",
            "employee": "HR-EMP-022",
            "employee_name": "Foreign Worker",
            "nric": "A12345678",
            "socso_member_number": "14141414",
            "wages": 3000.00,
            "date_of_birth": date(1990, 6, 15),
            "is_foreign": 1,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = "SB3000001"
            mock_frappe._dict = frappe._dict
            rows = get_ecaruman_data(None)

        row = rows[0]
        self.assertEqual(row["eis_employee"], 0.0)
        self.assertEqual(row["eis_employer"], 0.0)

    def test_age_60_exempt_from_eis(self):
        """Employee aged >= 60 → EIS = 0.00."""
        mock_row = {
            "salary_slip": "SS-0023",
            "company": "Test Co",
            "employee": "HR-EMP-023",
            "employee_name": "Senior Employee",
            "nric": "640101011234",
            "socso_member_number": "15151515",
            "wages": 4000.00,
            "date_of_birth": date(1964, 1, 1),
            "is_foreign": 0,
            "payroll_date": date(2025, 1, 31),
        }

        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.services.socso_eis_upload_service.frappe"
        ) as mock_frappe:
            mock_frappe.db.sql.return_value = [mock_row]
            mock_frappe.db.get_value.return_value = ""
            mock_frappe._dict = frappe._dict
            rows = get_ecaruman_data(None)

        row = rows[0]
        self.assertEqual(row["eis_employee"], 0.0)
        self.assertEqual(row["eis_employer"], 0.0)


class TestEcarumanFiltersIntegration(FrappeTestCase):
    """Verify get_ecaruman_data() handles real Frappe DB (empty data)."""

    def test_returns_list(self):
        """get_ecaruman_data() always returns a list."""
        result = get_ecaruman_data(None)
        self.assertIsInstance(result, list)

    def test_empty_for_distant_past(self):
        """No salary slips in 1900 → empty list."""
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 1900})
        result = get_ecaruman_data(filters)
        self.assertEqual(result, [])

    def test_generate_file_returns_string(self):
        """generate_ecaruman_file() always returns a string."""
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 1900})
        content = generate_ecaruman_file(filters)
        self.assertIsInstance(content, str)

    def test_generate_file_newline_terminated(self):
        """Each line in the file (including header) ends with newline."""
        filters = frappe._dict({"company": "_Test Company", "month": "01", "year": 1900})
        content = generate_ecaruman_file(filters)
        self.assertTrue(content.endswith("\n"), "File content should end with newline")
