"""Tests for on_submit hooks — TDD Red Phase (UT-008).

Tests enqueue_salary_slip_submission() and enqueue_expense_claim_submission()
from submission_service. The current stub does nothing (pass), so all
assertion-based tests will fail — confirming the TDD red phase.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call


class TestSubmissionHooks(FrappeTestCase):
    """Test on_submit hooks for Salary Slip and Expense Claim."""

    def _make_employee(self, requires_self_billed=0):
        """Create a mock employee with custom_requires_self_billed_invoice flag."""
        emp = MagicMock()
        emp.custom_requires_self_billed_invoice = requires_self_billed
        return emp

    def _make_salary_slip(self, name="SAL-SLP-00001", employee="HR-EMP-00001", net_pay=5000):
        """Create a mock Salary Slip doc."""
        doc = MagicMock()
        doc.name = name
        doc.doctype = "Salary Slip"
        doc.employee = employee
        doc.net_pay = net_pay
        return doc

    def _make_expense_claim(self, name="EXP-CLM-00001", employee="HR-EMP-00001",
                            category="Self-Billed Required"):
        """Create a mock Expense Claim doc."""
        doc = MagicMock()
        doc.name = name
        doc.doctype = "Expense Claim"
        doc.employee = employee
        doc.custom_expense_category = category
        return doc

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=False)
    def test_standard_slip_sets_exempt_status(self, mock_filter, mock_frappe):
        """Submitting a standard employee Salary Slip sets custom_lhdn_status='Exempt' and enqueues NO job."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        doc = self._make_salary_slip()
        enqueue_salary_slip_submission(doc, "on_submit")

        # Should set status to Exempt
        mock_frappe.db.set_value.assert_called_once_with(
            "Salary Slip", doc.name, "custom_lhdn_status", "Exempt"
        )
        # Should NOT enqueue any job
        mock_frappe.enqueue.assert_not_called()

    @patch("lhdn_payroll_integration.services.submission_service.validate_tin_with_lhdn", return_value=(True, None))
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=True)
    def test_contractor_slip_sets_pending_and_enqueues(self, mock_filter, mock_frappe, mock_validate_tin):
        """Submitting a contractor Salary Slip sets custom_lhdn_status='Pending' and enqueues a job."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        doc = self._make_salary_slip(name="SAL-SLP-00002", employee="HR-EMP-00002")
        enqueue_salary_slip_submission(doc, "on_submit")

        # Should set status to Pending
        mock_frappe.db.set_value.assert_any_call(
            "Salary Slip", doc.name, "custom_lhdn_status", "Pending"
        )
        # Should enqueue a job
        mock_frappe.enqueue.assert_called_once()
        enqueue_kwargs = mock_frappe.enqueue.call_args
        self.assertEqual(
            enqueue_kwargs[1].get("method") or enqueue_kwargs[0][0],
            "lhdn_payroll_integration.services.submission_service.process_salary_slip"
        )

    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=False)
    def test_expense_claim_overseas_sets_exempt_status(self, mock_filter, mock_frappe):
        """Submitting an Expense Claim with 'Overseas - Exempt' sets custom_lhdn_status='Exempt'."""
        from lhdn_payroll_integration.services.submission_service import enqueue_expense_claim_submission

        doc = self._make_expense_claim(category="Overseas - Exempt")
        enqueue_expense_claim_submission(doc, "on_submit")

        # Should set status to Exempt
        mock_frappe.db.set_value.assert_called_once_with(
            "Expense Claim", doc.name, "custom_lhdn_status", "Exempt"
        )
        # Should NOT enqueue any job
        mock_frappe.enqueue.assert_not_called()

    @patch("lhdn_payroll_integration.services.submission_service.validate_tin_with_lhdn", return_value=(True, None))
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=True)
    def test_enqueue_called_with_after_commit_true(self, mock_filter, mock_frappe, mock_validate_tin):
        """frappe.enqueue is called with enqueue_after_commit=True, queue='short', timeout=300."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        doc = self._make_salary_slip(name="SAL-SLP-00003")
        enqueue_salary_slip_submission(doc, "on_submit")

        mock_frappe.enqueue.assert_called_once()
        enqueue_kwargs = mock_frappe.enqueue.call_args
        # Check critical parameters
        self.assertTrue(enqueue_kwargs[1].get("enqueue_after_commit", False))
        self.assertEqual(enqueue_kwargs[1].get("queue"), "short")
        self.assertEqual(enqueue_kwargs[1].get("timeout"), 300)

    @patch("lhdn_payroll_integration.services.submission_service.validate_tin_with_lhdn", return_value=(True, None))
    @patch("lhdn_payroll_integration.services.submission_service.frappe")
    @patch("lhdn_payroll_integration.services.submission_service.should_submit_to_lhdn", return_value=True)
    def test_document_name_length_validation(self, mock_filter, mock_frappe, mock_validate_tin):
        """Document name longer than 50 chars is gracefully truncated — submission still proceeds."""
        from lhdn_payroll_integration.services.submission_service import enqueue_salary_slip_submission

        long_name = "SAL-SLP-" + "X" * 50  # 58 chars, exceeds 50 limit
        doc = self._make_salary_slip(name=long_name)

        # Should NOT raise — validate_document_name_length now truncates instead of throwing
        enqueue_salary_slip_submission(doc, "on_submit")

        # Should still set Pending status and enqueue the job
        mock_frappe.db.set_value.assert_any_call(
            "Salary Slip", doc.name, "custom_lhdn_status", "Pending"
        )
        mock_frappe.enqueue.assert_called_once()
