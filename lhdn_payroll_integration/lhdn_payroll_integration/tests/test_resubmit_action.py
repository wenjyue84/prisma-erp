"""Tests for resubmit_to_lhdn whitelisted server action.

TDD RED phase: these tests fail because resubmit_to_lhdn does not exist yet
in submission_service.py.
"""
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.submission_service import resubmit_to_lhdn


class TestResubmitPermission(FrappeTestCase):
    """resubmit_to_lhdn must raise PermissionError for non-System-Manager users."""

    def test_raises_permission_error_without_system_manager_role(self):
        """Non-System Manager caller gets PermissionError."""
        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["Employee", "Guest"],
        ):
            with self.assertRaises((frappe.PermissionError, PermissionError)):
                resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")

    def test_no_error_for_system_manager(self):
        """System Manager caller does NOT get PermissionError (may raise other errors)."""
        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["System Manager"],
        ):
            with patch(
                "lhdn_payroll_integration.services.submission_service.frappe.get_doc"
            ) as mock_get_doc:
                mock_doc = MagicMock()
                mock_doc.custom_lhdn_status = "Invalid"
                mock_get_doc.return_value = mock_doc
                with patch(
                    "lhdn_payroll_integration.services.submission_service.frappe.enqueue"
                ):
                    with patch(
                        "lhdn_payroll_integration.services.submission_service.frappe.db"
                    ):
                        # Should not raise PermissionError
                        try:
                            resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")
                        except (frappe.PermissionError, PermissionError):
                            self.fail("PermissionError raised for System Manager — should not happen")
                        except Exception:
                            pass  # Other exceptions are OK in this test


class TestResubmitStatusPrecondition(FrappeTestCase):
    """resubmit_to_lhdn must raise ValidationError if status is not Invalid or Submitted."""

    def _make_doc(self, status):
        doc = MagicMock()
        doc.custom_lhdn_status = status
        return doc

    def test_raises_validation_error_if_status_is_pending(self):
        """Status=Pending should raise ValidationError."""
        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["System Manager"],
        ):
            with patch(
                "lhdn_payroll_integration.services.submission_service.frappe.get_doc",
                return_value=self._make_doc("Pending"),
            ):
                with self.assertRaises((frappe.ValidationError, ValueError)):
                    resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")

    def test_raises_validation_error_if_status_is_valid(self):
        """Status=Valid should raise ValidationError."""
        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["System Manager"],
        ):
            with patch(
                "lhdn_payroll_integration.services.submission_service.frappe.get_doc",
                return_value=self._make_doc("Valid"),
            ):
                with self.assertRaises((frappe.ValidationError, ValueError)):
                    resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")

    def test_no_validation_error_if_status_is_invalid(self):
        """Status=Invalid should NOT raise ValidationError."""
        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["System Manager"],
        ):
            with patch(
                "lhdn_payroll_integration.services.submission_service.frappe.get_doc",
                return_value=self._make_doc("Invalid"),
            ):
                with patch(
                    "lhdn_payroll_integration.services.submission_service.frappe.enqueue"
                ):
                    with patch(
                        "lhdn_payroll_integration.services.submission_service.frappe.db"
                    ):
                        try:
                            resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")
                        except (frappe.ValidationError, ValueError):
                            self.fail("ValidationError raised for status=Invalid — should not happen")
                        except Exception:
                            pass


class TestResubmitStatusReset(FrappeTestCase):
    """resubmit_to_lhdn must reset status to Pending and call frappe.enqueue."""

    def test_sets_status_to_pending_and_enqueues(self):
        """On valid invocation: sets custom_lhdn_status=Pending and calls frappe.enqueue."""
        mock_salary_slip = MagicMock()
        mock_salary_slip.custom_lhdn_status = "Invalid"

        def fake_get_doc(data_or_doctype, name=None):
            # Intercept LHDN Resubmission Log creation — return a simple mock
            if isinstance(data_or_doctype, dict) and data_or_doctype.get("doctype") == "LHDN Resubmission Log":
                log = MagicMock()
                log.insert = MagicMock()
                return log
            # Intercept Salary Slip fetch
            if data_or_doctype == "Salary Slip":
                return mock_salary_slip
            return mock_salary_slip

        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["System Manager"],
        ):
            with patch(
                "lhdn_payroll_integration.services.submission_service.frappe.get_doc",
                side_effect=fake_get_doc,
            ):
                with patch(
                    "lhdn_payroll_integration.services.submission_service.frappe.enqueue"
                ) as mock_enqueue:
                    with patch(
                        "lhdn_payroll_integration.services.submission_service.frappe.db.set_value"
                    ) as mock_set_value:
                        with patch(
                            "lhdn_payroll_integration.services.submission_service.frappe.session",
                            new_callable=MagicMock,
                        ) as mock_session:
                            with patch(
                                "lhdn_payroll_integration.services.submission_service.frappe.utils"
                            ):
                                mock_session.user = "Administrator"
                                resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")

                                # frappe.db.set_value called to reset status to Pending
                                set_value_calls = [
                                    str(call) for call in mock_set_value.call_args_list
                                ]
                                pending_set = any("Pending" in c for c in set_value_calls)
                                self.assertTrue(
                                    pending_set,
                                    f"Expected db.set_value called with 'Pending' but got: {set_value_calls}",
                                )

                                # frappe.enqueue called once
                                mock_enqueue.assert_called_once()


class TestResubmitAuditLog(FrappeTestCase):
    """US-042: resubmit_to_lhdn() must create an LHDN Resubmission Log entry."""

    def test_audit_log_entry_created_on_resubmission(self):
        """A LHDN Resubmission Log doc is inserted when resubmit_to_lhdn() is called."""
        mock_doc = MagicMock()
        mock_doc.custom_lhdn_status = "Invalid"

        created_logs = []

        def fake_get_doc(data_or_doctype, name=None):
            if isinstance(data_or_doctype, dict) and data_or_doctype.get("doctype") == "LHDN Resubmission Log":
                log = MagicMock()
                log.doctype = "LHDN Resubmission Log"
                log.user = data_or_doctype.get("user")
                log.reference_doctype = data_or_doctype.get("reference_doctype")
                log.docname = data_or_doctype.get("docname")
                log.insert = MagicMock(side_effect=lambda **kwargs: created_logs.append(log))
                return log
            return mock_doc

        with patch(
            "lhdn_payroll_integration.services.submission_service.frappe.get_roles",
            return_value=["System Manager"],
        ):
            with patch(
                "lhdn_payroll_integration.services.submission_service.frappe.get_doc",
                side_effect=fake_get_doc,
            ):
                with patch(
                    "lhdn_payroll_integration.services.submission_service.frappe.enqueue"
                ):
                    with patch(
                        "lhdn_payroll_integration.services.submission_service.frappe.db"
                    ):
                        with patch(
                            "lhdn_payroll_integration.services.submission_service.frappe.session",
                            new_callable=MagicMock,
                        ) as mock_session:
                            with patch(
                                "lhdn_payroll_integration.services.submission_service.frappe.utils"
                            ):
                                mock_session.user = "Administrator"
                                resubmit_to_lhdn("Sal Slip/Test/00001", "Salary Slip")

        self.assertEqual(len(created_logs), 1, "Exactly one LHDN Resubmission Log must be created")
        log = created_logs[0]
        self.assertEqual(log.reference_doctype, "Salary Slip",
            "Log reference_doctype must match the resubmitted doctype")
        self.assertEqual(log.docname, "Sal Slip/Test/00001",
            "Log docname must match the resubmitted document name")
