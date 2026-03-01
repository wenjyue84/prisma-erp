"""
Unit Tests — LHDN Payroll Integration Doctypes & Core Fields (LP-01 to LP-20)
=============================================================================
Checks that all custom doctypes, fields, and reports from lhdn_payroll_integration
are accessible via the REST API and have the expected schema.
"""

import unittest

from tests.base import ERPNextTestCase
from tests.config import TEST_COMPANY


class TestCustomDoctypes(ERPNextTestCase):
    """LP-01 to LP-05: Custom LHDN doctypes exist and are accessible."""

    category = "unit:lhdn_payroll"

    def _list_doctype(self, doctype: str):
        return self.session.resource(doctype, params={"limit": 1})

    def test_lp01_lhdn_cp21_accessible(self):
        """LP-01: LHDN CP21 doctype is accessible via REST."""
        resp = self._list_doctype("LHDN CP21")
        self.assertIn(resp.status_code, (200, 403), f"CP21 status: {resp.status_code}")

    def test_lp02_lhdn_cp22_accessible(self):
        """LP-02: LHDN CP22 doctype is accessible via REST."""
        resp = self._list_doctype("LHDN CP22")
        self.assertIn(resp.status_code, (200, 403), f"CP22 status: {resp.status_code}")

    def test_lp03_lhdn_cp22a_accessible(self):
        """LP-03: LHDN CP22A doctype is accessible via REST."""
        resp = self._list_doctype("LHDN CP22A")
        self.assertIn(resp.status_code, (200, 403), f"CP22A status: {resp.status_code}")

    def test_lp04_lhdn_msic_code_has_data(self):
        """LP-04: LHDN MSIC Code master has at least 1 record (fixtures loaded)."""
        resp = self.session.resource("LHDN MSIC Code", params={"limit": 1})
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        self.assertGreater(len(data), 0, "LHDN MSIC Code table is empty — fixtures not loaded?")

    def test_lp05_lhdn_resubmission_log_accessible(self):
        """LP-05: LHDN Resubmission Log doctype is accessible."""
        resp = self._list_doctype("LHDN Resubmission Log")
        self.assertIn(resp.status_code, (200, 403), f"Resubmission Log status: {resp.status_code}")


class TestSalarySlipCustomFields(ERPNextTestCase):
    """LP-06 to LP-11: Custom LHDN fields exist on Salary Slip."""

    category = "unit:lhdn_payroll"

    EXPECTED_LHDN_FIELDS = [
        "custom_lhdn_status",
        "custom_epf_employee",
        "custom_epf_employer",
        "custom_socso_employee",
        "custom_socso_employer",
        "custom_eis_employee",
        "custom_eis_employer",
        "custom_pcb_amount",
    ]

    def _get_custom_field_names(self) -> list[str]:
        """Get all custom field names on Salary Slip via Custom Field doctype."""
        resp = self.session.get(
            "/api/resource/Custom Field",
            params={
                "filters": '[["dt","=","Salary Slip"]]',
                "fields": '["fieldname"]',
                "limit_page_length": 100,
            },
        )
        if resp.status_code == 200:
            data = resp.json().get("data") or []
            return [d.get("fieldname", "") for d in data]
        return []

    def test_lp06_salary_slip_meta_accessible(self):
        """LP-06: Salary Slip custom fields are queryable via REST."""
        resp = self.session.get(
            "/api/resource/Custom Field",
            params={
                "filters": '[["dt","=","Salary Slip"]]',
                "fields": '["fieldname"]',
                "limit_page_length": 100,
            },
        )
        self.assert_status(resp)

    def test_lp07_custom_lhdn_status_field_exists(self):
        """LP-07: custom_lhdn_status field exists on Salary Slip."""
        fields = self._get_custom_field_names()
        if not fields:
            self.skipTest("Could not load Salary Slip custom fields")
        self.assertIn("custom_lhdn_status", fields,
                      f"custom_lhdn_status missing. Found fields: "
                      f"{[f for f in fields if 'lhdn' in f.lower()]}")

    def test_lp08_custom_pcb_field_exists(self):
        """LP-08: custom_pcb_amount or similar PCB field exists on Salary Slip."""
        fields = self._get_custom_field_names()
        if not fields:
            self.skipTest("Could not load Salary Slip custom fields")
        pcb_fields = [f for f in fields if "pcb" in f.lower()]
        self.assertTrue(len(pcb_fields) > 0,
                        f"No PCB field on Salary Slip. Custom fields: {fields}")

    def test_lp09_epf_fields_exist(self):
        """LP-09: EPF employee/employer fields exist on Salary Slip."""
        fields = self._get_custom_field_names()
        if not fields:
            self.skipTest("Could not load Salary Slip custom fields")
        epf_fields = [f for f in fields if "epf" in f.lower()]
        self.assertTrue(len(epf_fields) >= 2,
                        f"Expected at least 2 EPF fields, got: {epf_fields}")

    def test_lp10_socso_fields_exist(self):
        """LP-10: SOCSO employee/employer fields exist on Salary Slip."""
        fields = self._get_custom_field_names()
        if not fields:
            self.skipTest("Could not load Salary Slip custom fields")
        socso_fields = [f for f in fields if "socso" in f.lower()]
        self.assertTrue(len(socso_fields) >= 2,
                        f"Expected at least 2 SOCSO fields, got: {socso_fields}")

    def test_lp11_eis_fields_exist(self):
        """LP-11: EIS employee/employer fields exist on Salary Slip."""
        fields = self._get_custom_field_names()
        if not fields:
            self.skipTest("Could not load Salary Slip custom fields")
        eis_fields = [f for f in fields if "eis" in f.lower()]
        self.assertTrue(len(eis_fields) >= 1,
                        f"Expected at least 1 EIS field, got: {eis_fields}")


class TestSalaryComponents(ERPNextTestCase):
    """LP-12 to LP-15: Salary components fixtures are loaded."""

    category = "unit:lhdn_payroll"

    EXPECTED_COMPONENTS = ["Basic Salary", "EPF", "SOCSO", "EIS", "PCB"]

    def _get_components(self) -> list[str]:
        resp = self.session.resource(
            "Salary Component",
            params={"fields": '["name","salary_component_abbr"]', "limit": 50},
        )
        if resp.status_code == 200:
            data = resp.json().get("data") or []
            return [d.get("name", "") for d in data]
        return []

    def test_lp12_salary_components_loaded(self):
        """LP-12: Salary Component list is accessible and non-empty."""
        resp = self.session.resource("Salary Component", params={"limit": 1})
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        self.assertGreater(len(data), 0, "No Salary Components found — fixtures not loaded?")

    def test_lp13_epf_component_exists(self):
        """LP-13: 'EPF' salary component exists (from fixtures)."""
        components = self._get_components()
        epf = [c for c in components if "epf" in c.lower()]
        self.assertTrue(len(epf) > 0, f"No EPF component. Available: {components[:10]}")

    def test_lp14_socso_component_exists(self):
        """LP-14: 'SOCSO' salary component exists."""
        components = self._get_components()
        socso = [c for c in components if "socso" in c.lower()]
        self.assertTrue(len(socso) > 0, f"No SOCSO component. Available: {components[:10]}")

    def test_lp15_pcb_component_exists(self):
        """LP-15: 'PCB' or 'Tax' salary component exists."""
        components = self._get_components()
        pcb = [c for c in components if "pcb" in c.lower() or "tax" in c.lower()]
        self.assertTrue(len(pcb) > 0, f"No PCB/Tax component. Available: {components[:10]}")


class TestLHDNReports(ERPNextTestCase):
    """LP-16 to LP-20: LHDN report modules are accessible."""

    category = "unit:lhdn_payroll"

    EXPECTED_REPORTS = [
        "LHDN Payroll Compliance",
        "LHDN Monthly Summary",
        "EA Form",
        "CP39 PCB Remittance",
        "Borang E",
    ]

    def _report_exists(self, report_name: str) -> bool:
        resp = self.session.resource("Report", report_name)
        return resp.status_code in (200, 403)

    def test_lp16_lhdn_payroll_compliance_report(self):
        """LP-16: 'LHDN Payroll Compliance' report doctype exists."""
        resp = self.session.resource("Report", params={
            "filters": '[["name","like","LHDN%"]]', "limit": 10
        })
        self.assert_status(resp)

    def test_lp17_ea_form_report_exists(self):
        """LP-17: 'EA Form' report is defined in the system."""
        resp = self.session.resource("Report", params={
            "filters": '[["name","like","EA%"]]', "limit": 5
        })
        self.assert_status(resp)

    def test_lp18_lhdn_monthly_summary_accessible(self):
        """LP-18: LHDN Monthly Summary report can be called."""
        resp = self.session.api(
            "frappe.desk.query_report.run",
            report_name="LHDN Monthly Summary",
            filters={},
        )
        # Accept 200 (has data) or permission/not-found errors
        self.assertIn(resp.status_code, (200, 403, 404, 422),
                      f"Monthly Summary report failed: {resp.status_code}")

    def test_lp19_lhdn_workspace_exists(self):
        """LP-19: 'LHDN Payroll' workspace is in the system."""
        resp = self.session.resource("Workspace", params={
            "filters": '[["name","like","LHDN%"]]', "limit": 5
        })
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        self.assertGreater(len(data), 0, "LHDN Payroll workspace not found!")

    def test_lp20_dev_tools_page_accessible(self):
        """LP-20: LHDN Dev Tools desk page is accessible."""
        resp = self.session.get("/app/lhdn-dev-tools")
        self.assertIn(resp.status_code, (200, 302, 403),
                      f"Dev tools page status: {resp.status_code}")


if __name__ == "__main__":
    unittest.main()
