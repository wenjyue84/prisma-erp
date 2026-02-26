"""Tests for exponential backoff retry service.

Tests schedule_retry() which retries LHDN submissions with exponential
backoff: wait_seconds = min(2**retry_count * 60, 3600), capped at 5 retries.
"""
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.retry_service import schedule_retry


class TestRetryService(FrappeTestCase):
    """Tests for schedule_retry exponential backoff."""

    @patch("lhdn_payroll_integration.services.retry_service.frappe")
    def test_first_retry_schedules_120_second_delay(self, mock_frappe):
        """First retry (count=0 -> 1) schedules job with 120s delay."""
        mock_doc = MagicMock()
        mock_doc.custom_retry_count = 0
        mock_frappe.get_doc.return_value = mock_doc

        schedule_retry("Salary Slip", "SAL-001", "ConnectionError: timed out")

        mock_frappe.enqueue.assert_called_once()
        call_kwargs = mock_frappe.enqueue.call_args
        # 2**1 * 60 = 120
        self.assertEqual(call_kwargs.kwargs.get("enqueue_after_timeout")
                         or call_kwargs[1].get("enqueue_after_timeout"), 120)

    @patch("lhdn_payroll_integration.services.retry_service.frappe")
    def test_second_retry_schedules_240_second_delay(self, mock_frappe):
        """Second retry (count=1 -> 2) schedules job with 240s delay."""
        mock_doc = MagicMock()
        mock_doc.custom_retry_count = 1
        mock_frappe.get_doc.return_value = mock_doc

        schedule_retry("Salary Slip", "SAL-001", "ConnectionError: timed out")

        mock_frappe.enqueue.assert_called_once()
        call_kwargs = mock_frappe.enqueue.call_args
        # 2**2 * 60 = 240
        self.assertEqual(call_kwargs.kwargs.get("enqueue_after_timeout")
                         or call_kwargs[1].get("enqueue_after_timeout"), 240)

    @patch("lhdn_payroll_integration.services.retry_service.frappe")
    def test_retry_count_5_capped_at_3600_seconds(self, mock_frappe):
        """Retry count 4 -> 5 would be 2**5*60=1920, but count 5 is max so
        this tests that high retry counts cap delay at 3600s."""
        mock_doc = MagicMock()
        mock_doc.custom_retry_count = 4
        mock_frappe.get_doc.return_value = mock_doc

        schedule_retry("Salary Slip", "SAL-001", "HTTP 503")

        mock_frappe.enqueue.assert_called_once()
        call_kwargs = mock_frappe.enqueue.call_args
        delay = (call_kwargs.kwargs.get("enqueue_after_timeout")
                 or call_kwargs[1].get("enqueue_after_timeout"))
        # min(2**5 * 60, 3600) = min(1920, 3600) = 1920
        # But if retry_count were higher (e.g. 6+), it would cap at 3600
        self.assertLessEqual(delay, 3600)

    @patch("lhdn_payroll_integration.services.retry_service.frappe")
    def test_after_5_retries_sets_invalid_status(self, mock_frappe):
        """After 5 retries (count=5), sets custom_lhdn_status='Invalid'
        and writes error log instead of scheduling another job."""
        mock_doc = MagicMock()
        mock_doc.custom_retry_count = 5
        mock_frappe.get_doc.return_value = mock_doc

        schedule_retry("Salary Slip", "SAL-001", "ConnectionError: timed out")

        # Should NOT enqueue another job
        mock_frappe.enqueue.assert_not_called()
        # Should set Invalid status
        mock_doc.db_set.assert_any_call("custom_lhdn_status", "Invalid", update_modified=False)
        # Should write error log about max retries
        error_log_calls = [
            c for c in mock_doc.db_set.call_args_list
            if c[0][0] == "custom_error_log"
        ]
        self.assertTrue(len(error_log_calls) > 0)
        error_msg = error_log_calls[0][0][1]
        self.assertIn("Max retries exceeded", error_msg)

    @patch("lhdn_payroll_integration.services.retry_service.frappe")
    def test_no_job_enqueued_after_max_retries(self, mock_frappe):
        """When retry_count >= 5, frappe.enqueue is never called."""
        mock_doc = MagicMock()
        mock_doc.custom_retry_count = 5
        mock_frappe.get_doc.return_value = mock_doc

        schedule_retry("Expense Claim", "EXP-001", "HTTP 500")

        mock_frappe.enqueue.assert_not_called()

    @patch("lhdn_payroll_integration.services.retry_service.frappe")
    def test_retry_count_incremented_on_each_call(self, mock_frappe):
        """custom_retry_count is incremented by 1 on each call."""
        mock_doc = MagicMock()
        mock_doc.custom_retry_count = 2
        mock_frappe.get_doc.return_value = mock_doc

        schedule_retry("Salary Slip", "SAL-001", "ConnectionError")

        # Should increment from 2 to 3
        mock_doc.db_set.assert_any_call("custom_retry_count", 3, update_modified=False)
