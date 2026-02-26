"""Tests for LHDN error log parsing.

Tests _format_error_log (status_poller) and _format_rejection_errors
(submission_service) — both parse LHDN JSON error responses into
human-readable text for custom_error_log.
"""
import json

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.status_poller import _format_error_log
from lhdn_payroll_integration.services.submission_service import _format_rejection_errors


class TestErrorLogParser(FrappeTestCase):
    """Tests for LHDN error response formatting functions."""

    def test_format_error_log_with_two_errors_returns_two_lines(self):
        """_format_error_log with 2 validation errors returns 2 [CODE] lines."""
        response = {
            "status": "invalid",
            "validationResults": {
                "status": "invalid",
                "validationSteps": [
                    {
                        "status": "invalid",
                        "name": "step1",
                        "error": {
                            "propertyName": "SupplierTIN",
                            "errorCode": "CF204",
                            "error": "Invalid TIN",
                            "innerError": [],
                        },
                    },
                    {
                        "status": "invalid",
                        "name": "step2",
                        "error": {
                            "propertyName": "InvoicePeriod",
                            "errorCode": "CF301",
                            "error": "Missing invoice period",
                            "innerError": [],
                        },
                    },
                ],
            },
        }
        result = _format_error_log(response)
        # Header line should say 2 error(s)
        self.assertIn("2 error(s)", result)
        # Exactly 2 formatted error lines with [CODE] pattern
        lines = [l for l in result.split("\n") if l.startswith("[")]
        self.assertEqual(len(lines), 2)
        self.assertIn("[CF204]", lines[0])
        self.assertIn("[CF301]", lines[1])

    def test_raw_json_appended_after_formatted_lines(self):
        """Raw JSON dump is appended after the separator line."""
        response = {
            "status": "invalid",
            "validationResults": {
                "status": "invalid",
                "validationSteps": [
                    {
                        "status": "invalid",
                        "name": "step1",
                        "error": {
                            "propertyName": "SupplierTIN",
                            "errorCode": "CF204",
                            "error": "Invalid TIN",
                            "innerError": [],
                        },
                    },
                ],
            },
        }
        result = _format_error_log(response)
        self.assertIn("---RAW JSON---", result)
        # Everything after the separator should be valid JSON
        raw_section = result.split("---RAW JSON---\n", 1)[1]
        parsed = json.loads(raw_section)
        self.assertEqual(parsed["status"], "invalid")

    def test_empty_errors_array_returns_default_message(self):
        """Empty validationSteps returns a default message."""
        response = {
            "status": "invalid",
            "validationResults": {
                "status": "invalid",
                "validationSteps": [],
            },
        }
        result = _format_error_log(response)
        self.assertIn("LHDN returned Invalid status with no error details", result)

    def test_error_log_on_rejected_slip_contains_readable_text(self):
        """_format_rejection_errors on a 202 rejection returns readable text."""
        rejection_error = {
            "code": "CF204",
            "message": "Document validation failed",
            "details": [
                {
                    "code": "CF204",
                    "message": "Invalid TIN",
                    "target": "SupplierTIN",
                },
            ],
        }
        result = _format_rejection_errors(rejection_error)
        self.assertIn("[CF204]", result)
        self.assertIn("SupplierTIN", result)
        self.assertIn("Invalid TIN", result)
        # Raw JSON appended
        self.assertIn("---RAW JSON---", result)

    def test_error_format_includes_code_and_field_name(self):
        """Each error line follows the format: [CODE] fieldName: message."""
        response = {
            "status": "invalid",
            "validationResults": {
                "status": "invalid",
                "validationSteps": [
                    {
                        "status": "invalid",
                        "name": "step1",
                        "error": {
                            "propertyName": "SupplierTIN",
                            "errorCode": "CF204",
                            "error": "Invalid TIN format (submitted: 'IG123')",
                            "innerError": [],
                        },
                    },
                ],
            },
        }
        result = _format_error_log(response)
        # Should contain the exact format: [CF204] SupplierTIN: Invalid TIN format
        self.assertIn("[CF204] SupplierTIN:", result)
        self.assertIn("Invalid TIN format", result)
