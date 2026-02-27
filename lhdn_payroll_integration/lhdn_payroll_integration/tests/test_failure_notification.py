"""Tests for LHDN submission failure email notification.

US-022: Add submission failure email notification for HR Manager.

Acceptance criteria:
- _write_response_to_doc() sends frappe.sendmail() to HR Manager users
  when status is set to Invalid
- Email includes: document name, employee name, first 500 chars of error log,
  direct link to document
- New Company field custom_lhdn_failure_email (Data) — if set, overrides
  role lookup
- Email sending errors are swallowed and logged, not re-raised
- Test verifies sendmail called on Invalid status write
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch, call


class TestFailureNotification(FrappeTestCase):
    """Tests for _write_response_to_doc() failure email behaviour."""

    def _make_response(self, accepted=None, rejected=None):
        """Build a mock requests.Response with LHDN-shaped JSON."""
        response = MagicMock()
        response.json.return_value = {
            "acceptedDocuments": accepted or [],
            "rejectedDocuments": rejected or [],
        }
        return response

    def _make_rejection_response(self, docname="SS-001"):
        return self._make_response(
            rejected=[
                {
                    "internalId": docname,
                    "error": {
                        "code": "DR01",
                        "message": "Validation failed",
                        "details": [
                            {
                                "code": "CF001",
                                "message": "Invalid TIN",
                                "target": "supplier/tin",
                            }
                        ],
                    },
                }
            ]
        )

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service.frappe"
    )
    def test_sendmail_called_on_invalid_status(self, mock_frappe):
        """sendmail is called when rejected document sets Invalid status."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service import (
            _write_response_to_doc,
        )

        mock_frappe.db.set_value.return_value = None
        mock_frappe.db.get_value.return_value = {"employee_name": "Ahmad", "company": "_Test Company"}
        mock_frappe.db.sql.return_value = [{"email": "hr@test.com"}]
        mock_frappe.utils.get_url.return_value = "http://localhost:8080/app/salary-slip/SS-001"
        mock_frappe.sendmail.return_value = None

        response = self._make_rejection_response("SS-001")
        _write_response_to_doc("Salary Slip", "SS-001", response)

        mock_frappe.sendmail.assert_called_once()
        call_kwargs = mock_frappe.sendmail.call_args
        self.assertIn("hr@test.com", call_kwargs[1].get("recipients", []))

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service.frappe"
    )
    def test_sendmail_not_called_on_accepted(self, mock_frappe):
        """sendmail is NOT called when document is accepted."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service import (
            _write_response_to_doc,
        )

        mock_frappe.db.set_value.return_value = None
        mock_frappe.sendmail.return_value = None

        response = self._make_response(
            accepted=[{"internalId": "SS-001", "uuid": "uuid-111"}]
        )
        _write_response_to_doc("Salary Slip", "SS-001", response)

        mock_frappe.sendmail.assert_not_called()

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service.frappe"
    )
    def test_company_failure_email_overrides_role_lookup(self, mock_frappe):
        """When custom_lhdn_failure_email is set on Company, it overrides HR Manager lookup."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service import (
            _write_response_to_doc,
        )

        mock_frappe.db.set_value.return_value = None
        mock_frappe.db.get_value.side_effect = [
            {"employee_name": "Ahmad", "company": "Test Corp"},
            "lhdn-alerts@testcorp.com",  # custom_lhdn_failure_email
        ]
        mock_frappe.utils.get_url.return_value = "http://localhost:8080/app/salary-slip/SS-001"
        mock_frappe.sendmail.return_value = None

        response = self._make_rejection_response("SS-001")
        _write_response_to_doc("Salary Slip", "SS-001", response)

        mock_frappe.sendmail.assert_called_once()
        recipients = mock_frappe.sendmail.call_args[1].get("recipients", [])
        self.assertIn("lhdn-alerts@testcorp.com", recipients)
        # SQL role lookup should NOT be called when override email is set
        mock_frappe.db.sql.assert_not_called()

    @patch(
        "lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service.frappe"
    )
    def test_sendmail_error_is_swallowed(self, mock_frappe):
        """Email sending error is caught and logged, not re-raised."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.submission_service import (
            _write_response_to_doc,
        )

        mock_frappe.db.set_value.return_value = None
        mock_frappe.db.get_value.return_value = {"employee_name": "Ahmad", "company": "TC"}
        mock_frappe.db.sql.return_value = [{"email": "hr@test.com"}]
        mock_frappe.utils.get_url.return_value = "http://localhost:8080"
        mock_frappe.sendmail.side_effect = Exception("SMTP error")
        mock_frappe.get_traceback.return_value = "traceback text"
        mock_frappe.log_error.return_value = None

        response = self._make_rejection_response("SS-001")
        # Should not raise
        _write_response_to_doc("Salary Slip", "SS-001", response)

        mock_frappe.log_error.assert_called()


class TestFailureEmailCompanyField(FrappeTestCase):
    """Tests for custom_lhdn_failure_email custom field on Company."""

    def test_custom_lhdn_failure_email_field_exists(self):
        exists = frappe.db.exists(
            "Custom Field", {"dt": "Company", "fieldname": "custom_lhdn_failure_email"}
        )
        self.assertTrue(
            exists, "Custom Field 'custom_lhdn_failure_email' not found on Company"
        )

    def test_custom_lhdn_failure_email_is_data_type(self):
        field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Company", "fieldname": "custom_lhdn_failure_email"},
            "fieldtype",
        )
        self.assertEqual(field, "Data", "custom_lhdn_failure_email should be fieldtype=Data")
