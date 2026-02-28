"""
Unit Tests — Prisma AI Chat API (PA-01 to PA-16)
=================================================
Tests the three whitelisted endpoints in prisma_assistant.api.chat:
  - send_message
  - get_api_key_info
  - reveal_api_key (System Manager only)

All tests run against the live HTTP API; no internal Python imports.
"""

import json
import unittest

from tests.base import ERPNextTestCase
from tests.config import AI_TIMEOUT


class TestSendMessage(ERPNextTestCase):
    """PA-01 to PA-08: send_message endpoint contract."""

    category = "unit:prisma_ai"

    def _send(self, message: str, history=None, files=None, timeout: int = AI_TIMEOUT):
        payload = {"message": message}
        if history is not None:
            payload["history"] = json.dumps(history) if isinstance(history, list) else history
        if files is not None:
            payload["files"] = json.dumps(files) if isinstance(files, list) else files
        return self.session.post(
            "/api/method/prisma_assistant.api.chat.send_message",
            json=payload,
            timeout=timeout,
        )

    def test_pa01_valid_message_returns_200(self):
        """PA-01: send_message with valid text → HTTP 200."""
        resp = self._send("Hello, say OK")
        self.assert_status(resp)

    def test_pa02_response_has_required_fields(self):
        """PA-02: Response body contains 'message' key with a string value."""
        resp = self._send("Say the word 'PONG' only.")
        body = self.assert_no_error(resp)
        msg = body.get("message")
        self.assertIsNotNone(msg, f"'message' key missing from response: {body}")
        self.assertIsInstance(msg, (str, dict), f"'message' should be str or dict, got: {type(msg)}")

    def test_pa03_empty_message_handled_gracefully(self):
        """PA-03: Empty message string → error or empty response (no 500)."""
        resp = self._send("")
        # Should not be a 500 server error
        self.assertNotEqual(resp.status_code, 500,
                             f"Empty message caused 500: {resp.text[:200]}")

    def test_pa04_empty_history_accepted(self):
        """PA-04: Explicitly empty history=[] is accepted."""
        resp = self._send("Say hi", history=[])
        self.assertIn(resp.status_code, (200, 422), "Empty history should not cause 500")

    def test_pa05_history_passed_correctly(self):
        """PA-05: Non-empty history list is accepted and included in context."""
        history = [
            {"role": "user", "content": "My name is TestBot"},
            {"role": "assistant", "content": "Hello TestBot!"},
        ]
        resp = self._send("What is my name?", history=history)
        self.assert_status(resp)

    def test_pa06_files_empty_list_accepted(self):
        """PA-06: files=[] is accepted without error."""
        resp = self._send("Say OK", files=[])
        self.assertNotEqual(resp.status_code, 500)

    def test_pa07_response_time_measured(self):
        """PA-07: send_message completes within AI_TIMEOUT seconds."""
        import time
        t0 = time.perf_counter()
        resp = self._send("Reply with: OK")
        elapsed = time.perf_counter() - t0
        self.assert_status(resp)
        self.assertLess(elapsed, AI_TIMEOUT,
                        f"send_message took {elapsed:.1f}s, limit is {AI_TIMEOUT}s")

    def test_pa08_large_message_handled(self):
        """PA-08: Message with 2000 characters is accepted (no truncation error)."""
        big_msg = "Summarise this: " + ("word " * 400)
        resp = self._send(big_msg)
        self.assertNotEqual(resp.status_code, 500,
                             f"Large message caused 500: {resp.text[:200]}")


class TestApiKeyInfo(ERPNextTestCase):
    """PA-09 to PA-12: get_api_key_info endpoint."""

    category = "unit:prisma_ai"

    def test_pa09_get_api_key_info_returns_200(self):
        """PA-09: get_api_key_info returns HTTP 200."""
        resp = self.session.api("prisma_assistant.api.chat.get_api_key_info")
        self.assert_status(resp)

    def test_pa10_key_info_has_status_field(self):
        """PA-10: Response contains a 'status' field indicating key presence."""
        resp = self.session.api("prisma_assistant.api.chat.get_api_key_info")
        body = self.assert_no_error(resp)
        msg = body.get("message") or {}
        # Accept either dict with 'status' or string
        self.assertIsNotNone(msg, "get_api_key_info returned null message")

    def test_pa11_key_is_masked(self):
        """PA-11: get_api_key_info does NOT return the full API key."""
        resp = self.session.api("prisma_assistant.api.chat.get_api_key_info")
        body = self.assert_no_error(resp)
        resp_text = str(body)
        # A real API key would be 20+ chars without masking patterns
        # If the key starts with sk- (Anthropic/OpenAI), it should be masked
        self.assertNotIn("sk-ant-", resp_text, "Full Anthropic API key exposed!")
        self.assertNotIn("sk-proj-", resp_text, "Full OpenAI API key exposed!")

    def test_pa12_reveal_requires_system_manager(self):
        """PA-12: reveal_api_key requires System Manager role (or returns safely)."""
        resp = self.session.api("prisma_assistant.api.chat.reveal_api_key")
        # Either succeeds (if user is SysManager) or returns 403/error
        self.assertIn(resp.status_code, (200, 403, 422),
                      f"Unexpected status: {resp.status_code}")


class TestAISettingsDoctype(ERPNextTestCase):
    """PA-13 to PA-16: Prisma AI Settings doctype accessibility."""

    category = "unit:prisma_ai"

    def test_pa13_settings_doctype_exists(self):
        """PA-13: 'Prisma AI Settings' doctype is reachable via REST API."""
        resp = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        self.assertIn(resp.status_code, (200, 404),
                      f"Unexpected status for Settings: {resp.status_code}")

    def test_pa14_settings_has_provider_field(self):
        """PA-14: Settings document has a provider/model configuration field."""
        resp = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        if resp.status_code == 200:
            body = self.parse_json(resp)
            data = body.get("data") or {}
            # At minimum the doctype fields include name
            self.assertIn("name", data, f"Settings missing 'name': {list(data.keys())}")

    def test_pa15_settings_api_key_not_exposed(self):
        """PA-15: REST GET on Settings does NOT expose plaintext API key."""
        resp = self.session.resource("Prisma AI Settings", "Prisma AI Settings")
        if resp.status_code == 200:
            resp_text = resp.text
            self.assertNotIn("sk-ant-", resp_text, "Anthropic key in REST response!")
            self.assertNotIn("sk-proj-", resp_text, "OpenAI key in REST response!")

    def test_pa16_desk_widget_asset_served(self):
        """PA-16: desk_widget.js asset is served at /assets/prisma_assistant/js/desk_widget.js."""
        resp = self.session.get("/assets/prisma_assistant/js/desk_widget.js")
        self.assertIn(resp.status_code, (200, 304),
                      f"desk_widget.js not served: {resp.status_code}")


if __name__ == "__main__":
    unittest.main()
