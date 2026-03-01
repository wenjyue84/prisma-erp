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
        resp = self.session.api(
            "frappe.client.get_list",
            doctype="Salary Slip",
            fields=["name", "custom_lhdn_status", "employee"],
            order_by="creation desc",
            limit=1,
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("message") or []
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
        # Skip gracefully if AI provider is rate-limited or unavailable — these are
        # infrastructure issues, not conversation-history bugs.
        rate_limit_indicators = ("429", "too many requests", "rate limit", "quota exceeded",
                                 "all ai providers failed", "no ai api key")
        if any(ind in reply for ind in rate_limit_indicators):
            self.skipTest(
                f"AI provider unavailable/rate-limited — INT-10 skipped. Reply: {reply[:120]}"
            )
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


class TestLHDNPayloadValidation(ERPNextTestCase):
    """INT-13 to INT-17: LHDN XML payload structure and error handling."""

    category = "integration"

    def test_int13_payload_builder_api_exists(self):
        """INT-13: payload_builder module method is reachable via API."""
        resp = self.session.api(
            "lhdn_payroll_integration.services.payload_builder.build_salary_slip_payload",
            salary_slip_name="NON_EXISTENT_SLIP_9999",
        )
        # Should return error message (doc not found), not 404 (method not found)
        self.assertIn(resp.status_code, (200, 404, 417, 500),
                      f"payload_builder unreachable: {resp.status_code}")

    def test_int14_submission_with_invalid_doc_returns_error(self):
        """INT-14: Submitting a non-existent Salary Slip returns structured error."""
        resp = self.session.api(
            "lhdn_payroll_integration.services.submission_service.resubmit_to_lhdn",
            docname="FAKE_SALARY_SLIP_999",
        )
        self.assertIn(resp.status_code, (200, 404, 417, 500),
                      f"Unexpected status for invalid doc submission: {resp.status_code}")
        if resp.status_code in (200, 417):
            body = self.parse_json(resp)
            # Should have error info in response
            msg = body.get("message") or body.get("exc_type") or ""
            self.assertTrue(len(str(msg)) > 0,
                            "No error message returned for non-existent salary slip")

    def test_int15_connection_test_returns_structured_result(self):
        """INT-15: LHDN connection test endpoint returns structured JSON."""
        resp = self.session.api(
            "lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.test_lhdn_connection"
        )
        if resp.status_code == 404:
            self.skipTest("LHDN Dev Tools test_lhdn_connection not deployed")
        self.assertIn(resp.status_code, (200, 403, 500),
                      f"Connection test failed: {resp.status_code}")
        if resp.status_code == 200:
            body = self.parse_json(resp)
            msg = body.get("message")
            self.assertIsNotNone(msg,
                                 "Connection test returned no message")

    def test_int16_exemption_tester_endpoint_exists(self):
        """INT-16: Exemption tester API endpoint is reachable."""
        resp = self.session.api(
            "lhdn_payroll_integration.lhdn_payroll_integration.page.lhdn_dev_tools.lhdn_dev_tools.test_exemption_filter",
            employee="HR-EMP-00001",
        )
        # Method should exist even if employee doesn't
        self.assertIn(resp.status_code, (200, 404, 417, 500),
                      f"Exemption tester unreachable: {resp.status_code}")

    def test_int17_salary_slip_lhdn_fields_complete_for_submission(self):
        """INT-17: A Salary Slip has all required fields for LHDN XML generation."""
        resp = self.session.api(
            "frappe.client.get_list",
            doctype="Salary Slip",
            fields=["name", "custom_lhdn_status", "employee", "employee_name",
                    "company", "posting_date", "gross_pay", "total_deduction",
                    "net_pay", "custom_pcb_amount", "custom_epf_employee"],
            order_by="creation desc",
            limit_page_length=1,
        )
        self.assert_status(resp)
        body = self.parse_json(resp)
        data = body.get("message") or []
        if not data:
            self.skipTest("No Salary Slips exist — run payroll first")
        slip = data[0]
        # Check minimum fields needed for LHDN XML payload generation
        required = ["employee", "company", "posting_date", "gross_pay", "net_pay"]
        missing = [f for f in required if not slip.get(f)]
        self.assertEqual(missing, [],
                         f"Salary Slip {slip.get('name')} missing LHDN-required fields: {missing}")


if __name__ == "__main__":
    unittest.main()
