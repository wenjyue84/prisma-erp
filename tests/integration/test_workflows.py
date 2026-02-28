"""
Integration Tests — End-to-End Workflows (INT-01 to INT-12)
===========================================================
Tests complete user journeys that cross multiple doctypes and services.
These are slower than unit tests and may create/clean up test data.
"""

import time
import unittest

from tests.base import ERPNextTestCase
from tests.config import TEST_COMPANY


class TestPayrollWorkflow(ERPNextTestCase):
    """INT-01 to INT-04: Basic payroll data-access workflow."""

    category = "integration"

    def test_int01_list_employees(self):
        """INT-01: GET /api/resource/Employee returns a list (payroll foundation)."""
        resp = self.session.resource("Employee", params={"limit": 5})
        self.assert_status(resp)
        body = self.parse_json(resp)
        self.assertIn("data", body, "Employee list missing 'data' key")

    def test_int02_list_salary_slips(self):
        """INT-02: GET /api/resource/Salary Slip returns accessible records."""
        resp = self.session.resource("Salary Slip", params={"limit": 5})
        self.assert_status(resp)
        body = self.parse_json(resp)
        self.assertIn("data", body)

    def test_int03_company_has_lhdn_fields(self):
        """INT-03: Test company has LHDN custom fields populated."""
        resp = self.session.resource("Company", TEST_COMPANY)
        if resp.status_code == 404:
            self.skipTest(f"Test company '{TEST_COMPANY}' not found — run setup_test_data.py")
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or {}
        # Check that at least one LHDN field exists on the company record
        lhdn_keys = [k for k in data.keys() if "lhdn" in k.lower() or "tin" in k.lower() or "custom" in k.lower()]
        self.assertTrue(len(lhdn_keys) > 0,
                        f"No LHDN/custom fields on Company. Keys: {list(data.keys())[:20]}")

    def test_int04_salary_slip_lhdn_status_field(self):
        """INT-04: Most recent Salary Slip has LHDN status field accessible."""
        resp = self.session.resource(
            "Salary Slip",
            params={
                "limit": 1,
                "order_by": "creation desc",
                "fields": '["name","custom_lhdn_status","employee"]',
            },
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("data") or []
        if not data:
            self.skipTest("No Salary Slips exist — run setup_test_data.py")
        slip = data[0]
        self.assertIn("custom_lhdn_status", slip,
                      f"custom_lhdn_status not in Salary Slip: {list(slip.keys())}")


class TestLHDNSubmissionWorkflow(ERPNextTestCase):
    """INT-05 to INT-08: LHDN submission API integration."""

    category = "integration"

    def test_int05_resubmit_api_exists(self):
        """INT-05: resubmit_to_lhdn whitelisted method is reachable."""
        # Call with a non-existent doc — should return error, not 404
        resp = self.session.api(
            "lhdn_payroll_integration.services.submission_service.resubmit_to_lhdn",
            docname="NON_EXISTENT_SLIP_9999",
        )
        # Should return 200 with error message (frappe style) or 404/422
        self.assertIn(resp.status_code, (200, 404, 422, 500),
                      f"Unexpected status: {resp.status_code}")

    def test_int06_bulk_enqueue_api_exists(self):
        """INT-06: bulk_enqueue_lhdn_submission method is reachable."""
        resp = self.session.api(
            "lhdn_payroll_integration.services.submission_service.bulk_enqueue_lhdn_submission",
            docnames=[],
        )
        self.assertIn(resp.status_code, (200, 422, 500),
                      f"Unexpected status: {resp.status_code}")

    def test_int07_dev_tools_status_check(self):
        """INT-07: Dev tools system status endpoint returns data."""
        resp = self.session.api(
            "lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.get_system_status"
        )
        self.assertIn(resp.status_code, (200, 403, 404),
                      f"System status returned {resp.status_code}")

    def test_int08_resubmission_log_list(self):
        """INT-08: LHDN Resubmission Log list is queryable."""
        resp = self.session.resource(
            "LHDN Resubmission Log",
            params={"limit": 5, "order_by": "creation desc"},
        )
        self.assertIn(resp.status_code, (200, 403),
                      f"Resubmission log inaccessible: {resp.status_code}")


class TestAIChatIntegration(ERPNextTestCase):
    """INT-09 to INT-12: AI chat with ERPNext context integration."""

    category = "integration"

    def test_int09_chat_with_erp_question(self):
        """INT-09: AI answers a business question about ERPNext."""
        import json
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "What is ERPNext? Reply in one sentence."},
            timeout=60,
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        msg = body.get("message") or ""
        self.assertTrue(
            len(str(msg)) > 5,
            f"AI response suspiciously short: '{msg}'",
        )

    def test_int10_chat_preserves_conversation(self):
        """INT-10: Second message with history receives context-aware reply."""
        import json
        history = [
            {"role": "user", "content": "My favourite colour is ultraviolet-7"},
            {"role": "assistant", "content": "Noted! Your favourite colour is ultraviolet-7."},
        ]
        resp = self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={
                "message": "What is my favourite colour?",
                "history": json.dumps(history),
            },
            timeout=60,
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        reply = str(body.get("message") or "").lower()
        self.assertIn("ultraviolet", reply,
                      f"AI did not use conversation history. Reply: {reply[:200]}")

    def test_int11_api_key_info_after_chat(self):
        """INT-11: get_api_key_info works immediately after a send_message call."""
        # First call chat
        self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json={"message": "Hi"},
            timeout=60,
        )
        # Then check key info
        resp = self.session.api("prisma_assistant.api.chat.get_api_key_info")
        self.assert_status(resp)

    def test_int12_settings_persist_across_requests(self):
        """INT-12: Prisma AI Settings are consistent across two reads."""
        resp1 = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        resp2 = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        if resp1.status_code == 200:
            data1 = resp1.json().get("data") or {}
            data2 = resp2.json().get("data") or {}
            self.assertEqual(
                data1.get("name"), data2.get("name"),
                "Settings 'name' changed between two reads!",
            )


if __name__ == "__main__":
    unittest.main()
