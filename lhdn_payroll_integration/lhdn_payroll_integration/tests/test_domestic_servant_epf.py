"""Tests for US-130: Foreign Worker EPF Oct 2025 — Domestic Servant Category Exclusion Flag.

Acceptance criteria:
- custom_is_domestic_servant field on Employee (via fixture)
- EPF rate returns 0 for domestic servants (both employer and employee)
- EPF i-Akaun CSV excludes domestic servant rows
- Validation warning appears when EPF found on domestic servant salary slip
- Flag defaults to False (non-breaking)
"""
from datetime import date
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDomesticServantEPFConstants(FrappeTestCase):
    """Verify domestic servant EPF exemption constant exported from statutory_rates."""

    def test_domestic_servant_epf_exempt_constant(self):
        """DOMESTIC_SERVANT_EPF_EXEMPT must be True."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            DOMESTIC_SERVANT_EPF_EXEMPT,
        )
        self.assertTrue(DOMESTIC_SERVANT_EPF_EXEMPT)

    def test_calculate_epf_employer_rate_accepts_domestic_servant_param(self):
        """calculate_epf_employer_rate must accept is_domestic_servant kwarg."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employer_rate,
        )
        rate = calculate_epf_employer_rate(
            5000, is_foreign=True, payroll_date=date(2025, 11, 1), is_domestic_servant=False
        )
        self.assertIsInstance(rate, float)

    def test_calculate_epf_employee_rate_accepts_domestic_servant_param(self):
        """calculate_epf_employee_rate must accept is_domestic_servant kwarg."""
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employee_rate,
        )
        rate = calculate_epf_employee_rate(
            is_foreign=True, payroll_date=date(2025, 11, 1), is_domestic_servant=False
        )
        self.assertIsInstance(rate, float)


class TestDomesticServantEPFRate(FrappeTestCase):
    """Verify EPF rates are zero for foreign domestic servants."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.utils.statutory_rates import (
            calculate_epf_employer_rate,
            calculate_epf_employee_rate,
        )
        self.employer_rate = calculate_epf_employer_rate
        self.employee_rate = calculate_epf_employee_rate

    def test_domestic_servant_employer_epf_zero_after_oct_2025(self):
        """Foreign domestic servant: employer EPF = 0% even after Oct 2025."""
        rate = self.employer_rate(
            5000,
            is_foreign=True,
            payroll_date=date(2025, 10, 1),
            is_domestic_servant=True,
        )
        self.assertAlmostEqual(
            rate, 0.0,
            msg="Domestic servant employer EPF must be 0% (excluded from mandate)"
        )

    def test_domestic_servant_employee_epf_zero_after_oct_2025(self):
        """Foreign domestic servant: employee EPF = 0% even after Oct 2025."""
        rate = self.employee_rate(
            is_foreign=True,
            payroll_date=date(2025, 11, 1),
            is_domestic_servant=True,
        )
        self.assertAlmostEqual(rate, 0.0,
                               msg="Domestic servant employee EPF must be 0%")

    def test_domestic_servant_employer_epf_zero_jan_2026(self):
        """Foreign domestic servant: employer EPF = 0% throughout 2026."""
        rate = self.employer_rate(
            8000,
            is_foreign=True,
            payroll_date=date(2026, 1, 15),
            is_domestic_servant=True,
        )
        self.assertAlmostEqual(rate, 0.0)

    def test_non_domestic_servant_foreign_worker_still_gets_2pct(self):
        """Non-domestic foreign worker: EPF is still 2% after Oct 2025."""
        employer_rate = self.employer_rate(
            5000,
            is_foreign=True,
            payroll_date=date(2025, 10, 1),
            is_domestic_servant=False,
        )
        self.assertAlmostEqual(employer_rate, 0.02,
                               msg="Non-domestic foreign worker must still pay 2% EPF")

    def test_local_employee_domestic_servant_flag_ignored(self):
        """Local employee with domestic_servant=True is unaffected (13% EPF)."""
        rate = self.employer_rate(
            5000,
            is_foreign=False,
            payroll_date=date(2025, 11, 1),
            is_domestic_servant=True,
        )
        self.assertAlmostEqual(
            rate, 0.13,
            msg="Local employee EPF rate must remain 13% regardless of domestic_servant flag"
        )

    def test_domestic_servant_before_oct_2025_also_zero(self):
        """Domestic servant before Oct 2025 mandate: EPF is also 0%."""
        rate = self.employer_rate(
            4000,
            is_foreign=True,
            payroll_date=date(2025, 9, 30),
            is_domestic_servant=True,
        )
        self.assertAlmostEqual(rate, 0.0)


class TestDomesticServantCustomField(FrappeTestCase):
    """Verify custom_is_domestic_servant field exists in fixture."""

    def _load_fixture(self):
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "custom_field.json"
        )
        self.assertTrue(os.path.exists(fixture_path), "custom_field.json fixture not found")
        with open(fixture_path) as f:
            return json.load(f)

    def test_domestic_servant_field_in_fixture(self):
        """custom_is_domestic_servant must be defined in custom_field.json."""
        fields = self._load_fixture()
        fieldnames = [f.get("fieldname", "") for f in fields]
        self.assertIn(
            "custom_is_domestic_servant",
            fieldnames,
            "custom_is_domestic_servant must be in custom_field.json fixture",
        )

    def test_domestic_servant_field_is_check_type(self):
        """custom_is_domestic_servant must be a Check (boolean) field."""
        fields = self._load_fixture()
        ds_field = next(
            (f for f in fields if f.get("fieldname") == "custom_is_domestic_servant"), None
        )
        self.assertIsNotNone(ds_field, "custom_is_domestic_servant field not found in fixture")
        self.assertEqual(
            ds_field.get("fieldtype"), "Check",
            "custom_is_domestic_servant must be fieldtype=Check"
        )

    def test_domestic_servant_field_defaults_to_zero(self):
        """custom_is_domestic_servant must default to 0 (False) — non-breaking."""
        fields = self._load_fixture()
        ds_field = next(
            (f for f in fields if f.get("fieldname") == "custom_is_domestic_servant"), None
        )
        self.assertIsNotNone(ds_field, "custom_is_domestic_servant field not found")
        self.assertIn(
            str(ds_field.get("default", "0")), ("0", ""),
            "custom_is_domestic_servant must default to 0 (non-breaking for existing employees)"
        )

    def test_domestic_servant_field_on_employee_doctype(self):
        """custom_is_domestic_servant must be applied to Employee doctype."""
        fields = self._load_fixture()
        ds_field = next(
            (f for f in fields if f.get("fieldname") == "custom_is_domestic_servant"), None
        )
        self.assertIsNotNone(ds_field)
        self.assertEqual(
            ds_field.get("dt"), "Employee",
            "custom_is_domestic_servant must be on Employee doctype"
        )


class TestDomesticServantExclusionService(FrappeTestCase):
    """Verify is_domestic_servant_epf_excluded() logic."""

    def test_foreign_domestic_servant_is_excluded(self):
        """is_domestic_servant_epf_excluded returns True for foreign domestic servant."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            is_domestic_servant_epf_excluded,
        )
        with patch("frappe.db.get_value") as mock_get:
            mock_get.return_value = {
                "custom_is_foreign_worker": 1,
                "custom_is_domestic_servant": 1,
            }
            result = is_domestic_servant_epf_excluded("EMP-001")
        self.assertTrue(result)

    def test_foreign_non_domestic_not_excluded(self):
        """is_domestic_servant_epf_excluded returns False for foreign non-domestic worker."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            is_domestic_servant_epf_excluded,
        )
        with patch("frappe.db.get_value") as mock_get:
            mock_get.return_value = {
                "custom_is_foreign_worker": 1,
                "custom_is_domestic_servant": 0,
            }
            result = is_domestic_servant_epf_excluded("EMP-002")
        self.assertFalse(result)

    def test_local_employee_not_excluded(self):
        """is_domestic_servant_epf_excluded returns False for local employee."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            is_domestic_servant_epf_excluded,
        )
        with patch("frappe.db.get_value") as mock_get:
            mock_get.return_value = {
                "custom_is_foreign_worker": 0,
                "custom_is_domestic_servant": 0,
            }
            result = is_domestic_servant_epf_excluded("EMP-003")
        self.assertFalse(result)

    def test_nonexistent_employee_returns_false(self):
        """is_domestic_servant_epf_excluded returns False for nonexistent employee."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            is_domestic_servant_epf_excluded,
        )
        with patch("frappe.db.get_value") as mock_get:
            mock_get.return_value = None
            result = is_domestic_servant_epf_excluded("NONEXISTENT")
        self.assertFalse(result)


class TestDomesticServantEPFWarning(FrappeTestCase):
    """Verify warn_domestic_servant_epf() hook fires correctly."""

    def _make_deduction(self, comp_name, amount):
        line = MagicMock()
        line.salary_component = comp_name
        line.amount = amount
        return line

    def _make_slip(self, employee, deductions=None):
        slip = MagicMock()
        slip.employee = employee
        slip.employee_name = "Test Worker"
        slip.deductions = deductions or []
        slip.earnings = []
        return slip

    def test_no_warning_for_non_domestic_servant(self):
        """No msgprint for non-domestic-servant foreign worker with EPF."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            warn_domestic_servant_epf,
        )
        slip = self._make_slip(
            "EMP-010",
            deductions=[self._make_deduction("EPF Employee (Foreign Worker)", 100.0)],
        )
        with patch("frappe.db.get_value") as mock_get, \
             patch("frappe.msgprint") as mock_msg:
            mock_get.return_value = {
                "custom_is_foreign_worker": 1,
                "custom_is_domestic_servant": 0,
            }
            warn_domestic_servant_epf(slip)
            mock_msg.assert_not_called()

    def test_warning_fires_for_domestic_servant_with_epf(self):
        """msgprint is called for domestic servant with EPF components."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            warn_domestic_servant_epf,
        )
        slip = self._make_slip(
            "EMP-011",
            deductions=[self._make_deduction("EPF Employee (Foreign Worker)", 80.0)],
        )
        with patch("frappe.db.get_value") as mock_get, \
             patch("frappe.msgprint") as mock_msg:
            mock_get.return_value = {
                "custom_is_foreign_worker": 1,
                "custom_is_domestic_servant": 1,
            }
            warn_domestic_servant_epf(slip)
            mock_msg.assert_called_once()

    def test_no_warning_when_no_epf_on_domestic_servant(self):
        """No msgprint if domestic servant slip has no EPF components (correct)."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.domestic_servant_epf_service import (
            warn_domestic_servant_epf,
        )
        basic = MagicMock()
        basic.salary_component = "Basic Salary"
        basic.amount = 1800.0
        slip = self._make_slip("EMP-012", deductions=[basic])
        with patch("frappe.db.get_value") as mock_get, \
             patch("frappe.msgprint") as mock_msg:
            mock_get.return_value = {
                "custom_is_foreign_worker": 1,
                "custom_is_domestic_servant": 1,
            }
            warn_domestic_servant_epf(slip)
            mock_msg.assert_not_called()


class TestDomesticServantIAkaunExclusion(FrappeTestCase):
    """Verify i-Akaun generate function skips domestic servant rows."""

    def test_generate_iakaun_excludes_domestic_servants(self):
        """generate_iakaun_file must not include domestic servant employees."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        mock_rows = [
            {
                "salary_slip": "SS-001",
                "employee": "EMP-100",
                "employee_name": "Ahmad Foreign Worker",
                "nric": "A12345678",
                "epf_member_number": "1234567",
                "wages": 3000.0,
                "employee_epf": 60.0,
                "employer_epf": 60.0,
                "total_contribution": 120.0,
                "is_domestic_servant": 0,
            },
            {
                "salary_slip": "SS-002",
                "employee": "EMP-101",
                "employee_name": "Maria Domestic Maid",
                "nric": "B98765432",
                "epf_member_number": "7654321",
                "wages": 1800.0,
                "employee_epf": 36.0,
                "employer_epf": 36.0,
                "total_contribution": 72.0,
                "is_domestic_servant": 1,
            },
        ]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data"
        ) as mock_get_data, patch("frappe.db.get_value") as mock_company:
            mock_get_data.return_value = mock_rows
            mock_company.return_value = "C1234567"
            content = generate_iakaun_file({"company": "Test Co", "month": "11", "year": 2025})

        self.assertIn(
            "AHMAD FOREIGN WORKER", content.upper(),
            "Normal foreign worker must appear in i-Akaun file"
        )
        self.assertNotIn(
            "MARIA DOMESTIC MAID", content.upper(),
            "Domestic servant must NOT appear in i-Akaun file"
        )

    def test_iakaun_header_count_excludes_domestic_servants(self):
        """i-Akaun file header total_employees excludes domestic servants."""
        from lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a import (
            generate_iakaun_file,
        )
        mock_rows = [
            {
                "salary_slip": "SS-003",
                "employee": "EMP-200",
                "employee_name": "Regular Worker",
                "nric": "C11111111",
                "epf_member_number": "1111111",
                "wages": 4000.0,
                "employee_epf": 80.0,
                "employer_epf": 80.0,
                "total_contribution": 160.0,
                "is_domestic_servant": 0,
            },
            {
                "salary_slip": "SS-004",
                "employee": "EMP-201",
                "employee_name": "Domestic Cook",
                "nric": "D22222222",
                "epf_member_number": "2222222",
                "wages": 1500.0,
                "employee_epf": 30.0,
                "employer_epf": 30.0,
                "total_contribution": 60.0,
                "is_domestic_servant": 1,
            },
        ]
        with patch(
            "lhdn_payroll_integration.lhdn_payroll_integration.report.epf_borang_a.epf_borang_a.get_data"
        ) as mock_get_data, patch("frappe.db.get_value") as mock_company:
            mock_get_data.return_value = mock_rows
            mock_company.return_value = "C9999999"
            content = generate_iakaun_file({"company": "Test Co", "month": "11", "year": 2025})

        header = content.split("\n")[0]
        count = int(header.split("|")[-1])
        self.assertEqual(count, 1, "i-Akaun header must show count=1 (domestic servant excluded)")
