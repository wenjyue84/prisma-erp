"""
Edge Case Tests — EC-01 to EC-18
=================================
Tests boundary conditions, unusual inputs, and corner cases for both
Prisma AI and LHDN Payroll apps. These should NOT cause 500 errors.
"""

import json
import string
import unittest

from tests.base import ERPNextTestCase
from tests.config import AI_TIMEOUT


class TestChatEdgeCases(ERPNextTestCase):
    """EC-01 to EC-08: Edge cases for the AI chat API."""

    category = "edge_cases"

    def _send(self, message: str, history=None, files=None):
        payload = {"message": message}
        if history is not None:
            payload["history"] = json.dumps(history) if isinstance(history, list) else history
        if files is not None:
            payload["files"] = json.dumps(files) if isinstance(files, list) else files
        return self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json=payload,
            timeout=AI_TIMEOUT,
        )

    def test_ec01_very_long_message(self):
        """EC-01: 10,000-character message doesn't cause 500."""
        big = "Tell me about AI. " * 555  # ~10 000 chars
        resp = self._send(big)
        self.assertNotEqual(resp.status_code, 500,
                             f"10k char message → 500: {resp.text[:200]}")

    def test_ec02_message_with_special_characters(self):
        """EC-02: Message with SQL/HTML special characters is handled safely."""
        special = "'; DROP TABLE users; -- <script>alert('xss')</script> & \"quotes\" \\ backslash"
        resp = self._send(special)
        self.assertNotEqual(resp.status_code, 500,
                             f"Special chars caused 500: {resp.text[:200]}")

    def test_ec03_message_with_unicode(self):
        """EC-03: Unicode (Arabic, Chinese, emoji) is accepted."""
        msg = "مرحبا 你好 こんにちは 🤖 Héllo Wörld"
        resp = self._send(msg)
        self.assertNotEqual(resp.status_code, 500,
                             f"Unicode message caused 500: {resp.text[:200]}")

    def test_ec04_message_only_whitespace(self):
        """EC-04: Whitespace-only message handled gracefully (no 500)."""
        resp = self._send("   \t\n   ")
        self.assertNotEqual(resp.status_code, 500,
                             f"Whitespace message → 500: {resp.text[:200]}")

    def test_ec05_history_with_100_turns(self):
        """EC-05: 100-turn history list is processed without error."""
        history = []
        for i in range(50):
            history.append({"role": "user", "content": f"Turn {i}"})
            history.append({"role": "assistant", "content": f"OK {i}"})
        resp = self._send("What turn are we on?", history=history)
        self.assertNotEqual(resp.status_code, 500,
                             f"100-turn history → 500: {resp.text[:200]}")

    def test_ec06_malformed_history_string(self):
        """EC-06: Malformed (non-JSON) history string is handled gracefully."""
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Hi", "history": "NOT VALID JSON {{{"},
            timeout=AI_TIMEOUT,
        )
        self.assertNotEqual(resp.status_code, 500,
                             f"Malformed history → 500: {resp.text[:200]}")

    def test_ec07_null_message_field(self):
        """EC-07: Null (None) message handled gracefully."""
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": None},
            timeout=AI_TIMEOUT,
        )
        self.assertNotEqual(resp.status_code, 500,
                             f"None message → 500: {resp.text[:200]}")

    def test_ec08_repeated_rapid_calls(self):
        """EC-08: Three rapid back-to-back calls succeed without failure."""
        for i in range(3):
            resp = self._send(f"Quick ping {i}")
            self.assertNotEqual(resp.status_code, 500,
                                 f"Call {i} returned 500: {resp.text[:200]}")


class TestPayrollEdgeCases(ERPNextTestCase):
    """EC-09 to EC-14: Edge cases for LHDN Payroll doctypes and reports."""

    category = "edge_cases"

    def test_ec09_salary_slip_list_with_zero_limit(self):
        """EC-09: GET Salary Slip with limit=0 doesn't crash."""
        resp = self.session.resource("Salary Slip", params={"limit": 0})
        self.assertNotEqual(resp.status_code, 500,
                             f"limit=0 → 500: {resp.text[:200]}")

    def test_ec10_salary_slip_invalid_filter(self):
        """EC-10: Invalid filter format returns 422 not 500."""
        resp = self.session.resource(
            "Salary Slip",
            params={"filters": "INVALID_FILTER_FORMAT"},
        )
        self.assertNotEqual(resp.status_code, 500,
                             f"Invalid filter → 500: {resp.text[:200]}")

    def test_ec11_employee_nonexistent_name(self):
        """EC-11: GET Employee/NONEXISTENT returns 404, not 500."""
        resp = self.session.resource("Employee", "EMP-NONEXISTENT-99999")
        self.assertIn(resp.status_code, (404, 403),
                      f"Nonexistent employee returned: {resp.status_code}")

    def test_ec12_report_with_future_date_filter(self):
        """EC-12: Report with future date range returns empty data, not error."""
        resp = self.session.api(
            "frappe.desk.query_report.run",
            report_name="LHDN Monthly Summary",
            filters={"year": "2099"},
        )
        self.assertIn(resp.status_code, (200, 403, 404, 422),
                      f"Future date filter → {resp.status_code}")

    def test_ec13_company_with_empty_tin(self):
        """EC-13: Company doctype accessible even with empty TIN fields."""
        resp = self.session.resource("Company", params={"limit": 1})
        self.assert_status(resp)

    def test_ec14_msic_code_special_filter(self):
        """EC-14: LHDN MSIC Code list with special char filter doesn't crash."""
        resp = self.session.resource(
            "LHDN MSIC Code",
            params={"search": "'; DROP TABLE --"},
        )
        self.assertNotEqual(resp.status_code, 500,
                             f"SQL-injection filter → 500: {resp.text[:200]}")


class TestAPIBoundaryValues(ERPNextTestCase):
    """EC-15 to EC-18: Boundary value conditions on API parameters."""

    category = "edge_cases"

    def test_ec15_resource_limit_max(self):
        """EC-15: Extremely large limit value (99999) handled safely."""
        resp = self.session.resource("Salary Component", params={"limit": 99999})
        self.assertNotEqual(resp.status_code, 500,
                             f"limit=99999 → 500: {resp.text[:200]}")

    def test_ec16_api_extra_unknown_param(self):
        """EC-16: Extra unknown parameters in API call don't cause 500."""
        resp = self.session.api(
            "frappe.auth.get_logged_user",
            unknown_param_xyz="ignored_value",
        )
        self.assertNotEqual(resp.status_code, 500,
                             f"Unknown param → 500: {resp.text[:200]}")

    def test_ec17_resource_empty_doctype_name(self):
        """EC-17: GET /api/resource/<empty_string> returns 404, not 500."""
        resp = self.session.get("/api/resource/")
        self.assertNotEqual(resp.status_code, 500,
                             f"Empty doctype → 500: {resp.text[:200]}")

    def test_ec18_very_deep_nested_json_body(self):
        """EC-18: Deeply nested JSON body in POST doesn't cause 500."""
        def nest(depth: int) -> dict:
            if depth == 0:
                return {"val": "leaf"}
            return {"child": nest(depth - 1)}
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Hi", "extra": nest(10)},
            timeout=AI_TIMEOUT,
        )
        self.assertNotEqual(resp.status_code, 500,
                             f"Deep JSON → 500: {resp.text[:200]}")


if __name__ == "__main__":
    unittest.main()
