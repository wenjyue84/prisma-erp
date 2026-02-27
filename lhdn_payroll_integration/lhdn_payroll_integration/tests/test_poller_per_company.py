"""Tests for US-023: per-document company base_url and token in status poller.

Verifies that poll_pending_documents() uses each document's own company to
resolve the API base URL and access token — not a hardcoded default.

Company A documents are polled against Company A's endpoint;
Company B documents are polled against Company B's endpoint.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call


class TestPollerPerDocumentCompany(FrappeTestCase):
    """Verify poll_pending_documents uses doc.company for base_url and token."""

    def _make_doc(self, name, uuid, company):
        return frappe._dict({
            "name": name,
            "custom_lhdn_uuid": uuid,
            "custom_lhdn_status": "Submitted",
            "company": company,
        })

    def _valid_response(self, uuid):
        resp = MagicMock()
        resp.json.return_value = {
            "uuid": uuid,
            "status": "valid",
            "dateTimeValidated": "2026-02-27T10:00:00Z",
        }
        return resp

    @patch("lhdn_payroll_integration.services.status_poller.get_access_token")
    @patch("lhdn_payroll_integration.services.status_poller.requests")
    @patch("lhdn_payroll_integration.services.status_poller.frappe")
    def test_company_a_docs_hit_company_a_endpoint(
        self, mock_frappe, mock_requests, mock_get_token
    ):
        """Company A documents are polled against Company A's sandbox URL."""
        from lhdn_payroll_integration.services.status_poller import poll_pending_documents

        # Two companies with different sandbox URLs
        COMPANY_A = "Company Alpha"
        COMPANY_A_URL = "https://sandbox.company-alpha.example"

        docs = [self._make_doc("SAL-001", "UUID-001", COMPANY_A)]
        mock_frappe.get_all.side_effect = [docs, []]  # Salary Slip, Expense Claim
        mock_get_token.return_value = "token-alpha"
        mock_requests.get.return_value = self._valid_response("UUID-001")

        # Mock _get_base_url behaviour via frappe.get_doc
        company_doc_a = MagicMock()
        company_doc_a.custom_integration_type = "Sandbox"
        company_doc_a.custom_sandbox_url = COMPANY_A_URL
        mock_frappe.get_doc.return_value = company_doc_a

        poll_pending_documents()

        # get_access_token must be called with Company Alpha
        mock_get_token.assert_called_with(COMPANY_A)

        # The HTTP GET URL must contain Company A's sandbox URL
        get_calls = mock_requests.get.call_args_list
        self.assertEqual(len(get_calls), 1)
        url_called = get_calls[0][0][0]
        self.assertIn(
            COMPANY_A_URL,
            url_called,
            f"Expected Company A URL '{COMPANY_A_URL}' in request, got '{url_called}'",
        )

    @patch("lhdn_payroll_integration.services.status_poller.get_access_token")
    @patch("lhdn_payroll_integration.services.status_poller.requests")
    @patch("lhdn_payroll_integration.services.status_poller.frappe")
    def test_company_b_docs_hit_company_b_endpoint(
        self, mock_frappe, mock_requests, mock_get_token
    ):
        """Company B documents are polled against Company B's sandbox URL, not Company A."""
        from lhdn_payroll_integration.services.status_poller import poll_pending_documents

        COMPANY_B = "Company Beta"
        COMPANY_B_URL = "https://sandbox.company-beta.example"

        docs = [self._make_doc("SAL-002", "UUID-002", COMPANY_B)]
        mock_frappe.get_all.side_effect = [docs, []]
        mock_get_token.return_value = "token-beta"
        mock_requests.get.return_value = self._valid_response("UUID-002")

        company_doc_b = MagicMock()
        company_doc_b.custom_integration_type = "Sandbox"
        company_doc_b.custom_sandbox_url = COMPANY_B_URL
        mock_frappe.get_doc.return_value = company_doc_b

        poll_pending_documents()

        mock_get_token.assert_called_with(COMPANY_B)

        get_calls = mock_requests.get.call_args_list
        self.assertEqual(len(get_calls), 1)
        url_called = get_calls[0][0][0]
        self.assertIn(
            COMPANY_B_URL,
            url_called,
            f"Expected Company B URL '{COMPANY_B_URL}' in request, got '{url_called}'",
        )

    @patch("lhdn_payroll_integration.services.status_poller.get_access_token")
    @patch("lhdn_payroll_integration.services.status_poller.requests")
    @patch("lhdn_payroll_integration.services.status_poller.frappe")
    def test_mixed_companies_each_use_own_endpoint(
        self, mock_frappe, mock_requests, mock_get_token
    ):
        """Docs from Company A and Company B each poll against their own company's endpoint."""
        from lhdn_payroll_integration.services.status_poller import poll_pending_documents

        COMPANY_A = "Company Alpha"
        COMPANY_B = "Company Beta"
        COMPANY_A_URL = "https://sandbox.alpha.example"
        COMPANY_B_URL = "https://sandbox.beta.example"

        docs = [
            self._make_doc("SAL-001", "UUID-A", COMPANY_A),
            self._make_doc("SAL-002", "UUID-B", COMPANY_B),
        ]
        mock_frappe.get_all.side_effect = [docs, []]

        # get_access_token returns different token per company
        def token_for_company(company):
            return f"token-{company}"

        mock_get_token.side_effect = token_for_company
        mock_requests.get.return_value = self._valid_response("UUID-A")

        # frappe.get_doc returns different company doc based on company name
        def get_doc_side_effect(doctype, name):
            doc = MagicMock()
            doc.custom_integration_type = "Sandbox"
            if name == COMPANY_A:
                doc.custom_sandbox_url = COMPANY_A_URL
            else:
                doc.custom_sandbox_url = COMPANY_B_URL
            return doc

        mock_frappe.get_doc.side_effect = get_doc_side_effect

        poll_pending_documents()

        # Two API calls were made — one per document
        self.assertEqual(
            mock_requests.get.call_count,
            2,
            "Expected exactly 2 API calls — one per document",
        )

        # First call uses Company A URL, second call uses Company B URL
        urls = [c[0][0] for c in mock_requests.get.call_args_list]
        self.assertIn(COMPANY_A_URL, urls[0], "First doc should use Company A URL")
        self.assertIn(COMPANY_B_URL, urls[1], "Second doc should use Company B URL")

        # get_access_token called with correct company each time
        token_calls = [c[0][0] for c in mock_get_token.call_args_list]
        self.assertIn(COMPANY_A, token_calls)
        self.assertIn(COMPANY_B, token_calls)

    @patch("lhdn_payroll_integration.services.status_poller.get_access_token")
    @patch("lhdn_payroll_integration.services.status_poller.requests")
    @patch("lhdn_payroll_integration.services.status_poller.frappe")
    def test_base_url_never_hardcoded_empty(
        self, mock_frappe, mock_requests, mock_get_token
    ):
        """base_url is always resolved from doc.company — never a hardcoded empty string."""
        from lhdn_payroll_integration.services.status_poller import poll_pending_documents

        COMPANY = "Arising Packaging"
        SANDBOX_URL = "https://preprod-api.myinvois.hasil.gov.my"

        docs = [self._make_doc("SAL-001", "UUID-001", COMPANY)]
        mock_frappe.get_all.side_effect = [docs, []]
        mock_get_token.return_value = "test-token"
        mock_requests.get.return_value = self._valid_response("UUID-001")

        company_doc = MagicMock()
        company_doc.custom_integration_type = "Sandbox"
        company_doc.custom_sandbox_url = SANDBOX_URL
        mock_frappe.get_doc.return_value = company_doc

        poll_pending_documents()

        get_calls = mock_requests.get.call_args_list
        self.assertEqual(len(get_calls), 1)
        url_called = get_calls[0][0][0]

        # URL must not be just "/api/..." (which would result from empty base_url)
        self.assertTrue(
            url_called.startswith("http"),
            f"URL must be absolute (starts with http), got: '{url_called}'",
        )
        self.assertNotIn(
            "//api/",
            url_called,
            "URL should not result from empty base_url concatenation",
        )
