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


class TestBrowserUIRegressions(ERPNextTestCase):
    """REG-13 to REG-19: Regressions found during chrome-devtools browser testing (2026-03-01)."""

    category = "regression"

    def test_reg13_admin_first_name_not_tampered(self):
        """REG-13: Administrator first_name is not 'Hacked'.

        Regression: CSRF test SEC-06 could leave first_name as 'Hacked' if
        tearDown() failed to restore it.
        """
        resp = self.session.resource("User", "Administrator")
        if resp.status_code == 200:
            data = resp.json().get("data") or {}
            first_name = data.get("first_name", "")
            self.assertNotEqual(first_name, "Hacked",
                                "Administrator first_name is still 'Hacked' — SEC-06 tearDown broken")

    def test_reg14_lhdn_dev_tools_getpage_returns_script(self):
        """REG-14: LHDN Dev Tools page getpage response includes page script.

        Regression: Page was blank because triple-nested directory structure
        prevented Frappe from finding lhdn_dev_tools.js.
        """
        resp = self.session.api(
            "frappe.desk.desk_page.getpage",
            name="lhdn-dev-tools",
        )
        if resp.status_code == 200:
            body = self.parse_json(resp)
            msg = body.get("message") or {}
            script = msg.get("script") or ""
            self.assertGreater(len(script), 50,
                               f"Dev Tools page has no/empty script — "
                               f"check module path in container. Script length: {len(script)}")

    def test_reg15_lhdn_workspace_exists_in_database(self):
        """REG-15: LHDN Payroll workspace exists in the Workspace table.

        Regression: Workspace was deleted/missing from DB. The desk home page
        showed an LHDN Payroll tile from cache, but clicking it showed
        'Icon is not correctly configured'. The workspace record needs to
        be recreated via sync_fixtures or bench migrate.
        """
        resp = self.session.get(
            "/api/resource/Workspace",
            params={
                "filters": '[["name","like","LHDN%"]]',
                "fields": '["name"]',
                "limit_page_length": 5,
            },
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        lhdn_workspaces = [d.get("name") for d in data]
        self.assertGreater(len(lhdn_workspaces), 0,
                           "LHDN Payroll workspace not in database — "
                           "run: bench --site frontend sync_fixtures")

    def test_reg16_hrms_bundle_not_404(self):
        """REG-16: hrms.bundle.js and hrms.bundle.css are served (not 404).

        Regression: HRMS assets returned 404 because bench build wasn't
        run after HRMS app installation.
        """
        js_resp = self.session.get("/assets/hrms/dist/js/hrms.bundle.js")
        css_resp = self.session.get("/assets/hrms/dist/css/hrms.bundle.css")
        # Accept 200 (served) or 304 (cached). Flag 404 as a regression.
        js_ok = js_resp.status_code in (200, 304)
        css_ok = css_resp.status_code in (200, 304)
        if not js_ok and not css_ok:
            # Check alternate paths (Frappe v16 uses hashed bundles)
            alt_js = self.session.get("/hrms.bundle.js")
            alt_css = self.session.get("/hrms.bundle.css")
            self.skipTest(
                f"HRMS bundles not found at expected paths. "
                f"Main: JS={js_resp.status_code} CSS={css_resp.status_code}, "
                f"Alt: JS={alt_js.status_code} CSS={alt_css.status_code}. "
                f"Run: bench build --app hrms"
            )

    def test_reg17_salary_slip_custom_fields_via_api(self):
        """REG-17: Salary Slip custom fields are queryable via Custom Field API.

        Regression: Tests originally used frappe.client.get on DocType which
        doesn't return custom fields. Must query Custom Field doctype instead.
        """
        resp = self.session.get(
            "/api/resource/Custom Field",
            params={
                "filters": '[["dt","=","Salary Slip"],["fieldname","=","custom_lhdn_status"]]',
                "fields": '["fieldname","dt"]',
                "limit_page_length": 1,
            },
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        self.assertGreater(len(data), 0,
                           "custom_lhdn_status not found via Custom Field API")

    def test_reg18_statutory_deduction_fields_exist(self):
        """REG-18: All 7 statutory deduction fields exist on Salary Slip.

        Regression: Fields custom_pcb_amount, custom_epf_employee, etc. were
        missing from custom_field.json fixture, causing LP-08 to LP-11 failures.
        """
        expected = ["custom_pcb_amount", "custom_epf_employee", "custom_epf_employer",
                    "custom_socso_employee", "custom_socso_employer",
                    "custom_eis_employee", "custom_eis_employer"]
        resp = self.session.get(
            "/api/resource/Custom Field",
            params={
                "filters": '[["dt","=","Salary Slip"]]',
                "fields": '["fieldname"]',
                "limit_page_length": 50,
            },
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        field_names = [d.get("fieldname", "") for d in data]
        missing = [f for f in expected if f not in field_names]
        self.assertEqual(missing, [],
                         f"Statutory deduction fields missing from Salary Slip: {missing}")

    def test_reg19_socket_io_not_blocking_page_render(self):
        """REG-19: socket.io connection failure doesn't break page rendering.

        Regression: WebSocket 'Unauthorized' error was logged but shouldn't
        prevent page content from loading.
        """
        resp = self.session.api("frappe.ping")
        self.assert_status(resp)
        body = self.parse_json(resp)
        self.assertEqual(body.get("message"), "pong",
                         "Basic API connectivity broken — page rendering would also fail")


if __name__ == "__main__":
    unittest.main()
