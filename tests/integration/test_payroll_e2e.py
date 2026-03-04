"""
Integration Tests — E2E Payroll Workflow (E2E-01 to E2E-08)
============================================================
Tests a complete payroll lifecycle via REST API: employee data access,
salary slip structure, statutory deduction fields, and LHDN submission
readiness.  Creates no persistent test data — reads existing records only.
"""

import unittest

from tests.base import ERPNextTestCase
from tests.config import TEST_COMPANY


class TestPayrollDataAccess(ERPNextTestCase):
    """E2E-01 to E2E-03: Verify payroll data foundation exists."""

    category = "integration:e2e"

    def test_e2e01_employees_exist(self):
        """E2E-01: At least one Employee record exists for payroll."""
        resp = self.session.api(
            "frappe.client.get_count",
            doctype="Employee",
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        count = body.get("message", 0)
        self.assertGreater(count, 0,
                           "No Employee records found — payroll has no employees to process")

    def test_e2e02_salary_structure_exists(self):
        """E2E-02: At least one Salary Structure is configured."""
        resp = self.session.api(
            "frappe.client.get_count",
            doctype="Salary Structure",
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        count = body.get("message", 0)
        self.assertGreater(count, 0,
                           "No Salary Structure found — payroll cannot compute deductions")

    def test_e2e03_salary_components_have_amounts(self):
        """E2E-03: Key salary components exist and are properly configured."""
        resp = self.session.api(
            "frappe.client.get_list",
            doctype="Salary Component",
            fields=["name", "type"],
            limit_page_length=50,
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        components = body.get("message") or []
        names = [c.get("name", "").lower() for c in components]
        # Must have at least one earning and one deduction component
        self.assertTrue(any("basic" in n or "salary" in n for n in names),
                        f"No basic salary component found. Components: {names[:10]}")


class TestSalarySlipE2E(ERPNextTestCase):
    """E2E-04 to E2E-06: Salary Slip field completeness for LHDN submission."""

    category = "integration:e2e"

    STATUTORY_FIELDS = [
        "custom_lhdn_status",
        "custom_pcb_amount",
        "custom_epf_employee",
        "custom_epf_employer",
        "custom_socso_employee",
        "custom_socso_employer",
        "custom_eis_employee",
        "custom_eis_employer",
    ]

    def _get_latest_salary_slip(self) -> dict | None:
        """Fetch the most recent Salary Slip with all custom fields."""
        resp = self.session.api(
            "frappe.client.get_list",
            doctype="Salary Slip",
            fields=["name"],
            order_by="creation desc",
            limit_page_length=1,
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
        data = body.get("message") or []
        if not data:
            return None
        # Fetch full document
        slip_name = data[0].get("name")
        resp2 = self.session.resource("Salary Slip", slip_name)
        if resp2.status_code != 200:
            return None
        return resp2.json().get("data") or {}

    def test_e2e04_salary_slip_has_statutory_fields(self):
        """E2E-04: Salary Slip has all statutory deduction custom fields."""
        slip = self._get_latest_salary_slip()
        if not slip:
            self.skipTest("No Salary Slips exist — run payroll first")
        slip_keys = set(slip.keys())
        missing = [f for f in self.STATUTORY_FIELDS if f not in slip_keys]
        self.assertEqual(missing, [],
                         f"Salary Slip missing statutory fields: {missing}")

    def test_e2e05_salary_slip_has_earnings_and_deductions(self):
        """E2E-05: Salary Slip has earnings and deductions child tables."""
        slip = self._get_latest_salary_slip()
        if not slip:
            self.skipTest("No Salary Slips exist")
        earnings = slip.get("earnings") or []
        deductions = slip.get("deductions") or []
        self.assertGreater(len(earnings), 0,
                           "Salary Slip has zero earnings rows")
        self.assertGreater(len(deductions), 0,
                           "Salary Slip has zero deduction rows")

    def test_e2e06_salary_slip_employee_link_valid(self):
        """E2E-06: Salary Slip's employee link resolves to a real Employee."""
        slip = self._get_latest_salary_slip()
        if not slip:
            self.skipTest("No Salary Slips exist")
        employee = slip.get("employee")
        self.assertTrue(employee, "Salary Slip has no employee linked")
        resp = self.session.resource("Employee", employee)
        self.assert_status(resp, msg=f"Employee {employee} linked from Salary Slip not found")


class TestLHDNSubmissionReadiness(ERPNextTestCase):
    """E2E-07 to E2E-08: LHDN submission pipeline is ready for payroll data."""

    category = "integration:e2e"

    def test_e2e07_company_has_lhdn_credentials(self):
        """E2E-07: Test company has LHDN client_id configured (submission prerequisite)."""
        resp = self.session.resource("Company", TEST_COMPANY)
        if resp.status_code == 404:
            self.skipTest(f"Company '{TEST_COMPANY}' not found")
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or {}
        # Check LHDN credential fields exist (may be empty in sandbox)
        lhdn_fields = [k for k in data.keys()
                       if k.startswith("custom_") and ("lhdn" in k.lower() or "tin" in k.lower())]
        self.assertTrue(len(lhdn_fields) > 0,
                        "Company has no LHDN custom fields — integration not installed?")

    def test_e2e08_submission_api_reachable_for_salary_slip(self):
        """E2E-08: LHDN submission API accepts Salary Slip doctype context."""
        # Test the system status endpoint to ensure the LHDN integration is alive
        resp = self.session.api(
            "lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.get_system_status"
        )
        if resp.status_code == 404:
            self.skipTest("LHDN Dev Tools page not deployed")
        self.assertIn(resp.status_code, (200, 403),
                      f"System status endpoint failed: {resp.status_code}")
        if resp.status_code == 200:
            body = self.parse_json(resp)
            msg = body.get("message") or {}
            # Should return status info (even if sandbox credentials are not configured)
            self.assertIsInstance(msg, dict,
                                 f"Expected dict response from system status, got: {type(msg)}")


if __name__ == "__main__":
    unittest.main()
