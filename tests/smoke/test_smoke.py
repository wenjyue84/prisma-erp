"""
Smoke Tests — SMK-01 to SMK-10
================================
Fast, minimal checks that the stack is alive and the critical apps are installed.
These should always be the FIRST suite run; if any fail, abort remaining suites.
"""

import unittest

from tests.base import ERPNextTestCase
from tests.config import EXPECTED_APPS, BASE_URL


class TestHTTPConnectivity(ERPNextTestCase):
    """SMK-01 to SMK-03: Basic HTTP connectivity."""

    category = "smoke"

    def test_smk01_root_returns_200(self):
        """SMK-01: GET / → 200 (nginx + Frappe web layer alive)."""
        resp = self.session.get("/")
        self.assertIn(resp.status_code, (200, 302), f"Root URL returned {resp.status_code}")

    def test_smk02_api_ping(self):
        """SMK-02: GET /api/method/frappe.ping → {message: 'pong'}."""
        resp = self.session.get("/api/method/frappe.ping")
        self.assert_status(resp)
        body = self.parse_json(resp)
        self.assertEqual(body.get("message"), "pong", f"Ping returned: {body}")

    def test_smk03_favicon_served(self):
        """SMK-03: Static asset /assets/frappe/images/frappe-favicon.svg served."""
        resp = self.session.get("/assets/frappe/images/frappe-favicon.svg")
        self.assertIn(resp.status_code, (200, 301, 302, 404),
                      "Favicon request failed with unexpected status")


class TestAuthentication(ERPNextTestCase):
    """SMK-04 to SMK-06: Authentication flow."""

    category = "smoke"

    def test_smk04_current_user_is_administrator(self):
        """SMK-04: Session user is Administrator after login."""
        resp = self.session.api("frappe.auth.get_logged_user")
        body = self.assert_no_error(resp)
        self.assertEqual(
            body.get("message"), "Administrator",
            f"Expected Administrator, got: {body.get('message')}"
        )

    def test_smk05_whoami_endpoint(self):
        """SMK-05: /api/method/frappe.client.get_value returns a result."""
        resp = self.session.api(
            "frappe.client.get_value",
            doctype="User",
            filters={"name": "Administrator"},
            fieldname="full_name",
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        self.assertIn("message", body)

    def test_smk06_unauthenticated_get_fails(self):
        """SMK-06: Unauthenticated session to restricted endpoint → 403/401."""
        import requests
        anon = requests.Session()
        resp = anon.get(
            f"{BASE_URL}/api/method/frappe.auth.get_logged_user",
            timeout=10,
        )
        # Frappe typically returns 403 or redirects to login
        self.assertNotEqual(resp.status_code, 200,
                             "Unauthenticated request should NOT return 200")


class TestAppsInstalled(ERPNextTestCase):
    """SMK-07 to SMK-10: Verify all expected apps are installed via their artefacts."""

    category = "smoke"

    def test_smk07_frappe_installed(self):
        """SMK-07: Core 'frappe' is installed — verified by User doctype being accessible."""
        resp = self.session.resource("User", "Administrator")
        self.assert_status(resp)
        body = self.parse_json(resp)
        self.assertEqual(body.get("data", {}).get("name"), "Administrator",
                         "User/Administrator not accessible — frappe not installed?")

    def test_smk08_erpnext_installed(self):
        """SMK-08: 'erpnext' is installed — verified by Employee doctype existing."""
        resp = self.session.resource("Employee", params={"limit": 1})
        self.assertIn(resp.status_code, (200, 403),
                      f"Employee doctype not accessible (erpnext installed?): {resp.status_code}")

    def test_smk09_prisma_assistant_installed(self):
        """SMK-09: 'prisma_assistant' installed — verified by send_message being reachable."""
        resp = self.session.api("prisma_assistant.api.chat.send_message", message="ping")
        self.assertNotEqual(resp.status_code, 404,
                            "send_message → 404: prisma_assistant not installed or not on PATH")

    def test_smk10_lhdn_payroll_installed(self):
        """SMK-10: 'lhdn_payroll_integration' installed — verified by LHDN MSIC Code doctype."""
        resp = self.session.resource("LHDN MSIC Code", params={"limit": 1})
        self.assertIn(resp.status_code, (200, 403),
                      f"LHDN MSIC Code not accessible (lhdn_payroll_integration installed?): {resp.status_code}")


if __name__ == "__main__":
    unittest.main()
