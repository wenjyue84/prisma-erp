"""Tests for US-034 + US-072: HRDF levy validation and basic reporting."""
import json
import os
from unittest.mock import patch, MagicMock

from frappe.tests.utils import FrappeTestCase


class TestHrdfCustomField(FrappeTestCase):
    """Verify custom_hrdf_levy_rate field exists in fixture."""

    def test_custom_hrdf_levy_rate_in_fixture(self):
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures",
            "custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)

        hrdf_fields = [
            fld for fld in fields
            if fld.get("fieldname") == "custom_hrdf_levy_rate"
        ]
        self.assertEqual(len(hrdf_fields), 1, "custom_hrdf_levy_rate must appear once")

        field = hrdf_fields[0]
        self.assertEqual(field["dt"], "Company")
        self.assertEqual(field["fieldtype"], "Select")
        self.assertIn("0.5%", field["options"])
        self.assertIn("1.0%", field["options"])

    def test_custom_hrdf_mandatory_sector_in_fixture(self):
        """US-072: custom_hrdf_mandatory_sector Check field must exist on Company."""
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures",
            "custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)

        mandatory_sector_fields = [
            fld for fld in fields
            if fld.get("fieldname") == "custom_hrdf_mandatory_sector"
        ]
        self.assertEqual(
            len(mandatory_sector_fields), 1,
            "custom_hrdf_mandatory_sector must appear once in custom_field.json"
        )
        field = mandatory_sector_fields[0]
        self.assertEqual(field["dt"], "Company")
        self.assertEqual(field["fieldtype"], "Check")

    def test_hrdf_levy_rate_options_descriptive(self):
        """US-072: Options must contain descriptive labels for voluntary/mandatory."""
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fixtures",
            "custom_field.json",
        )
        with open(fixture_path) as f:
            fields = json.load(f)

        hrdf_field = next(
            (f for f in fields if f.get("fieldname") == "custom_hrdf_levy_rate"),
            None
        )
        self.assertIsNotNone(hrdf_field)
        options = hrdf_field.get("options", "")
        # Must have both voluntary (5-9) and mandatory (10+) labels
        self.assertIn("Voluntary", options, "Options must indicate voluntary rate for 5-9 employees")
        self.assertIn("Mandatory", options, "Options must indicate mandatory rate for 10+ employees")


class TestHrdfReportRateMap(FrappeTestCase):
    """Verify RATE_MAP constants and _get_levy_rate helper."""

    def test_rate_map_half_percent(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            RATE_MAP,
        )
        self.assertAlmostEqual(RATE_MAP["0.5%"], 0.005)

    def test_rate_map_one_percent(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            RATE_MAP,
        )
        self.assertAlmostEqual(RATE_MAP["1.0%"], 0.01)

    def test_rate_map_new_voluntary_option(self):
        """US-072: RATE_MAP must handle new descriptive option string for voluntary."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            RATE_MAP,
        )
        new_key = "0.5% (Voluntary - 5-9 employees)"
        self.assertIn(new_key, RATE_MAP)
        self.assertAlmostEqual(RATE_MAP[new_key], 0.005)

    def test_rate_map_new_mandatory_option(self):
        """US-072: RATE_MAP must handle new descriptive option string for mandatory."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            RATE_MAP,
        )
        new_key = "1.0% (Mandatory - 10+ employees)"
        self.assertIn(new_key, RATE_MAP)
        self.assertAlmostEqual(RATE_MAP[new_key], 0.01)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_get_levy_rate_half_percent(self, mock_frappe):
        mock_frappe.db.get_value.return_value = "0.5%"
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            _get_levy_rate,
        )
        rate = _get_levy_rate("Test Co")
        self.assertAlmostEqual(rate, 0.005)
        mock_frappe.db.get_value.assert_called_once_with(
            "Company", "Test Co", "custom_hrdf_levy_rate"
        )

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_get_levy_rate_one_percent(self, mock_frappe):
        mock_frappe.db.get_value.return_value = "1.0%"
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            _get_levy_rate,
        )
        rate = _get_levy_rate("Test Co")
        self.assertAlmostEqual(rate, 0.01)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_get_levy_rate_not_set(self, mock_frappe):
        mock_frappe.db.get_value.return_value = None
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            _get_levy_rate,
        )
        rate = _get_levy_rate("Test Co")
        self.assertEqual(rate, 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_get_levy_rate_new_voluntary_string(self, mock_frappe):
        """US-072: _get_levy_rate resolves new descriptive option string."""
        mock_frappe.db.get_value.return_value = "0.5% (Voluntary - 5-9 employees)"
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            _get_levy_rate,
        )
        rate = _get_levy_rate("Test Co")
        self.assertAlmostEqual(rate, 0.005)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_get_levy_rate_new_mandatory_string(self, mock_frappe):
        """US-072: _get_levy_rate resolves new descriptive option string."""
        mock_frappe.db.get_value.return_value = "1.0% (Mandatory - 10+ employees)"
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            _get_levy_rate,
        )
        rate = _get_levy_rate("Test Co")
        self.assertAlmostEqual(rate, 0.01)


class TestHrdfRateMismatchWarning(FrappeTestCase):
    """US-072: Verify get_rate_mismatch_warning correctly flags rate mismatches."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_rate_mismatch_warning,
        )
        self.get_warning = get_rate_mismatch_warning

    def test_10_employee_mandatory_sector_requires_one_percent(self):
        """10-employee company in mandatory sector must use 1.0% — warn if 0.5%."""
        warning = self.get_warning(
            rate_str="0.5% (Voluntary - 5-9 employees)",
            is_mandatory_sector=True,
            employee_count=10,
        )
        self.assertTrue(len(warning) > 0, "Should warn for 0.5% rate with 10+ mandatory sector employees")
        self.assertIn("1.0%", warning)

    def test_10_employee_mandatory_sector_one_percent_no_warning(self):
        """10-employee mandatory sector company at 1.0% — no warning."""
        warning = self.get_warning(
            rate_str="1.0% (Mandatory - 10+ employees)",
            is_mandatory_sector=True,
            employee_count=10,
        )
        self.assertEqual(warning, "", "No warning expected for correct 1.0% rate")

    def test_50_employee_mandatory_sector_requires_one_percent(self):
        """50-employee company in mandatory sector must use 1.0%."""
        warning = self.get_warning(
            rate_str="0.5%",
            is_mandatory_sector=True,
            employee_count=50,
        )
        self.assertTrue(len(warning) > 0, "Should warn for 0.5% rate with 50+ mandatory sector employees")

    def test_7_employee_company_allows_half_percent(self):
        """7-employee company may use 0.5% voluntary — no error warning."""
        warning = self.get_warning(
            rate_str="0.5% (Voluntary - 5-9 employees)",
            is_mandatory_sector=True,
            employee_count=7,
        )
        # No mismatch error (7 < 10 threshold)
        self.assertNotIn("requires 1.0%", warning)

    def test_not_mandatory_sector_no_warning(self):
        """Non-mandatory sector company using 0.5% — no warning regardless of headcount."""
        warning = self.get_warning(
            rate_str="0.5%",
            is_mandatory_sector=False,
            employee_count=20,
        )
        self.assertNotIn("requires 1.0%", warning)

    def test_no_rate_configured(self):
        """No rate configured — return configuration warning."""
        warning = self.get_warning(
            rate_str="",
            is_mandatory_sector=True,
            employee_count=15,
        )
        self.assertTrue(len(warning) > 0, "Should warn when no rate is configured")

    def test_legacy_rate_string_works(self):
        """Legacy '1.0%' option string still works correctly."""
        warning = self.get_warning(
            rate_str="1.0%",
            is_mandatory_sector=True,
            employee_count=10,
        )
        self.assertEqual(warning, "", "No warning for correct 1.0% rate (legacy string)")


class TestHrdfLevyCalculation(FrappeTestCase):
    """Verify levy calculation at 0.5% and 1.0% rates against Company fixture."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_levy_at_half_percent(self, mock_frappe):
        """Employee with RM5000 wages at 0.5% = RM25.00 levy."""
        mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
            "0.5%" if len(args) >= 3 and args[2] == "custom_hrdf_levy_rate"
            else ({"custom_hrdf_mandatory_sector": 0} if kwargs.get("as_dict") else None)
        )
        mock_frappe.db.sql.return_value = [
            {
                "salary_slip": "SS-001",
                "employee": "EMP-001",
                "employee_name": "Ali bin Ahmad",
                "wages": 5000.0,
            }
        ]
        mock_frappe._dict = dict

        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_data,
        )

        filters = {"company": "Test Co", "month": "01", "year": 2026}
        rows = get_data(filters)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["hrdf_levy"], 25.0, places=2)
        self.assertEqual(rows[0]["hrdf_rate"], "0.5%")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_levy_at_one_percent(self, mock_frappe):
        """Employee with RM5000 wages at 1.0% = RM50.00 levy."""
        mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
            "1.0%" if len(args) >= 3 and args[2] == "custom_hrdf_levy_rate"
            else ({"custom_hrdf_mandatory_sector": 1} if kwargs.get("as_dict") else None)
        )
        mock_frappe.db.sql.return_value = [
            {
                "salary_slip": "SS-002",
                "employee": "EMP-002",
                "employee_name": "Siti binti Zainab",
                "wages": 5000.0,
            }
        ]
        mock_frappe._dict = dict

        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_data,
        )

        filters = {"company": "Test Co", "month": "02", "year": 2026}
        rows = get_data(filters)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["hrdf_levy"], 50.0, places=2)
        self.assertEqual(rows[0]["hrdf_rate"], "1.0%")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_levy_multiple_employees(self, mock_frappe):
        """Multiple employees: verify each gets correct levy."""
        mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
            "1.0%" if len(args) >= 3 and args[2] == "custom_hrdf_levy_rate"
            else ({"custom_hrdf_mandatory_sector": 1} if kwargs.get("as_dict") else None)
        )
        mock_frappe.db.sql.return_value = [
            {"salary_slip": "SS-003", "employee": "EMP-003",
             "employee_name": "Ahmad", "wages": 3000.0},
            {"salary_slip": "SS-004", "employee": "EMP-004",
             "employee_name": "Bala", "wages": 7000.0},
        ]
        mock_frappe._dict = dict

        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_data,
        )

        rows = get_data({"company": "Test Co", "month": "03", "year": 2026})

        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["hrdf_levy"], 30.0, places=2)
        self.assertAlmostEqual(rows[1]["hrdf_levy"], 70.0, places=2)

    def test_get_data_no_company_returns_empty(self):
        """get_data with no company filter returns empty list."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_data,
        )
        rows = get_data({})
        self.assertEqual(rows, [])


class TestHrdfReportColumns(FrappeTestCase):
    """Verify report column definitions."""

    def test_columns_include_hrdf_levy(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("hrdf_levy", fieldnames)
        self.assertIn("hrdf_rate", fieldnames)
        self.assertIn("employee", fieldnames)
        self.assertIn("wages", fieldnames)

    def test_columns_include_rate_warning(self):
        """US-072: Report must include rate_warning column."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            get_columns,
        )
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("rate_warning", fieldnames)

    def test_execute_returns_columns_and_data(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            execute,
        )
        cols, data = execute({})
        self.assertIsInstance(cols, list)
        self.assertIsInstance(data, list)
        self.assertTrue(len(cols) > 0)
