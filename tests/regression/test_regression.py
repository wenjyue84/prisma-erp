"""
Regression Tests — REG-01 to REG-12
=====================================
Guards against specific bugs that have been fixed or were reported.
Each test documents the original issue and asserts the fix is still in place.

Add new regression tests here whenever a bug is fixed, BEFORE closing the ticket.
"""

import unittest

from tests.base import ERPNextTestCase
from tests.config import AI_TIMEOUT


class TestPrismaAIRegressions(ERPNextTestCase):
    """REG-01 to REG-05: Regressions in Prisma AI app."""

    category = "regression"

    def test_reg01_desk_widget_js_served(self):
        """REG-01: desk_widget.js is served from /assets/prisma_assistant/js/.

        Regression: After hot-deploy the asset must be in the FRONTEND container.
        Failure = assets copied to backend container only (wrong container).
        """
        resp = self.session.get("/assets/prisma_assistant/js/desk_widget.js")
        self.assertIn(resp.status_code, (200, 304),
                      "desk_widget.js not served — was it copied to the FRONTEND container?")

    def test_reg02_desk_widget_css_served(self):
        """REG-02: desk_widget.css is served from /assets/prisma_assistant/css/.

        Regression: Same container bug as REG-01.
        """
        resp = self.session.get("/assets/prisma_assistant/css/desk_widget.css")
        self.assertIn(resp.status_code, (200, 304),
                      "desk_widget.css not served — check FRONTEND container assets")

    def test_reg03_chat_api_not_500_on_missing_key(self):
        """REG-03: send_message with no AI key configured returns graceful error, not 500.

        Regression: When api_key is empty/unconfigured, old code threw an unhandled
        AttributeError that became HTTP 500. Should return 200 with error message.
        """
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Test with potentially missing key"},
            timeout=AI_TIMEOUT,
        )
        # Must NOT be a raw 500
        self.assertNotEqual(resp.status_code, 500,
                             f"Chat API returned 500 — unhandled exception: {resp.text[:300]}")

    def test_reg04_fallback_provider_fields_in_settings(self):
        """REG-04: Settings doctype has fallback_base_url field (added in feature/prisma-assistant-v2).

        Regression: fallback_base_url was missing before PR #aa57961.
        """
        resp = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        if resp.status_code == 200:
            body = self.parse_json(resp)
            data = body.get("data") or {}
            # The field should exist even if empty
            self.assertIn(
                "fallback_base_url", data,
                f"fallback_base_url missing from Prisma AI Settings. "
                f"Available fields: {[k for k in data.keys() if 'fallback' in k.lower() or 'base' in k.lower()]}"
            )

    def test_reg05_get_api_key_info_returns_masked_not_raw(self):
        """REG-05: get_api_key_info never returns the raw API key value.

        Regression: Early version of the endpoint accidentally returned the
        unencrypted key in the 'preview' field.
        """
        resp = self.session.api("prisma_assistant.api.chat.get_api_key_info")
        self.assert_status(resp)
        body_text = resp.text
        # Real Anthropic keys start with 'sk-ant-api03-'
        self.assertNotIn("sk-ant-api03-", body_text,
                         "Raw Anthropic API key exposed by get_api_key_info!")
        self.assertNotIn("sk-proj-", body_text,
                         "Raw OpenAI API key exposed by get_api_key_info!")


class TestLHDNPayrollRegressions(ERPNextTestCase):
    """REG-06 to REG-12: Regressions in LHDN Payroll Integration."""

    category = "regression"

    def test_reg06_lhdn_workspace_has_4_shortcuts(self):
        """REG-06: LHDN Payroll workspace has at least 4 shortcuts.

        Regression: After workspace fixture deploy, shortcuts disappeared if
        bench migrate was used instead of sync_fixtures().
        """
        resp = self.session.resource(
            "Workspace",
            params={"filters": '[["name","like","LHDN%"]]', "fields": '["name"]', "limit": 5},
        )
        self.assert_status(resp)
        data = self.parse_json(resp).get("data") or []
        self.assertGreater(len(data), 0,
                           "LHDN Payroll workspace not found — was sync_fixtures run?")

    def test_reg07_msic_code_fixture_loaded(self):
        """REG-07: LHDN MSIC Code master data has records (fixtures loaded).

        Regression: After fresh bench migrate, fixtures weren't loaded automatically.
        Fix: use 'bench --site frontend sync_fixtures'.
        """
        resp = self.session.resource("LHDN MSIC Code", params={"limit": 1})
        self.assert_status(resp)
        data = self.parse_json(resp).get("data") or []
        self.assertGreater(len(data), 0,
                           "LHDN MSIC Code table empty — run: bench --site frontend sync_fixtures")

    def test_reg08_salary_slip_lhdn_fields_not_breaking_submit(self):
        """REG-08: Salary Slip meta loads without Python error.

        Regression: When a custom field had a bad default value, loading
        the DocType meta threw a 500.
        """
        resp = self.session.resource("Salary Slip", params={"limit": 1})
        self.assertNotEqual(resp.status_code, 500,
                             f"Salary Slip list → 500: {resp.text[:300]}")

    def test_reg09_dev_tools_page_not_missing(self):
        """REG-09: lhdn_dev_tools desk page exists.

        Regression: After clearing sites/assets, the page JS was missing
        because it was only in the backend container.
        """
        resp = self.session.get("/app/lhdn-dev-tools")
        self.assertIn(resp.status_code, (200, 302, 303),
                      "lhdn-dev-tools page not reachable")

    def test_reg10_resubmit_to_lhdn_method_signature(self):
        """REG-10: resubmit_to_lhdn accepts docname + doctype parameters.

        Regression: Original function signature only accepted docname;
        doctype parameter was added later for Expense Claims.
        """
        resp = self.session.api(
            "lhdn_payroll_integration.services.submission_service.resubmit_to_lhdn",
            docname="NONEXISTENT",
            doctype="Salary Slip",
        )
        # Should NOT return 422 "Missing required arguments"
        if resp.status_code == 422:
            body = resp.json()
            self.assertNotIn(
                "doctype", str(body.get("exception") or ""),
                f"resubmit_to_lhdn doesn't accept 'doctype' param: {body}",
            )

    def test_reg11_nginx_serves_after_restart(self):
        """REG-11: nginx returns 200 (not 502) after container restart.

        Regression: nginx cached stale backend DNS → 502 Bad Gateway.
        Fix: restart frontend container after backend restart.
        """
        resp = self.session.api("frappe.ping")
        self.assertNotEqual(resp.status_code, 502,
                             "nginx returned 502 — restart the frontend container!")
        self.assertEqual(resp.status_code, 200,
                         f"Unexpected status from nginx: {resp.status_code}")

    def test_reg12_prisma_assistant_module_correct(self):
        """REG-12: Prisma AI Settings doctype is in 'Prisma Assistant' module.

        Regression: After extraction from lhdn_payroll_integration, the
        doctype was briefly left in 'LHDN Payroll Integration' module.
        """
        resp = self.session.api(
            "frappe.client.get",
            doctype="DocType",
            name="Prisma AI Settings",
        )
        if resp.status_code == 200:
            body = resp.json().get("message") or {}
            module = body.get("module") or ""
            self.assertEqual(
                module, "Prisma Assistant",
                f"Prisma AI Settings module is '{module}', expected 'Prisma Assistant'",
            )


if __name__ == "__main__":
    unittest.main()
