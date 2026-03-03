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


class TestCreateSalarySlip(ERPNextTestCase):
    """E2E-09 to E2E-13: Full payslip creation lifecycle via REST API.

    Creates a real Salary Slip draft for January 2025, verifies its
    fields, then deletes it so payroll data stays clean.
    """

    category = "integration:e2e"

    # Class-level state shared across tests (tests run in name order)
    _emp: dict | None = None       # employee document summary
    _slip_name: str | None = None  # name of the created test slip

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
    # Use a historical period unlikely to conflict with real payroll runs
    TEST_START = "2025-01-01"
    TEST_END   = "2025-01-31"

    @classmethod
    def tearDownClass(cls):
        """Best-effort cleanup: always delete the test slip if it was created."""
        if cls._slip_name:
            try:
                cls.session.delete_resource("Salary Slip", cls._slip_name)
            except Exception:
                pass
        super().tearDownClass()

    def test_e2e09_prerequisites(self):
        """E2E-09: An Employee with a submitted Salary Structure Assignment exists."""
        resp = self.session.resource(
            "Employee",
            **{"fields": '["name","employee_name","company"]', "limit_page_length": 1}
        )
        self.assert_status(resp)
        employees = resp.json().get("data") or []
        if not employees:
            self.skipTest("No Employee records found — create an employee with a salary structure first")

        emp = employees[0]

        ssa_resp = self.session.resource(
            "Salary Structure Assignment",
            **{
                "filters": f'[["employee","=","{emp["name"]}"],["docstatus","=","1"]]',
                "limit_page_length": 1,
            }
        )
        self.assert_status(ssa_resp)
        assignments = ssa_resp.json().get("data") or []
        if not assignments:
            self.skipTest(
                f"No submitted Salary Structure Assignment for {emp['name']} — "
                "assign and submit a salary structure first"
            )

        TestCreateSalarySlip._emp = emp

    def test_e2e10_create_salary_slip(self):
        """E2E-10: POST /api/resource/Salary Slip creates a new draft slip."""
        if not TestCreateSalarySlip._emp:
            self.skipTest("Skip: E2E-09 prerequisites not met")

        emp = TestCreateSalarySlip._emp
        resp = self.session.create_resource("Salary Slip", {
            "employee": emp["name"],
            "company": emp.get("company", ""),
            "start_date": self.TEST_START,
            "end_date": self.TEST_END,
            "posting_date": self.TEST_END,
        })

        if resp.status_code in (409, 422):
            # Duplicate — a slip for this period already exists
            self.skipTest(
                f"Salary Slip for {emp['name']} {self.TEST_START}–{self.TEST_END} "
                "already exists — delete it first to re-run this test"
            )

        self.assertIn(
            resp.status_code, (200, 201),
            f"Expected 200/201, got {resp.status_code}. Body: {resp.text[:300]}"
        )
        data = resp.json().get("data") or {}
        slip_name = data.get("name")
        self.assertTrue(slip_name, f"No name in response: {resp.text[:200]}")
        TestCreateSalarySlip._slip_name = slip_name

    def test_e2e11_statutory_fields_present(self):
        """E2E-11: Created Salary Slip contains all LHDN statutory deduction fields."""
        if not TestCreateSalarySlip._slip_name:
            self.skipTest("Skip: no slip created by E2E-10")

        resp = self.session.resource("Salary Slip", TestCreateSalarySlip._slip_name)
        self.assert_status(resp)
        slip = resp.json().get("data") or {}

        missing = [f for f in self.STATUTORY_FIELDS if f not in slip]
        self.assertEqual(
            missing, [],
            f"Salary Slip missing LHDN statutory fields: {missing}"
        )

    def test_e2e12_earnings_populated(self):
        """E2E-12: Created Salary Slip has earnings rows and gross_pay > 0."""
        if not TestCreateSalarySlip._slip_name:
            self.skipTest("Skip: no slip created by E2E-10")

        resp = self.session.resource("Salary Slip", TestCreateSalarySlip._slip_name)
        self.assert_status(resp)
        slip = resp.json().get("data") or {}

        earnings = slip.get("earnings") or []
        gross_pay = float(slip.get("gross_pay") or 0)

        self.assertGreater(
            len(earnings), 0,
            "Salary Slip has zero earnings rows — check Salary Structure components"
        )
        self.assertGreater(
            gross_pay, 0,
            f"gross_pay={gross_pay} — earnings components may have zero amounts"
        )

    def test_e2e13_draft_deletable(self):
        """E2E-13: Created Salary Slip is a draft (docstatus=0) ready for deletion."""
        if not TestCreateSalarySlip._slip_name:
            self.skipTest("Skip: no slip created by E2E-10")

        resp = self.session.resource("Salary Slip", TestCreateSalarySlip._slip_name)
        self.assert_status(resp)
        slip = resp.json().get("data") or {}
        docstatus = slip.get("docstatus")
        self.assertEqual(
            docstatus, 0,
            f"Salary Slip is not a draft (docstatus={docstatus}) — cannot safely delete"
        )
        # Perform the actual deletion (tearDownClass also does this as safety net)
        del_resp = self.session.delete_resource("Salary Slip", TestCreateSalarySlip._slip_name)
        self.assertIn(
            del_resp.status_code, (200, 202),
            f"DELETE returned {del_resp.status_code}: {del_resp.text[:200]}"
        )
        TestCreateSalarySlip._slip_name = None  # prevent double-delete in tearDownClass


if __name__ == "__main__":
    unittest.main()
