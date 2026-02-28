"""
Tests for US-092: LHDN MyInvois Webhook Callback Handler

Covers:
- _verify_signature(): valid HMAC-SHA256 → True; wrong sig → False; empty sig → False
- receive_status_callback(): valid callback → document status updated + 200
- receive_status_callback(): invalid signature → 401 rejected
- receive_status_callback(): missing webhook secret → 401
- receive_status_callback(): bad JSON → 400
- receive_status_callback(): missing document_id or status → 400
- _update_document_status(): updates Salary Slip by UUID; falls back to Expense Claim
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.api.lhdn_webhook import (
    _verify_signature,
    _update_document_status,
    receive_status_callback,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_sig(body: str, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest matching _verify_signature logic."""
    return hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# _verify_signature
# ---------------------------------------------------------------------------

class TestVerifySignature(FrappeTestCase):
    """Unit tests for _verify_signature()."""

    def test_valid_signature_returns_true(self):
        body = '{"document_id": "uuid-123", "status": "Valid"}'
        secret = "my-secret"
        sig = _make_sig(body, secret)
        self.assertTrue(_verify_signature(body, secret, sig))

    def test_wrong_signature_returns_false(self):
        body = '{"document_id": "uuid-123", "status": "Valid"}'
        self.assertFalse(_verify_signature(body, "my-secret", "deadbeef"))

    def test_empty_signature_returns_false(self):
        body = '{"document_id": "uuid-123", "status": "Valid"}'
        self.assertFalse(_verify_signature(body, "my-secret", ""))

    def test_different_secret_returns_false(self):
        body = '{"document_id": "uuid-123"}'
        sig = _make_sig(body, "correct-secret")
        self.assertFalse(_verify_signature(body, "wrong-secret", sig))

    def test_tampered_body_returns_false(self):
        original = '{"document_id": "uuid-123"}'
        secret = "s3cr3t"
        sig = _make_sig(original, secret)
        tampered = '{"document_id": "uuid-HACKED"}'
        self.assertFalse(_verify_signature(tampered, secret, sig))


# ---------------------------------------------------------------------------
# _update_document_status
# ---------------------------------------------------------------------------

class TestUpdateDocumentStatus(FrappeTestCase):
    """Unit tests for _update_document_status()."""

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.commit")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.set_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    def test_updates_salary_slip_when_found(self, mock_get_value, mock_set_value, mock_commit):
        mock_get_value.side_effect = lambda dt, filters, field: "SS-001" if dt == "Salary Slip" else None

        _update_document_status("uuid-abc", "Valid")

        mock_set_value.assert_called_once_with(
            "Salary Slip", "SS-001", "custom_lhdn_status", "Submitted"
        )
        mock_commit.assert_called_once()

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.commit")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.set_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    def test_falls_back_to_expense_claim(self, mock_get_value, mock_set_value, mock_commit):
        mock_get_value.side_effect = lambda dt, filters, field: (
            None if dt == "Salary Slip" else "EXP-001"
        )

        _update_document_status("uuid-xyz", "Invalid")

        mock_set_value.assert_called_once_with(
            "Expense Claim", "EXP-001", "custom_lhdn_status", "Invalid"
        )
        mock_commit.assert_called_once()

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.commit")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.set_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    def test_maps_cancelled_status(self, mock_get_value, mock_set_value, mock_commit):
        mock_get_value.side_effect = lambda dt, filters, field: "SS-002" if dt == "Salary Slip" else None

        _update_document_status("uuid-cancel", "Cancelled")

        mock_set_value.assert_called_once_with(
            "Salary Slip", "SS-002", "custom_lhdn_status", "Cancelled"
        )

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.commit")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.set_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    def test_no_update_when_uuid_not_found(self, mock_get_value, mock_set_value, mock_commit):
        mock_get_value.return_value = None

        _update_document_status("uuid-missing", "Valid")

        mock_set_value.assert_not_called()
        mock_commit.assert_not_called()


# ---------------------------------------------------------------------------
# receive_status_callback
# Patch _read_raw_body and _read_signature_header to avoid LocalProxy issues
# with frappe.request in test context.
# ---------------------------------------------------------------------------

class TestReceiveStatusCallback(FrappeTestCase):
    """Tests for the receive_status_callback() endpoint."""

    @patch("lhdn_payroll_integration.api.lhdn_webhook._update_document_status")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.defaults.get_global_default")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_signature_header")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_raw_body")
    def test_valid_callback_updates_status(
        self, mock_body, mock_sig_hdr, mock_global_default, mock_get_value, mock_update
    ):
        secret = "webhook-secret-123"
        payload = {"company": "ACME Sdn Bhd", "document_id": "uuid-001", "status": "Valid"}
        body = json.dumps(payload)
        sig = _make_sig(body, secret)

        mock_body.return_value = body
        mock_sig_hdr.return_value = sig
        mock_global_default.return_value = "ACME Sdn Bhd"
        mock_get_value.return_value = secret

        result = receive_status_callback()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["document_id"], "uuid-001")
        self.assertEqual(result["updated_status"], "Valid")
        mock_update.assert_called_once_with("uuid-001", "Valid")

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.response", new_callable=dict)
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.defaults.get_global_default")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_signature_header")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_raw_body")
    def test_invalid_signature_returns_401(
        self, mock_body, mock_sig_hdr, mock_global_default, mock_get_value, mock_response
    ):
        secret = "webhook-secret-123"
        payload = {"company": "ACME Sdn Bhd", "document_id": "uuid-001", "status": "Valid"}
        body = json.dumps(payload)

        mock_body.return_value = body
        mock_sig_hdr.return_value = "badsignature"
        mock_global_default.return_value = "ACME Sdn Bhd"
        mock_get_value.return_value = secret

        result = receive_status_callback()

        self.assertEqual(mock_response.get("http_status_code"), 401)
        self.assertIn("Invalid signature", result.get("error", ""))

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.response", new_callable=dict)
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.defaults.get_global_default")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_signature_header")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_raw_body")
    def test_missing_webhook_secret_returns_401(
        self, mock_body, mock_sig_hdr, mock_global_default, mock_get_value, mock_response
    ):
        body = '{"company": "ACME Sdn Bhd", "document_id": "uuid-001", "status": "Valid"}'
        mock_body.return_value = body
        mock_sig_hdr.return_value = "anysig"
        mock_global_default.return_value = "ACME Sdn Bhd"
        mock_get_value.return_value = None  # No secret configured

        result = receive_status_callback()

        self.assertEqual(mock_response.get("http_status_code"), 401)
        self.assertIn("Webhook secret not configured", result.get("error", ""))

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.response", new_callable=dict)
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_signature_header")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_raw_body")
    def test_invalid_json_returns_400(self, mock_body, mock_sig_hdr, mock_response):
        mock_body.return_value = "NOT JSON {{{"
        mock_sig_hdr.return_value = ""

        result = receive_status_callback()

        self.assertEqual(mock_response.get("http_status_code"), 400)
        self.assertIn("Invalid JSON", result.get("error", ""))

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.response", new_callable=dict)
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.defaults.get_global_default")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_signature_header")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_raw_body")
    def test_missing_document_id_returns_400(
        self, mock_body, mock_sig_hdr, mock_global_default, mock_get_value, mock_response
    ):
        secret = "webhook-secret-123"
        # Payload without document_id
        payload = {"company": "ACME Sdn Bhd", "status": "Valid"}
        body = json.dumps(payload)
        sig = _make_sig(body, secret)

        mock_body.return_value = body
        mock_sig_hdr.return_value = sig
        mock_global_default.return_value = "ACME Sdn Bhd"
        mock_get_value.return_value = secret

        result = receive_status_callback()

        self.assertEqual(mock_response.get("http_status_code"), 400)
        self.assertIn("Missing", result.get("error", ""))

    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.response", new_callable=dict)
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.db.get_value")
    @patch("lhdn_payroll_integration.api.lhdn_webhook.frappe.defaults.get_global_default")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_signature_header")
    @patch("lhdn_payroll_integration.api.lhdn_webhook._read_raw_body")
    def test_missing_status_returns_400(
        self, mock_body, mock_sig_hdr, mock_global_default, mock_get_value, mock_response
    ):
        secret = "webhook-secret-123"
        # Payload without status
        payload = {"company": "ACME Sdn Bhd", "document_id": "uuid-001"}
        body = json.dumps(payload)
        sig = _make_sig(body, secret)

        mock_body.return_value = body
        mock_sig_hdr.return_value = sig
        mock_global_default.return_value = "ACME Sdn Bhd"
        mock_get_value.return_value = secret

        result = receive_status_callback()

        self.assertEqual(mock_response.get("http_status_code"), 400)
        self.assertIn("Missing", result.get("error", ""))
