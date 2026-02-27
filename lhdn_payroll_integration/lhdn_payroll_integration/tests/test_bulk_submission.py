"""Tests for bulk LHDN submission — US-037.

Verifies:
- bulk_enqueue_lhdn_submission() sets all docs to Pending and enqueues
- Skips docs already Pending/Submitted/Exempt
- Returns success/failed counts
- Role check: only HR Manager or System Manager can call
"""
from unittest.mock import MagicMock, patch, call

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.submission_service import (
    bulk_enqueue_lhdn_submission,
)


class TestBulkEnqueueLhdnSubmission(FrappeTestCase):
    """Test bulk_enqueue_lhdn_submission() whitelisted method."""

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_enqueues_all_provided_docnames(self, mock_frappe):
        """All provided docnames are set to Pending and enqueued."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.return_value = None  # no existing status

        docnames = ["SAL-SLP-001", "SAL-SLP-002", "SAL-SLP-003"]
        result = bulk_enqueue_lhdn_submission(docnames, "Salary Slip")

        self.assertEqual(result["success"], 3)
        self.assertEqual(result["failed"], 0)

        # Verify each doc was set to Pending
        set_value_calls = mock_frappe.db.set_value.call_args_list
        pending_calls = [
            c for c in set_value_calls
            if c[0][2] == "custom_lhdn_status" and c[0][3] == "Pending"
        ]
        self.assertEqual(len(pending_calls), 3)

        # Verify each doc was enqueued
        self.assertEqual(mock_frappe.enqueue.call_count, 3)

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_skips_already_pending_documents(self, mock_frappe):
        """Documents with Pending status are skipped."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.return_value = "Pending"

        docnames = ["SAL-SLP-001", "SAL-SLP-002"]
        result = bulk_enqueue_lhdn_submission(docnames, "Salary Slip")

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 2)
        mock_frappe.enqueue.assert_not_called()

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_skips_submitted_and_exempt(self, mock_frappe):
        """Documents with Submitted or Exempt status are skipped."""
        mock_frappe.get_roles.return_value = ["System Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.side_effect = ["Submitted", "Exempt", None]

        docnames = ["SAL-SLP-001", "SAL-SLP-002", "SAL-SLP-003"]
        result = bulk_enqueue_lhdn_submission(docnames, "Salary Slip")

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(mock_frappe.enqueue.call_count, 1)

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_returns_error_messages_for_skipped(self, mock_frappe):
        """Error messages include doc name and reason for skip."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.return_value = "Submitted"

        docnames = ["SAL-SLP-001"]
        result = bulk_enqueue_lhdn_submission(docnames, "Salary Slip")

        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("SAL-SLP-001", result["errors"][0])
        self.assertIn("Submitted", result["errors"][0])

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_permission_check_hr_manager(self, mock_frappe):
        """HR Manager role is allowed."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.return_value = None

        result = bulk_enqueue_lhdn_submission(["SAL-SLP-001"], "Salary Slip")
        self.assertEqual(result["success"], 1)

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_permission_denied_without_role(self, mock_frappe):
        """Users without HR Manager or System Manager role are denied."""
        mock_frappe.get_roles.return_value = ["Employee"]
        mock_frappe.PermissionError = PermissionError
        mock_frappe.throw.side_effect = PermissionError(
            "Only HR Manager or System Manager can bulk submit to LHDN."
        )

        with self.assertRaises(PermissionError):
            bulk_enqueue_lhdn_submission(["SAL-SLP-001"], "Salary Slip")

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_parses_json_string_docnames(self, mock_frappe):
        """Accepts JSON string input and parses it."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.return_value = ["SAL-SLP-001", "SAL-SLP-002"]
        mock_frappe.db.get_value.return_value = None

        result = bulk_enqueue_lhdn_submission('["SAL-SLP-001", "SAL-SLP-002"]', "Salary Slip")

        mock_frappe.parse_json.assert_called_once_with('["SAL-SLP-001", "SAL-SLP-002"]')
        self.assertEqual(result["success"], 2)

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_enqueues_expense_claim_doctype(self, mock_frappe):
        """Expense Claim doctype uses the correct process method."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.return_value = None

        result = bulk_enqueue_lhdn_submission(["EXP-001"], "Expense Claim")

        self.assertEqual(result["success"], 1)
        enqueue_call = mock_frappe.enqueue.call_args
        self.assertIn("process_expense_claim", enqueue_call[1]["method"])

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_invalid_doc_enqueue_failure_counted(self, mock_frappe):
        """Exception during enqueue is caught and counted as failure."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x
        mock_frappe.db.get_value.return_value = None
        mock_frappe.db.set_value.side_effect = [None, Exception("DB error"), None]

        result = bulk_enqueue_lhdn_submission(
            ["SAL-SLP-001", "SAL-SLP-002", "SAL-SLP-003"], "Salary Slip"
        )

        # First succeeds, second fails on set_value, third succeeds
        self.assertEqual(result["success"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertTrue(any("DB error" in e for e in result["errors"]))

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    def test_empty_docnames_returns_zero_counts(self, mock_frappe):
        """Empty docnames list returns zero success and zero failed."""
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.parse_json.side_effect = lambda x: x

        result = bulk_enqueue_lhdn_submission([], "Salary Slip")

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["errors"], [])
