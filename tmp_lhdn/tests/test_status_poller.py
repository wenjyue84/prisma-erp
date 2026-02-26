"""Tests for status polling scheduler — TDD Red Phase (UT-013).

Tests poll_pending_documents() which queries Salary Slip and Expense Claim
for documents with custom_lhdn_status='Submitted', fetches their current
status from the LHDN API using the stored custom_lhdn_uuid, and updates
them to 'Valid' (Status 2) or 'Invalid' (Status 3).

The status_poller module has only a stub implementation — so all tests
will FAIL, confirming the TDD red phase.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call
import json


class TestStatusPoller(FrappeTestCase):
	"""Test status polling scheduler for LHDN document status checks."""

	def _mock_salary_slips(self):
		"""Return a list of mock Salary Slip records with Submitted status."""
		return [
			frappe._dict({
				"name": "SAL-SLP-00001",
				"custom_lhdn_uuid": "UUID-SAL-001",
				"custom_lhdn_status": "Submitted",
			}),
			frappe._dict({
				"name": "SAL-SLP-00002",
				"custom_lhdn_uuid": "UUID-SAL-002",
				"custom_lhdn_status": "Submitted",
			}),
		]

	def _mock_expense_claims(self):
		"""Return a list of mock Expense Claim records with Submitted status."""
		return [
			frappe._dict({
				"name": "EXP-CLAIM-00001",
				"custom_lhdn_uuid": "UUID-EXP-001",
				"custom_lhdn_status": "Submitted",
			}),
		]

	def _mock_status_2_response(self):
		"""Create a mock response with LHDN status 'valid' (Status 2)."""
		resp = MagicMock()
		resp.status_code = 200
		resp.json.return_value = {
			"uuid": "UUID-SAL-001",
			"status": "valid",
			"dateTimeValidated": "2026-02-26T10:00:00Z",
		}
		return resp

	def _mock_status_3_response(self):
		"""Create a mock response with LHDN status 'invalid' (Status 3)."""
		resp = MagicMock()
		resp.status_code = 200
		resp.json.return_value = {
			"uuid": "UUID-SAL-002",
			"status": "invalid",
			"validationResults": {
				"code": "InvalidTIN",
				"message": "TIN validation failed for document",
			},
		}
		return resp

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_queries_salary_slip_with_submitted_status(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""poll_pending_documents queries Salary Slip for status='Submitted' with non-empty UUID."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		mock_frappe.get_all.return_value = []
		mock_get_token.return_value = "test-token"

		poll_pending_documents()

		# Verify frappe.get_all was called for Salary Slip with correct filters
		get_all_calls = mock_frappe.get_all.call_args_list
		salary_slip_call = None
		for c in get_all_calls:
			args = c[0] if c[0] else ()
			kwargs = c[1] if c[1] else {}
			doctype = args[0] if args else kwargs.get("doctype", "")
			if doctype == "Salary Slip":
				salary_slip_call = c
				break

		self.assertIsNotNone(
			salary_slip_call,
			"poll_pending_documents must call frappe.get_all for 'Salary Slip'"
		)

		# Check filters include custom_lhdn_status='Submitted' and custom_lhdn_uuid != ''
		kwargs = salary_slip_call[1] if salary_slip_call[1] else {}
		filters = kwargs.get("filters", {})
		self.assertEqual(
			filters.get("custom_lhdn_status"), "Submitted",
			"Filter must include custom_lhdn_status='Submitted'"
		)
		self.assertIn(
			"custom_lhdn_uuid", filters,
			"Filter must include custom_lhdn_uuid (non-empty check)"
		)

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_queries_expense_claim_with_submitted_status(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""poll_pending_documents queries Expense Claim for status='Submitted' with non-empty UUID."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		mock_frappe.get_all.return_value = []
		mock_get_token.return_value = "test-token"

		poll_pending_documents()

		# Verify frappe.get_all was called for Expense Claim with correct filters
		get_all_calls = mock_frappe.get_all.call_args_list
		expense_claim_call = None
		for c in get_all_calls:
			args = c[0] if c[0] else ()
			kwargs = c[1] if c[1] else {}
			doctype = args[0] if args else kwargs.get("doctype", "")
			if doctype == "Expense Claim":
				expense_claim_call = c
				break

		self.assertIsNotNone(
			expense_claim_call,
			"poll_pending_documents must call frappe.get_all for 'Expense Claim'"
		)

		# Check filters include custom_lhdn_status='Submitted' and custom_lhdn_uuid != ''
		kwargs = expense_claim_call[1] if expense_claim_call[1] else {}
		filters = kwargs.get("filters", {})
		self.assertEqual(
			filters.get("custom_lhdn_status"), "Submitted",
			"Filter must include custom_lhdn_status='Submitted'"
		)
		self.assertIn(
			"custom_lhdn_uuid", filters,
			"Filter must include custom_lhdn_uuid (non-empty check)"
		)

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_status_2_response_sets_valid(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""Status 2 (valid) response sets custom_lhdn_status='Valid' and stores validated datetime."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		# Return one salary slip with Submitted status
		salary_slips = [frappe._dict({
			"name": "SAL-SLP-00001",
			"custom_lhdn_uuid": "UUID-SAL-001",
			"custom_lhdn_status": "Submitted",
		})]
		mock_frappe.get_all.side_effect = [salary_slips, []]  # Salary Slip, Expense Claim
		mock_get_token.return_value = "test-token"

		# Mock GET response with status 'valid'
		mock_requests.get.return_value = self._mock_status_2_response()

		poll_pending_documents()

		# Verify status was set to 'Valid'
		set_value_calls = mock_frappe.db.set_value.call_args_list
		status_set = False
		datetime_set = False
		for c in set_value_calls:
			args = c[0] if c[0] else ()
			if len(args) >= 4:
				if args[0] == "Salary Slip" and args[1] == "SAL-SLP-00001":
					if args[2] == "custom_lhdn_status" and args[3] == "Valid":
						status_set = True
					if args[2] == "custom_lhdn_validated_datetime":
						datetime_set = True

		self.assertTrue(status_set, "custom_lhdn_status should be set to 'Valid' for status 2 response")
		self.assertTrue(datetime_set, "custom_lhdn_validated_datetime should be set for status 2 response")

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_status_3_response_sets_invalid(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""Status 3 (invalid) response sets custom_lhdn_status='Invalid' and populates error log."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		# Return one salary slip with Submitted status
		salary_slips = [frappe._dict({
			"name": "SAL-SLP-00002",
			"custom_lhdn_uuid": "UUID-SAL-002",
			"custom_lhdn_status": "Submitted",
		})]
		mock_frappe.get_all.side_effect = [salary_slips, []]  # Salary Slip, Expense Claim
		mock_get_token.return_value = "test-token"

		# Mock GET response with status 'invalid'
		mock_requests.get.return_value = self._mock_status_3_response()

		poll_pending_documents()

		# Verify status was set to 'Invalid' and error log populated
		set_value_calls = mock_frappe.db.set_value.call_args_list
		status_set = False
		error_logged = False
		for c in set_value_calls:
			args = c[0] if c[0] else ()
			if len(args) >= 4:
				if args[0] == "Salary Slip" and args[1] == "SAL-SLP-00002":
					if args[2] == "custom_lhdn_status" and args[3] == "Invalid":
						status_set = True
					if args[2] == "custom_error_log" and args[3]:
						error_logged = True

		self.assertTrue(status_set, "custom_lhdn_status should be set to 'Invalid' for status 3 response")
		self.assertTrue(error_logged, "custom_error_log should be populated with error details for status 3 response")

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_documents_without_uuid_are_skipped(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""Documents without a custom_lhdn_uuid are not queried against the LHDN API."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		# Return documents — some with UUID, some without
		salary_slips = [
			frappe._dict({
				"name": "SAL-SLP-00001",
				"custom_lhdn_uuid": "UUID-SAL-001",
				"custom_lhdn_status": "Submitted",
			}),
			frappe._dict({
				"name": "SAL-SLP-00003",
				"custom_lhdn_uuid": "",
				"custom_lhdn_status": "Submitted",
			}),
		]
		mock_frappe.get_all.side_effect = [salary_slips, []]
		mock_get_token.return_value = "test-token"
		mock_requests.get.return_value = self._mock_status_2_response()

		poll_pending_documents()

		# requests.get should be called only once (for SAL-SLP-00001)
		# SAL-SLP-00003 has empty UUID and should be skipped
		get_calls = mock_requests.get.call_args_list
		self.assertEqual(
			len(get_calls), 1,
			f"Expected 1 API call (skipping empty UUID doc), got {len(get_calls)}"
		)

		# Verify the call was for the document with a UUID
		url_called = get_calls[0][0][0] if get_calls[0][0] else get_calls[0][1].get("url", "")
		self.assertIn(
			"UUID-SAL-001", url_called,
			"API call should use the UUID from the document with a valid UUID"
		)

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_per_document_error_does_not_abort_batch(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""An error processing one document does not abort the rest of the batch."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		salary_slips = [
			frappe._dict({
				"name": "SAL-SLP-00001",
				"custom_lhdn_uuid": "UUID-SAL-001",
				"custom_lhdn_status": "Submitted",
			}),
			frappe._dict({
				"name": "SAL-SLP-00002",
				"custom_lhdn_uuid": "UUID-SAL-002",
				"custom_lhdn_status": "Submitted",
			}),
		]
		mock_frappe.get_all.side_effect = [salary_slips, []]
		mock_get_token.return_value = "test-token"

		# First call raises an exception, second succeeds
		mock_requests.get.side_effect = [
			Exception("Connection failed for first document"),
			self._mock_status_2_response(),
		]

		# Should NOT raise — errors are caught per document
		poll_pending_documents()

		# requests.get should be called twice (once per document)
		self.assertEqual(
			mock_requests.get.call_count, 2,
			"Both documents should be attempted even if the first one fails"
		)

		# frappe.log_error should be called for the failed document
		mock_frappe.log_error.assert_called()

	@patch("lhdn_payroll_integration.services.status_poller.get_access_token")
	@patch("lhdn_payroll_integration.services.status_poller.requests")
	@patch("lhdn_payroll_integration.services.status_poller.frappe")
	def test_max_100_documents_per_doctype_per_run(
		self, mock_frappe, mock_requests, mock_get_token
	):
		"""Processes max 100 documents per doctype per run to avoid timeouts."""
		from lhdn_payroll_integration.services.status_poller import poll_pending_documents

		mock_frappe.get_all.return_value = []
		mock_get_token.return_value = "test-token"

		poll_pending_documents()

		# Verify frappe.get_all was called with limit_page_length=100 for both doctypes
		get_all_calls = mock_frappe.get_all.call_args_list
		for c in get_all_calls:
			kwargs = c[1] if c[1] else {}
			limit = kwargs.get("limit_page_length", kwargs.get("limit", None))
			self.assertIsNotNone(
				limit,
				"frappe.get_all must specify a limit_page_length parameter"
			)
			self.assertLessEqual(
				limit, 100,
				f"limit_page_length should be <= 100, got {limit}"
			)
