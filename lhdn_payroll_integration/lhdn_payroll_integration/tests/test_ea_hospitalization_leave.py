"""
Tests for US-201: Employment Act S.60F(2): Track 60-Day Hospitalization Leave
Quota Separately from Ordinary Sick Leave.

TDD GREEN: bench --site frontend run-tests --module lhdn_payroll_integration.tests.test_ea_hospitalization_leave
"""
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.hospitalization_leave_service import (
    EA_HOSPITALIZATION_DAYS,
    HOSPITALIZATION_LEAVE_TYPE,
    SICK_LEAVE_TYPE,
    validate_hospitalization_leave,
)


class TestHospitalizationLeaveConstants(FrappeTestCase):
    """Verify statutory constants match Employment Act 1955 S.60F(2)."""

    def test_ea_hospitalization_days_is_60(self):
        self.assertEqual(EA_HOSPITALIZATION_DAYS, 60)

    def test_hospitalization_leave_type_name(self):
        self.assertEqual(HOSPITALIZATION_LEAVE_TYPE, "Hospitalization Leave (EA)")

    def test_sick_leave_type_name(self):
        self.assertEqual(SICK_LEAVE_TYPE, "Sick Leave (EA)")


class TestLeaveTypeFixtures(FrappeTestCase):
    """Verify that EA Leave Types exist in the database."""

    def test_sick_leave_ea_exists(self):
        self.assertTrue(
            frappe.db.exists("Leave Type", SICK_LEAVE_TYPE),
            f"Leave Type '{SICK_LEAVE_TYPE}' must exist in database"
        )

    def test_hospitalization_leave_ea_exists(self):
        self.assertTrue(
            frappe.db.exists("Leave Type", HOSPITALIZATION_LEAVE_TYPE),
            f"Leave Type '{HOSPITALIZATION_LEAVE_TYPE}' must exist in database"
        )

    def test_hospitalization_leave_ea_max_days_is_60(self):
        max_days = frappe.db.get_value("Leave Type", HOSPITALIZATION_LEAVE_TYPE, "max_days_allowed")
        self.assertEqual(
            int(max_days or 0), 60,
            "Hospitalization Leave (EA) max_days_allowed must be 60"
        )

    def test_sick_leave_ea_is_not_lwp(self):
        is_lwp = frappe.db.get_value("Leave Type", SICK_LEAVE_TYPE, "is_lwp")
        self.assertEqual(is_lwp, 0, "Sick Leave (EA) must not be Leave Without Pay")

    def test_hospitalization_leave_ea_is_not_lwp(self):
        is_lwp = frappe.db.get_value("Leave Type", HOSPITALIZATION_LEAVE_TYPE, "is_lwp")
        self.assertEqual(is_lwp, 0, "Hospitalization Leave (EA) must not be Leave Without Pay")


class TestCustomFieldsOnLeaveApplication(FrappeTestCase):
    """Verify custom fields exist on Leave Application for hospitalization data."""

    def test_hospitalization_discharge_date_field_exists(self):
        meta = frappe.get_meta("Leave Application")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn(
            "custom_hospitalization_discharge_date",
            field_names,
            "Leave Application must have custom_hospitalization_discharge_date field"
        )

    def test_medical_certificate_type_field_exists(self):
        meta = frappe.get_meta("Leave Application")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn(
            "custom_medical_certificate_type",
            field_names,
            "Leave Application must have custom_medical_certificate_type field"
        )

    def test_medical_certificate_type_has_correct_options(self):
        meta = frappe.get_meta("Leave Application")
        field = next(
            (f for f in meta.fields if f.fieldname == "custom_medical_certificate_type"),
            None
        )
        self.assertIsNotNone(field)
        self.assertIn("Hospitalization Certificate", field.options)
        self.assertIn("Post-Hospitalization Medical Advice", field.options)


class TestValidateHospitalizationLeaveSkipsOtherTypes(FrappeTestCase):
    """Validation is skipped for non-Hospitalization Leave types."""

    def _make_leave_app(self, leave_type, discharge_date=None, cert_type=None):
        doc = MagicMock()
        doc.leave_type = leave_type
        doc.employee = "EMP-TEST-HOSP-001"
        doc.from_date = "2026-01-15"
        doc.to_date = "2026-01-17"
        doc.get = lambda key, default=None: getattr(doc, key, default)
        doc.custom_hospitalization_discharge_date = discharge_date
        doc.custom_medical_certificate_type = cert_type
        return doc

    def test_ordinary_sick_leave_skips_validation(self):
        doc = self._make_leave_app("Sick Leave (EA)")
        # Should not raise any exception
        try:
            validate_hospitalization_leave(doc)
        except Exception as e:
            self.fail(f"validate_hospitalization_leave raised unexpectedly for Sick Leave: {e}")

    def test_casual_leave_skips_validation(self):
        doc = self._make_leave_app("Casual Leave")
        try:
            validate_hospitalization_leave(doc)
        except Exception as e:
            self.fail(f"validate_hospitalization_leave raised unexpectedly for Casual Leave: {e}")


class TestValidateHospitalizationLeaveRequiresFields(FrappeTestCase):
    """Hospitalization Leave requires discharge date and certificate type."""

    def _make_hosp_leave_app(self, discharge_date=None, cert_type=None):
        doc = MagicMock()
        doc.leave_type = HOSPITALIZATION_LEAVE_TYPE
        doc.employee = "EMP-TEST-HOSP-002"
        doc.from_date = "2026-01-15"
        doc.to_date = "2026-01-17"
        doc.custom_hospitalization_discharge_date = discharge_date
        doc.custom_medical_certificate_type = cert_type

        def _get(key, default=None):
            return getattr(doc, key, default)

        doc.get = _get
        return doc

    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.throw")
    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.db.get_value", return_value=None)
    def test_raises_if_discharge_date_missing(self, mock_db, mock_throw):
        doc = self._make_hosp_leave_app(discharge_date=None, cert_type="Hospitalization Certificate")
        mock_throw.side_effect = Exception("discharge date required")
        with self.assertRaises(Exception):
            validate_hospitalization_leave(doc)
        self.assertTrue(mock_throw.called)

    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.throw")
    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.db.get_value", return_value=None)
    def test_raises_if_certificate_type_missing(self, mock_db, mock_throw):
        doc = self._make_hosp_leave_app(discharge_date="2026-01-14", cert_type=None)
        mock_throw.side_effect = Exception("certificate type required")
        with self.assertRaises(Exception):
            validate_hospitalization_leave(doc)
        self.assertTrue(mock_throw.called)

    @patch("lhdn_payroll_integration.services.hospitalization_leave_service._warn_if_balance_zero")
    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.throw")
    def test_passes_when_all_fields_provided(self, mock_throw, mock_warn):
        doc = self._make_hosp_leave_app(
            discharge_date="2026-01-14",
            cert_type="Hospitalization Certificate"
        )
        validate_hospitalization_leave(doc)
        mock_throw.assert_not_called()

    @patch("lhdn_payroll_integration.services.hospitalization_leave_service._warn_if_balance_zero")
    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.throw")
    def test_post_hospitalization_certificate_accepted(self, mock_throw, mock_warn):
        doc = self._make_hosp_leave_app(
            discharge_date="2026-01-14",
            cert_type="Post-Hospitalization Medical Advice"
        )
        validate_hospitalization_leave(doc)
        mock_throw.assert_not_called()


class TestHospitalizationLeaveBalanceWarning(FrappeTestCase):
    """When balance reaches zero, HR should be alerted."""

    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.msgprint")
    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.db.get_value")
    def test_no_alert_when_balance_available(self, mock_db_get, mock_msgprint):
        # Simulate 30 days used out of 60 → 30 remaining
        mock_db_get.side_effect = [
            {"total_leaves_allocated": 60, "total_leaves_encashed": 0},  # allocation
            30.0,  # used days
        ]
        from lhdn_payroll_integration.services.hospitalization_leave_service import _warn_if_balance_zero

        doc = MagicMock()
        doc.employee = "EMP-001"
        doc.from_date = "2026-01-15"
        doc.to_date = "2026-01-17"
        doc.get = lambda key, default=None: getattr(doc, key, default)
        _warn_if_balance_zero(doc)
        mock_msgprint.assert_not_called()

    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.msgprint")
    @patch("lhdn_payroll_integration.services.hospitalization_leave_service.frappe.db.get_value")
    def test_alert_when_balance_exhausted(self, mock_db_get, mock_msgprint):
        # Simulate 60 days used → 0 remaining
        mock_db_get.side_effect = [
            {"total_leaves_allocated": 60, "total_leaves_encashed": 0},  # allocation
            60.0,  # used days
        ]
        from lhdn_payroll_integration.services.hospitalization_leave_service import _warn_if_balance_zero

        doc = MagicMock()
        doc.employee = "EMP-001"
        doc.from_date = "2026-01-15"
        doc.to_date = "2026-01-17"
        doc.get = lambda key, default=None: getattr(doc, key, default)
        _warn_if_balance_zero(doc)
        self.assertTrue(mock_msgprint.called, "msgprint should be called when balance is zero")
        call_args = mock_msgprint.call_args
        self.assertIn("Exhausted", str(call_args) + str(mock_msgprint.call_args_list))
