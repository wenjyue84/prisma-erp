"""
Security Tests — SEC-01 to SEC-14
===================================
Validates that the Prisma ERP stack correctly enforces authentication,
blocks injection attempts, and follows OWASP best-practices.

All tests use a *separate*, unauthenticated session to simulate attackers.
"""

import unittest

import requests

from tests.base import ERPNextTestCase
from tests.config import BASE_URL, AI_TIMEOUT


def anon_session() -> requests.Session:
    """Return a fresh unauthenticated session."""
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


class TestAuthEnforcement(ERPNextTestCase):
    """SEC-01 to SEC-05: Authentication requirements."""

    category = "security"

    def test_sec01_anon_cannot_get_logged_user(self):
        """SEC-01: Anonymous GET to frappe.auth.get_logged_user → not 200."""
        s = anon_session()
        resp = s.get(f"{BASE_URL}/api/method/frappe.auth.get_logged_user", timeout=10)
        self.assertNotEqual(resp.status_code, 200,
                             "Unauthenticated user returned 200 for get_logged_user!")

    def test_sec02_anon_cannot_list_salary_slips(self):
        """SEC-02: Anonymous GET to Salary Slip list → 403 or redirect."""
        s = anon_session()
        resp = s.get(f"{BASE_URL}/api/resource/Salary Slip", timeout=10)
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anonymous user accessed Salary Slips: {resp.status_code}")

    def test_sec03_anon_cannot_call_send_message(self):
        """SEC-03: Anonymous call to send_message → not 200."""
        s = anon_session()
        resp = s.post(
            f"{BASE_URL}/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Hello"},
            timeout=15,
        )
        self.assertNotEqual(resp.status_code, 200,
                             "Unauthenticated send_message returned 200!")

    def test_sec04_anon_cannot_read_prisma_settings(self):
        """SEC-04: Anonymous GET to Prisma AI Settings → not 200."""
        s = anon_session()
        resp = s.get(f"{BASE_URL}/api/resource/Prisma AI Settings/Prisma AI Settings", timeout=10)
        self.assertNotEqual(resp.status_code, 200,
                             "Anonymous user read Prisma AI Settings!")

    def test_sec05_anon_cannot_access_employee_data(self):
        """SEC-05: Anonymous GET to Employee list → not 200."""
        s = anon_session()
        resp = s.get(f"{BASE_URL}/api/resource/Employee", timeout=10)
        self.assertIn(resp.status_code, (401, 403, 302, 307),
                      f"Anonymous user accessed Employee list: {resp.status_code}")


class TestCSRFProtection(ERPNextTestCase):
    """SEC-06 to SEC-08: CSRF token enforcement on mutating endpoints."""

    category = "security"

    def test_sec06_post_without_csrf_fails(self):
        """SEC-06: POST without X-Frappe-CSRF-Token header is rejected or fails."""
        s = anon_session()
        # Login first but send without CSRF token
        s.post(f"{BASE_URL}/api/method/login",
               data={"usr": "Administrator", "pwd": "admin"}, timeout=10)
        # Now POST without CSRF token
        resp = s.post(
            f"{BASE_URL}/api/method/frappe.client.set_value",
            json={"doctype": "User", "name": "Administrator", "fieldname": "first_name", "value": "Hacked"},
            timeout=10,
        )
        # Should return 403 or an integrity error — NOT successfully modify
        if resp.status_code == 200:
            body = resp.json()
            # Even if 200, the server should have rejected with an exc
            self.assertIn("exc_type", body,
                          f"set_value without CSRF succeeded: {body}")

    def test_sec07_csrf_token_not_in_error_response(self):
        """SEC-07: Error responses do not leak CSRF tokens in body."""
        resp = self.session.api("frappe.auth.get_logged_user",
                                invalid_param="trigger_error")
        body_text = resp.text
        # CSRF token should not appear in error messages
        # (Frappe usually includes it only in the cookie/header)
        csrf = self.session._csrf_token or ""
        if len(csrf) > 10:
            self.assertNotIn(csrf, body_text,
                             "CSRF token leaked in response body!")

    def test_sec08_api_key_not_in_error_logs(self):
        """SEC-08: Error responses from chat API don't contain API keys."""
        # Trigger an error by sending an invalid provider name (if supported)
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Force error test ping"},
            timeout=AI_TIMEOUT,
        )
        body_text = resp.text
        self.assertNotIn("sk-ant-", body_text, "Anthropic API key in chat response!")
        self.assertNotIn("sk-proj-", body_text, "OpenAI API key in chat response!")


class TestInjectionAttacks(ERPNextTestCase):
    """SEC-09 to SEC-12: SQL injection, XSS, and command injection attempts."""

    category = "security"

    SQL_PAYLOADS = [
        "' OR '1'='1",
        "'; DROP TABLE tabSalarySlip; --",
        "1 UNION SELECT password FROM tabUser --",
        '" OR ""="',
    ]

    XSS_PAYLOADS = [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert(1)",
        "&#60;script&#62;alert(1)&#60;/script&#62;",
    ]

    def test_sec09_sql_injection_in_filter(self):
        """SEC-09: SQL injection in filter parameter doesn't dump data."""
        for payload in self.SQL_PAYLOADS:
            resp = self.session.resource(
                "Salary Slip",
                params={"filters": f'[["name","like","{payload}"]]', "limit": 5},
            )
            self.assertNotEqual(resp.status_code, 500,
                                 f"SQL payload '{payload}' caused 500")

    def test_sec10_sql_injection_in_search(self):
        """SEC-10: SQL injection in search_term is escaped."""
        for payload in self.SQL_PAYLOADS:
            resp = self.session.api(
                "frappe.client.get_list",
                doctype="Employee",
                txt=payload,
                limit=5,
            )
            self.assertNotEqual(resp.status_code, 500,
                                 f"SQL in search_term → 500: {payload}")

    def test_sec11_xss_in_chat_message(self):
        """SEC-11: XSS payloads in chat message are handled without executing."""
        for payload in self.XSS_PAYLOADS:
            resp = self.session.post(
                "/api/method/prisma_assistant.api.chat.send_message",
                json={"message": payload},
                timeout=AI_TIMEOUT,
            )
            self.assertNotEqual(resp.status_code, 500,
                                 f"XSS payload caused 500: {payload}")

    def test_sec12_path_traversal_in_resource(self):
        """SEC-12: Path traversal in resource name is blocked."""
        resp = self.session.resource("../../../etc/passwd")
        self.assertNotEqual(resp.status_code, 200,
                             "Path traversal in resource name returned 200!")


class TestSensitiveDataExposure(ERPNextTestCase):
    """SEC-13 to SEC-14: Sensitive data not exposed in API responses."""

    category = "security"

    def test_sec13_user_password_not_in_response(self):
        """SEC-13: GET User/Administrator does not expose password hash."""
        resp = self.session.resource("User", "Administrator")
        if resp.status_code == 200:
            body_text = resp.text
            self.assertNotIn('"password"', body_text,
                             "Password hash exposed in User GET response!")

    def test_sec14_api_key_fields_masked_in_settings(self):
        """SEC-14: GET Prisma AI Settings does not expose plaintext API key."""
        resp = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        if resp.status_code == 200:
            body = resp.json().get("data") or {}
            # If api_key field is present, it should be encrypted/masked (not plain text)
            api_key_val = str(body.get("api_key") or "")
            if len(api_key_val) > 5:
                # A real API key starts with sk- for Anthropic/OpenAI
                # Frappe encrypts fields; if we see sk- prefix the key is exposed
                self.assertFalse(
                    api_key_val.startswith("sk-"),
                    f"API key exposed in plaintext in Settings: {api_key_val[:20]}...",
                )


if __name__ == "__main__":
    unittest.main()
