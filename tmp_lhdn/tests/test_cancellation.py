"""Tests for cancellation hook — 72-hour window check.

TDD RED phase: These tests import handle_salary_slip_cancel from
cancellation_service.  The stub exists but has no real logic, so all
assertions will fail (the function just does `pass`).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

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
		# should be within 72h window → enqueue (not throw)
		handle_salary_slip_cancel(doc, "on_cancel")

		mock_frappe.enqueue.assert_called_once()
		mock_frappe.throw.assert_not_called()
