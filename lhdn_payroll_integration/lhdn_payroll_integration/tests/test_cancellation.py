"""Tests for cancellation hook — 72-hour window check and async cancellation job.

TDD RED phase: These tests import handle_salary_slip_cancel from
cancellation_service.  The stub exists but has no real logic, so all
assertions will fail (the function just does `pass`).

TestAsyncCancellationJob — RED phase: These tests call process_lhdn_cancellation
which currently is a stub (just `pass`). Assertions on API calls and status
updates will fail.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

from frappe.tests.utils import FrappeTestCase


class TestCancellationHook(FrappeTestCase):
	"""Tests for handle_salary_slip_cancel and handle_expense_claim_cancel."""

	def _make_doc(self, **kwargs):
		"""Helper to create a mock Salary Slip doc with sensible defaults."""
		doc = MagicMock()
		doc.doctype = kwargs.get("doctype", "Salary Slip")
		doc.name = kwargs.get("name", "SAL-SLP-00001")
		doc.custom_lhdn_status = kwargs.get("custom_lhdn_status", "Valid")
		doc.custom_lhdn_uuid = kwargs.get("custom_lhdn_uuid", "abc-123-uuid")
		doc.custom_lhdn_validated_datetime = kwargs.get(
			"custom_lhdn_validated_datetime", None
		)
		doc.custom_lhdn_submission_datetime = kwargs.get(
			"custom_lhdn_submission_datetime", None
		)
		return doc

	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_exempt_slip_allows_native_cancel(self, mock_frappe):
		"""Cancelling a Salary Slip with custom_lhdn_status='Exempt' should
		allow native cancel — no LHDN call, no error raised."""
		from lhdn_payroll_integration.services.cancellation_service import (
			handle_salary_slip_cancel,
		)

		doc = self._make_doc(custom_lhdn_status="Exempt")
		# Should NOT raise any exception
		handle_salary_slip_cancel(doc, "on_cancel")

		# frappe.enqueue should NOT be called (no LHDN cancellation needed)
		mock_frappe.enqueue.assert_not_called()
		# frappe.throw should NOT be called
		mock_frappe.throw.assert_not_called()

	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_within_72h_enqueues_cancellation_job(self, mock_frappe):
		"""Cancelling a Salary Slip validated 10 hours ago should enqueue
		an async cancellation job (within 72h window)."""
		from lhdn_payroll_integration.services.cancellation_service import (
			handle_salary_slip_cancel,
		)

		now = datetime(2026, 3, 1, 12, 0, 0)
		validated_10h_ago = now - timedelta(hours=10)

		mock_frappe.utils.now_datetime.return_value = now

		doc = self._make_doc(
			custom_lhdn_status="Valid",
			custom_lhdn_validated_datetime=validated_10h_ago,
		)

		handle_salary_slip_cancel(doc, "on_cancel")

		# Should enqueue a cancellation job
		mock_frappe.enqueue.assert_called_once()
		call_kwargs = mock_frappe.enqueue.call_args
		self.assertTrue(
			call_kwargs.kwargs.get("enqueue_after_commit", False)
			or (len(call_kwargs.args) > 0 and call_kwargs.kwargs.get("enqueue_after_commit", False)),
			"enqueue should use enqueue_after_commit=True",
		)

	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_past_72h_raises_validation_error(self, mock_frappe):
		"""Cancelling a Salary Slip validated 96 hours ago should raise
		frappe.ValidationError."""
		from lhdn_payroll_integration.services.cancellation_service import (
			handle_salary_slip_cancel,
		)

		import frappe as real_frappe

		mock_frappe.ValidationError = real_frappe.ValidationError
		mock_frappe.throw.side_effect = real_frappe.ValidationError

		now = datetime(2026, 3, 5, 12, 0, 0)
		validated_96h_ago = now - timedelta(hours=96)

		mock_frappe.utils.now_datetime.return_value = now

		doc = self._make_doc(
			custom_lhdn_status="Valid",
			custom_lhdn_validated_datetime=validated_96h_ago,
		)

		with self.assertRaises(real_frappe.ValidationError):
			handle_salary_slip_cancel(doc, "on_cancel")

	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_error_message_mentions_credit_note_and_72_hours(self, mock_frappe):
		"""The ValidationError message should mention 'Credit Note' and
		'72 hours' to guide the user."""
		from lhdn_payroll_integration.services.cancellation_service import (
			handle_salary_slip_cancel,
		)

		import frappe as real_frappe

		mock_frappe.ValidationError = real_frappe.ValidationError

		now = datetime(2026, 3, 5, 12, 0, 0)
		validated_96h_ago = now - timedelta(hours=96)

		mock_frappe.utils.now_datetime.return_value = now

		doc = self._make_doc(
			custom_lhdn_status="Valid",
			custom_lhdn_validated_datetime=validated_96h_ago,
		)

		# Capture what message was passed to frappe.throw
		thrown_msg = None

		def capture_throw(msg, *args, **kwargs):
			nonlocal thrown_msg
			thrown_msg = msg
			raise real_frappe.ValidationError(msg)

		mock_frappe.throw.side_effect = capture_throw

		try:
			handle_salary_slip_cancel(doc, "on_cancel")
		except real_frappe.ValidationError:
			pass

		self.assertIsNotNone(thrown_msg, "frappe.throw should have been called")
		self.assertIn("Credit Note", thrown_msg)
		self.assertIn("72 hours", thrown_msg)

	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_uses_validated_datetime_if_set_else_submission_datetime(self, mock_frappe):
		"""Reference time should prefer custom_lhdn_validated_datetime,
		falling back to custom_lhdn_submission_datetime."""
		from lhdn_payroll_integration.services.cancellation_service import (
			handle_salary_slip_cancel,
		)

		import frappe as real_frappe

		mock_frappe.ValidationError = real_frappe.ValidationError
		mock_frappe.throw.side_effect = real_frappe.ValidationError

		now = datetime(2026, 3, 5, 12, 0, 0)
		# submission_datetime is 10h ago (within window)
		# validated_datetime is None
		submission_10h_ago = now - timedelta(hours=10)

		mock_frappe.utils.now_datetime.return_value = now

		doc = self._make_doc(
			custom_lhdn_status="Submitted",
			custom_lhdn_validated_datetime=None,
			custom_lhdn_submission_datetime=submission_10h_ago,
		)

		# With submission_datetime 10h ago and no validated_datetime,
		# should be within 72h window -> enqueue (not throw)
		handle_salary_slip_cancel(doc, "on_cancel")

		mock_frappe.enqueue.assert_called_once()
		mock_frappe.throw.assert_not_called()


class TestAsyncCancellationJob(FrappeTestCase):
	"""Tests for process_lhdn_cancellation -- async background job.

	TDD RED phase: process_lhdn_cancellation is currently a stub (pass),
	so all assertions will fail.
	"""

	@patch("lhdn_payroll_integration.services.cancellation_service.requests")
	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_on_lhdn_api_success_sets_cancelled_status(self, mock_frappe, mock_requests):
		"""When LHDN API returns 200, custom_lhdn_status should be set to Cancelled."""
		from lhdn_payroll_integration.services.cancellation_service import (
			process_lhdn_cancellation,
		)

		# Setup mock document
		mock_doc = MagicMock()
		mock_doc.doctype = "Salary Slip"
		mock_doc.name = "SAL-SLP-00001"
		mock_doc.custom_lhdn_status = "Valid"
		mock_frappe.get_doc.return_value = mock_doc

		# Setup mock company settings for API credentials
		mock_company_doc = MagicMock()
		mock_company_doc.custom_client_id = "test-client-id"
		mock_company_doc.custom_client_secret = "test-client-secret"
		mock_company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
		mock_company_doc.custom_integration_type = "Sandbox"

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Salary Slip":
				return mock_doc
			if doctype == "Company":
				return mock_company_doc
			return MagicMock()

		mock_frappe.get_doc.side_effect = get_doc_side_effect

		# Setup successful API response
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"status": "cancelled"}
		mock_requests.put.return_value = mock_response

		# Execute
		process_lhdn_cancellation(
			doctype="Salary Slip",
			docname="SAL-SLP-00001",
			uuid="abc-123-uuid",
		)

		# Assert status was set to Cancelled
		mock_doc.db_set.assert_any_call("custom_lhdn_status", "Cancelled", update_modified=False)

	@patch("lhdn_payroll_integration.services.cancellation_service.requests")
	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_on_lhdn_api_success_cancels_frappe_document(self, mock_frappe, mock_requests):
		"""When LHDN API returns 200, the Frappe document cancel() should be called."""
		from lhdn_payroll_integration.services.cancellation_service import (
			process_lhdn_cancellation,
		)

		# Setup mock document
		mock_doc = MagicMock()
		mock_doc.doctype = "Salary Slip"
		mock_doc.name = "SAL-SLP-00001"
		mock_doc.custom_lhdn_status = "Valid"
		mock_frappe.get_doc.return_value = mock_doc

		# Setup mock company settings
		mock_company_doc = MagicMock()
		mock_company_doc.custom_client_id = "test-client-id"
		mock_company_doc.custom_client_secret = "test-client-secret"
		mock_company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
		mock_company_doc.custom_integration_type = "Sandbox"

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Salary Slip":
				return mock_doc
			if doctype == "Company":
				return mock_company_doc
			return MagicMock()

		mock_frappe.get_doc.side_effect = get_doc_side_effect

		# Setup successful API response
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"status": "cancelled"}
		mock_requests.put.return_value = mock_response

		# Execute
		process_lhdn_cancellation(
			doctype="Salary Slip",
			docname="SAL-SLP-00001",
			uuid="abc-123-uuid",
		)

		# Assert cancel was called on the document
		mock_doc.cancel.assert_called_once()

	@patch("lhdn_payroll_integration.services.cancellation_service.requests")
	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_on_lhdn_api_error_status_remains_unchanged(self, mock_frappe, mock_requests):
		"""When LHDN API returns 400, custom_lhdn_status should NOT change."""
		from lhdn_payroll_integration.services.cancellation_service import (
			process_lhdn_cancellation,
		)

		# Setup mock document
		mock_doc = MagicMock()
		mock_doc.doctype = "Salary Slip"
		mock_doc.name = "SAL-SLP-00001"
		mock_doc.custom_lhdn_status = "Valid"
		mock_frappe.get_doc.return_value = mock_doc

		# Setup mock company settings
		mock_company_doc = MagicMock()
		mock_company_doc.custom_client_id = "test-client-id"
		mock_company_doc.custom_client_secret = "test-client-secret"
		mock_company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
		mock_company_doc.custom_integration_type = "Sandbox"

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Salary Slip":
				return mock_doc
			if doctype == "Company":
				return mock_company_doc
			return MagicMock()

		mock_frappe.get_doc.side_effect = get_doc_side_effect

		# Setup failed API response
		mock_response = MagicMock()
		mock_response.status_code = 400
		mock_response.text = "Bad Request: Invalid document UUID"
		mock_response.json.return_value = {"error": "Invalid UUID"}
		mock_requests.put.return_value = mock_response

		# Execute
		process_lhdn_cancellation(
			doctype="Salary Slip",
			docname="SAL-SLP-00001",
			uuid="abc-123-uuid",
		)

		# Assert custom_lhdn_status was NOT set to Cancelled
		cancelled_calls = [
			c for c in mock_doc.db_set.call_args_list
			if len(c.args) >= 2 and c.args[0] == "custom_lhdn_status" and c.args[1] == "Cancelled"
		]
		self.assertEqual(
			len(cancelled_calls), 0,
			"custom_lhdn_status should NOT be set to Cancelled on API error",
		)

	@patch("lhdn_payroll_integration.services.cancellation_service.requests")
	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_on_lhdn_api_error_frappe_doc_not_cancelled(self, mock_frappe, mock_requests):
		"""When LHDN API returns 400, the Frappe document should NOT be cancelled."""
		from lhdn_payroll_integration.services.cancellation_service import (
			process_lhdn_cancellation,
		)

		# Setup mock document
		mock_doc = MagicMock()
		mock_doc.doctype = "Salary Slip"
		mock_doc.name = "SAL-SLP-00001"
		mock_doc.custom_lhdn_status = "Valid"
		mock_frappe.get_doc.return_value = mock_doc

		# Setup mock company settings
		mock_company_doc = MagicMock()
		mock_company_doc.custom_client_id = "test-client-id"
		mock_company_doc.custom_client_secret = "test-client-secret"
		mock_company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
		mock_company_doc.custom_integration_type = "Sandbox"

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Salary Slip":
				return mock_doc
			if doctype == "Company":
				return mock_company_doc
			return MagicMock()

		mock_frappe.get_doc.side_effect = get_doc_side_effect

		# Setup failed API response
		mock_response = MagicMock()
		mock_response.status_code = 400
		mock_response.text = "Bad Request"
		mock_requests.put.return_value = mock_response

		# Execute
		process_lhdn_cancellation(
			doctype="Salary Slip",
			docname="SAL-SLP-00001",
			uuid="abc-123-uuid",
		)

		# Assert cancel was NOT called on the document
		mock_doc.cancel.assert_not_called()

	@patch("lhdn_payroll_integration.services.cancellation_service.requests")
	@patch("lhdn_payroll_integration.services.cancellation_service.frappe")
	def test_on_lhdn_api_error_writes_error_to_log(self, mock_frappe, mock_requests):
		"""When LHDN API returns 400, the error should be logged via frappe.log_error."""
		from lhdn_payroll_integration.services.cancellation_service import (
			process_lhdn_cancellation,
		)

		# Setup mock document
		mock_doc = MagicMock()
		mock_doc.doctype = "Salary Slip"
		mock_doc.name = "SAL-SLP-00001"
		mock_doc.custom_lhdn_status = "Valid"
		mock_frappe.get_doc.return_value = mock_doc

		# Setup mock company settings
		mock_company_doc = MagicMock()
		mock_company_doc.custom_client_id = "test-client-id"
		mock_company_doc.custom_client_secret = "test-client-secret"
		mock_company_doc.custom_sandbox_url = "https://preprod-api.myinvois.hasil.gov.my"
		mock_company_doc.custom_integration_type = "Sandbox"

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Salary Slip":
				return mock_doc
			if doctype == "Company":
				return mock_company_doc
			return MagicMock()

		mock_frappe.get_doc.side_effect = get_doc_side_effect

		# Setup failed API response
		mock_response = MagicMock()
		mock_response.status_code = 400
		mock_response.text = "Bad Request: Invalid document UUID"
		mock_requests.put.return_value = mock_response

		# Execute
		process_lhdn_cancellation(
			doctype="Salary Slip",
			docname="SAL-SLP-00001",
			uuid="abc-123-uuid",
		)

		# Assert error was logged
		mock_frappe.log_error.assert_called_once()
		log_call = mock_frappe.log_error.call_args
		# The log should contain the error details
		log_str = str(log_call)
		self.assertTrue(
			"400" in log_str or "Bad Request" in log_str or "cancellation" in log_str.lower(),
			f"frappe.log_error should mention the API error. Got: {log_str}",
		)
