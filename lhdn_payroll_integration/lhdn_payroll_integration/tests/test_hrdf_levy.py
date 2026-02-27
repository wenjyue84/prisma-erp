"""Tests for US-034: HRDF levy validation and basic reporting."""
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


class TestHrdfLevyCalculation(FrappeTestCase):
    """Verify levy calculation at 0.5% and 1.0% rates against Company fixture."""

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy.frappe")
    def test_levy_at_half_percent(self, mock_frappe):
        """Employee with RM5000 wages at 0.5% = RM25.00 levy."""
        mock_frappe.db.get_value.return_value = "0.5%"
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
        mock_frappe.db.get_value.return_value = "1.0%"
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
        mock_frappe.db.get_value.return_value = "1.0%"
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

    def test_execute_returns_columns_and_data(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.hrdf_monthly_levy.hrdf_monthly_levy import (
            execute,
        )
        cols, data = execute({})
        self.assertIsInstance(cols, list)
        self.assertIsInstance(data, list)
        self.assertTrue(len(cols) > 0)
