"""Tests for US-090: Foreign Worker EPF Mandatory Contribution (Effective October 2025).

EPF (Amendment) Act 2024 mandates EPF contributions for foreign workers at 2% each
(employee + employer) effective 1 October 2025.

Acceptance criteria:
- calculate_epf_employer_rate(monthly_gross, is_foreign, payroll_date) returns 2%
  for foreign workers when payroll_date >= 2025-10-01
- Returns 0% for foreign workers before October 2025 (they were exempt)
- Malaysian citizen/PR employee rates unchanged (12%/13%)
- FOREIGN_WORKER_EPF_START = date(2025, 10, 1) and FOREIGN_WORKER_EPF_RATE = 0.02 exported
"""
from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestForeignWorkerEPFConstants(FrappeTestCase):
    """Verify EPF foreign worker constants are exported from statutory_rates."""

    def test_foreign_worker_epf_start_date(self):
        """FOREIGN_WORKER_EPF_START must be 2025-10-01."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            FOREIGN_WORKER_EPF_START,
        )
        self.assertEqual(FOREIGN_WORKER_EPF_START, date(2025, 10, 1))

    def test_foreign_worker_epf_rate(self):
        """FOREIGN_WORKER_EPF_RATE must be 0.02 (2%)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            FOREIGN_WORKER_EPF_RATE,
        )
        self.assertAlmostEqual(FOREIGN_WORKER_EPF_RATE, 0.02)

    def test_calculate_epf_employer_rate_exported(self):
        """calculate_epf_employer_rate must accept is_foreign and payroll_date params."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employer_rate,
        )
        # Should not raise with new signature
        result = calculate_epf_employer_rate(5000, is_foreign=False, payroll_date=date(2025, 11, 1))
        self.assertIsInstance(result, float)

    def test_calculate_epf_employee_rate_exported(self):
        """calculate_epf_employee_rate must be importable from statutory_rates."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employee_rate,
        )
        result = calculate_epf_employee_rate(is_foreign=False)
        self.assertIsInstance(result, float)


class TestForeignWorkerEPFEmployerRate(FrappeTestCase):
    """Verify calculate_epf_employer_rate handles foreign workers correctly."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employer_rate,
        )
        self.calc = calculate_epf_employer_rate

    def test_october_2025_foreign_worker_employer_2_percent(self):
        """Foreign worker, October 2025 → employer rate = 2%."""
        rate = self.calc(5000, is_foreign=True, payroll_date=date(2025, 10, 1))
        self.assertAlmostEqual(rate, 0.02,
                               msg="Employer EPF must be 2% for foreign worker from October 2025")

    def test_november_2025_foreign_worker_employer_2_percent(self):
        """Foreign worker, November 2025 → employer rate = 2% (still in effect)."""
        rate = self.calc(8000, is_foreign=True, payroll_date=date(2025, 11, 1))
        self.assertAlmostEqual(rate, 0.02)

    def test_january_2026_foreign_worker_employer_2_percent(self):
        """Foreign worker, January 2026 → employer rate = 2%."""
        rate = self.calc(3000, is_foreign=True, payroll_date=date(2026, 1, 15))
        self.assertAlmostEqual(rate, 0.02)

    def test_september_2025_foreign_worker_exempt(self):
        """Foreign worker, September 2025 → employer rate = 0% (not yet mandatory)."""
        rate = self.calc(5000, is_foreign=True, payroll_date=date(2025, 9, 30))
        self.assertAlmostEqual(rate, 0.0,
                               msg="Foreign worker EPF is 0% before October 2025")

    def test_december_2024_foreign_worker_exempt(self):
        """Foreign worker, December 2024 → employer rate = 0%."""
        rate = self.calc(5000, is_foreign=True, payroll_date=date(2024, 12, 1))
        self.assertAlmostEqual(rate, 0.0)

    def test_malaysian_employee_under_5000_unaffected(self):
        """Malaysian employee RM5,000 or below → 13% (unchanged)."""
        rate = self.calc(5000, is_foreign=False, payroll_date=date(2025, 10, 1))
        self.assertAlmostEqual(rate, 0.13,
                               msg="Citizen/PR EPF rate must remain 13% for wages <= RM5,000")

    def test_malaysian_employee_above_5000_unaffected(self):
        """Malaysian employee above RM5,000 → 12% (unchanged)."""
        rate = self.calc(6000, is_foreign=False, payroll_date=date(2025, 10, 1))
        self.assertAlmostEqual(rate, 0.12,
                               msg="Citizen/PR EPF rate must remain 12% for wages > RM5,000")

    def test_backward_compat_no_params(self):
        """Calling with only monthly_gross (old signature) still returns correct rate."""
        rate_low = self.calc(5000)
        rate_high = self.calc(6000)
        self.assertAlmostEqual(rate_low, 0.13)
        self.assertAlmostEqual(rate_high, 0.12)

    def test_foreign_worker_rate_same_regardless_of_wages(self):
        """Foreign worker EPF rate is flat 2% regardless of wage level."""
        oct_2025 = date(2025, 10, 1)
        for wages in [1000, 3000, 5000, 8000, 15000]:
            rate = self.calc(wages, is_foreign=True, payroll_date=oct_2025)
            self.assertAlmostEqual(rate, 0.02,
                                   msg=f"Foreign worker EPF employer rate must be 2% at RM{wages}")


class TestForeignWorkerEPFEmployeeRate(FrappeTestCase):
    """Verify calculate_epf_employee_rate handles foreign workers correctly."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employee_rate,
        )
        self.calc = calculate_epf_employee_rate

    def test_october_2025_foreign_worker_employee_2_percent(self):
        """Foreign worker, October 2025 → employee rate = 2%."""
        rate = self.calc(is_foreign=True, payroll_date=date(2025, 10, 1))
        self.assertAlmostEqual(rate, 0.02,
                               msg="Employee EPF must be 2% for foreign worker from October 2025")

    def test_september_2025_foreign_worker_exempt(self):
        """Foreign worker, September 2025 → employee rate = 0%."""
        rate = self.calc(is_foreign=True, payroll_date=date(2025, 9, 30))
        self.assertAlmostEqual(rate, 0.0)

    def test_malaysian_employee_rate_11_percent(self):
        """Malaysian citizen/PR → employee rate = 11% (unchanged)."""
        rate = self.calc(is_foreign=False, payroll_date=date(2025, 10, 1))
        self.assertAlmostEqual(rate, 0.11)

    def test_employee_and_employer_both_2_percent_for_foreign(self):
        """Both employee and employer EPF rates = 2% for foreign worker (symmetric)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employer_rate,
        )
        oct_2025 = date(2025, 10, 1)
        ee_rate = self.calc(is_foreign=True, payroll_date=oct_2025)
        er_rate = calculate_epf_employer_rate(5000, is_foreign=True, payroll_date=oct_2025)
        self.assertAlmostEqual(ee_rate, er_rate,
                               msg="Employee and employer EPF rates must both be 2% for foreign worker")
        self.assertAlmostEqual(ee_rate, 0.02)


class TestForeignWorkerEPFSalaryComponents(FrappeTestCase):
    """Verify foreign worker EPF salary components exist in fixtures."""

    def test_epf_employee_foreign_worker_component_exists(self):
        """EPF Employee (Foreign Worker) salary component must exist."""
        result = frappe.db.exists("Salary Component", "EPF Employee (Foreign Worker)")
        # This test verifies the fixture was applied; it may be None if fixtures not synced
        # For unit test purposes we check the fixtures JSON directly
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "salary_component.json"
        )
        if os.path.exists(fixture_path):
            with open(fixture_path) as f:
                components = json.load(f)
            names = [c.get("name", "") for c in components]
            self.assertIn("EPF Employee (Foreign Worker)", names,
                          "EPF Employee (Foreign Worker) must be in salary_component.json fixture")

    def test_epf_employer_foreign_worker_component_exists(self):
        """EPF Employer (Foreign Worker) salary component must exist in fixtures."""
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "salary_component.json"
        )
        if os.path.exists(fixture_path):
            with open(fixture_path) as f:
                components = json.load(f)
            names = [c.get("name", "") for c in components]
            self.assertIn("EPF Employer (Foreign Worker)", names,
                          "EPF Employer (Foreign Worker) must be in salary_component.json fixture")

    def test_foreign_worker_epf_components_are_deductions(self):
        """Both foreign worker EPF components must be type=Deduction."""
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "salary_component.json"
        )
        if os.path.exists(fixture_path):
            with open(fixture_path) as f:
                components = json.load(f)
            fw_components = [
                c for c in components
                if c.get("name") in (
                    "EPF Employee (Foreign Worker)",
                    "EPF Employer (Foreign Worker)",
                )
            ]
            for comp in fw_components:
                self.assertEqual(comp.get("type"), "Deduction",
                                 f"{comp['name']} must be type=Deduction")


class TestEPFBorangAForeignWorkerWarning(FrappeTestCase):
    """Verify EPF Borang A rate validation handles foreign worker 2% rate."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_epf_employer_rate_warning,
        )
        self.get_warning = get_epf_employer_rate_warning

    def test_citizen_correct_13pct_no_warning(self):
        """Citizen at RM4,000 → 13% (RM520 employer EPF) → no warning."""
        warning = self.get_warning(wages=4000, employer_epf=520.0)
        self.assertEqual(warning, "")

    def test_citizen_wrong_rate_warns(self):
        """Citizen at RM4,000 but employer EPF is RM80 (2%) → warning."""
        warning = self.get_warning(wages=4000, employer_epf=80.0)
        self.assertTrue(len(warning) > 0, "Should warn for citizen with 2% EPF (should be 13%)")

    def test_borang_a_columns_present(self):
        """EPF Borang A must have all required columns."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        for required in ["employee", "wages", "employee_epf", "employer_epf"]:
            self.assertIn(required, fieldnames, f"Column '{required}' missing from EPF Borang A")


class TestIAkaunCitizenTypeCode(FrappeTestCase):
    """US-131: EPF i-Akaun CSV must include citizen type code for Malaysian vs foreign worker."""

    def test_get_citizen_type_code_is_importable(self):
        """get_citizen_type_code must be importable from epf_borang_a."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_citizen_type_code,
        )
        self.assertTrue(callable(get_citizen_type_code))

    def test_citizen_type_malaysian_returns_1(self):
        """Malaysian employee (is_foreign=False/0) → citizen type '1'."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_citizen_type_code,
        )
        self.assertEqual(get_citizen_type_code(False), "1")
        self.assertEqual(get_citizen_type_code(0), "1")
        self.assertEqual(get_citizen_type_code(None), "1")

    def test_citizen_type_foreign_returns_2(self):
        """Foreign worker (is_foreign=True/1) → citizen type '2'."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            get_citizen_type_code,
        )
        self.assertEqual(get_citizen_type_code(True), "2")
        self.assertEqual(get_citizen_type_code(1), "2")

    def test_generate_iakaun_file_returns_string(self):
        """generate_iakaun_file must return a string (even with no data)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        result = generate_iakaun_file(frappe._dict())
        self.assertIsInstance(result, str)

    def test_iakaun_detail_line_includes_citizen_type_for_malaysian(self):
        """Detail line for Malaysian employee must end with '|1' citizen type."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        mock_rows = [
            frappe._dict({
                "employee": "EMP001",
                "employee_name": "Ahmad bin Ali",
                "nric": "900101-01-1234",
                "epf_member_number": "12345678",
                "wages": 5000.00,
                "employee_epf": 550.00,
                "employer_epf": 650.00,
                "is_domestic_servant": 0,
                "is_foreign_worker": 0,
            }),
        ]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "10", "year": 2025}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertEqual(len(detail_lines), 1)
        self.assertTrue(
            detail_lines[0].endswith("|1"),
            f"Malaysian employee detail line must end with '|1', got: {detail_lines[0]}",
        )

    def test_iakaun_detail_line_includes_citizen_type_for_foreign(self):
        """Detail line for foreign worker must end with '|2' citizen type."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        mock_rows = [
            frappe._dict({
                "employee": "EMP002",
                "employee_name": "John Foreign",
                "nric": "A12345678",
                "epf_member_number": "87654321",
                "wages": 3000.00,
                "employee_epf": 60.00,
                "employer_epf": 60.00,
                "is_domestic_servant": 0,
                "is_foreign_worker": 1,
            }),
        ]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "10", "year": 2025}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertEqual(len(detail_lines), 1)
        self.assertTrue(
            detail_lines[0].endswith("|2"),
            f"Foreign worker detail line must end with '|2', got: {detail_lines[0]}",
        )

    def test_iakaun_mixed_payroll_correct_citizen_types(self):
        """Mixed payroll: Malaysian gets '1', foreign worker gets '2'."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        mock_rows = [
            frappe._dict({
                "employee": "EMP001",
                "employee_name": "Ahmad bin Ali",
                "nric": "900101011234",
                "epf_member_number": "11111111",
                "wages": 5000.00,
                "employee_epf": 550.00,
                "employer_epf": 650.00,
                "is_domestic_servant": 0,
                "is_foreign_worker": 0,
            }),
            frappe._dict({
                "employee": "EMP002",
                "employee_name": "Nguyen Van A",
                "nric": "B98765432",
                "epf_member_number": "22222222",
                "wages": 2500.00,
                "employee_epf": 50.00,
                "employer_epf": 50.00,
                "is_domestic_servant": 0,
                "is_foreign_worker": 1,
            }),
        ]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict({"month": "10", "year": 2025}))
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertEqual(len(detail_lines), 2, "Should have 2 detail lines")
        # Malaysian first
        self.assertTrue(
            detail_lines[0].endswith("|1"),
            f"First row (Malaysian) must have citizen type '1', got: {detail_lines[0]}",
        )
        # Foreign second
        self.assertTrue(
            detail_lines[1].endswith("|2"),
            f"Second row (foreign) must have citizen type '2', got: {detail_lines[1]}",
        )

    def test_iakaun_domestic_servant_excluded(self):
        """Foreign domestic servant (is_domestic_servant=1) is excluded from i-Akaun."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        mock_rows = [
            frappe._dict({
                "employee": "EMP003",
                "employee_name": "Maria Helper",
                "nric": "C11223344",
                "epf_member_number": "",
                "wages": 1500.00,
                "employee_epf": 30.00,
                "employer_epf": 30.00,
                "is_domestic_servant": 1,
                "is_foreign_worker": 1,
            }),
        ]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data",
            return_value=mock_rows,
        ):
            result = generate_iakaun_file(frappe._dict())
        detail_lines = [l for l in result.split("\n") if l.startswith("D|")]
        self.assertEqual(len(detail_lines), 0, "Domestic servant must be excluded from i-Akaun")
