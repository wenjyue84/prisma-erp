"""Tests for US-175: Employment Contract Stamp Duty Compliance Tracker.

Covers:
- DocType existence and field structure
- Stamp duty exemption logic (≤ RM3,000/month)
- Compliance status logic (30-day window)
- get_pending_stamp_records service function
- send_stamp_duty_alerts runs without error
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service import (
    EXEMPTION_THRESHOLD,
    STAMP_DUTY_AMOUNT,
    STAMP_DUTY_SAS_EFFECTIVE_DATE,
    STAMPING_WINDOW_DAYS,
    _parse_date,
    get_pending_stamp_records,
    send_stamp_duty_alerts,
)


class TestStampDutyConstants(FrappeTestCase):
    """Test statutory constants match legislative requirements."""

    def test_sas_effective_date_is_2026_01_01(self):
        """SAS mandates e-Duti Setem stamping from 1 January 2026."""
        self.assertEqual(STAMP_DUTY_SAS_EFFECTIVE_DATE, date(2026, 1, 1))

    def test_exemption_threshold_is_3000(self):
        """Finance Bill 2025 raised exemption threshold to RM3,000/month."""
        self.assertEqual(EXEMPTION_THRESHOLD, 3000.0)

    def test_stamp_duty_amount_is_10(self):
        """Item 4, First Schedule, Stamp Act 1949: fixed RM10 per employment contract."""
        self.assertEqual(STAMP_DUTY_AMOUNT, 10.0)

    def test_stamping_window_is_30_days(self):
        """Employment contracts must be stamped within 30 days of signing."""
        self.assertEqual(STAMPING_WINDOW_DAYS, 30)


class TestStampDutyDocType(FrappeTestCase):
    """Test that LHDN Contract Stamp Duty DocType exists with correct fields."""

    def test_doctype_exists(self):
        """LHDN Contract Stamp Duty DocType must be registered."""
        self.assertTrue(frappe.db.exists("DocType", "LHDN Contract Stamp Duty"))

    def test_required_fields_present(self):
        """DocType must have all fields needed for stamp duty tracking."""
        meta = frappe.get_meta("LHDN Contract Stamp Duty")
        field_names = [f.fieldname for f in meta.fields]

        required = [
            "employee",
            "employee_name",
            "company",
            "contract_signing_date",
            "gross_monthly_salary",
            "stamp_duty_exempt",
            "eduti_stamp_reference",
            "contract_stamping_date",
            "stamping_deadline",
            "days_overdue",
            "compliance_status",
        ]
        for field in required:
            self.assertIn(field, field_names, f"Missing field: {field}")

    def test_stamp_duty_exempt_is_check_field(self):
        """stamp_duty_exempt must be a Check field (boolean)."""
        meta = frappe.get_meta("LHDN Contract Stamp Duty")
        field = meta.get_field("stamp_duty_exempt")
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, "Check")

    def test_gross_monthly_salary_is_currency_field(self):
        """gross_monthly_salary must be a Currency field."""
        meta = frappe.get_meta("LHDN Contract Stamp Duty")
        field = meta.get_field("gross_monthly_salary")
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, "Currency")

    def test_db_table_exists(self):
        """Physical DB table must have been created by migrate."""
        tables = frappe.db.sql("SHOW TABLES LIKE 'tabLHDN Contract Stamp Duty'", as_list=True)
        self.assertEqual(len(tables), 1, "tabLHDN Contract Stamp Duty table does not exist in DB")


class TestStampDutyExemptionLogic(FrappeTestCase):
    """Test the Finance Bill 2025 exemption threshold logic."""

    def _exemption_applies(self, salary):
        """Helper: apply the same exemption logic as the service."""
        return salary <= EXEMPTION_THRESHOLD

    def test_salary_at_3000_is_exempt(self):
        """Exactly RM3,000/month → exempt (inclusive boundary)."""
        self.assertTrue(self._exemption_applies(3000.0))

    def test_salary_below_3000_is_exempt(self):
        """RM2,999.99/month → exempt."""
        self.assertTrue(self._exemption_applies(2999.99))

    def test_salary_of_1500_is_exempt(self):
        """RM1,500/month → exempt (typical low-wage worker)."""
        self.assertTrue(self._exemption_applies(1500.0))

    def test_salary_above_3000_not_exempt(self):
        """RM3,000.01/month → NOT exempt, must be stamped."""
        self.assertFalse(self._exemption_applies(3000.01))

    def test_salary_of_5000_not_exempt(self):
        """RM5,000/month → NOT exempt."""
        self.assertFalse(self._exemption_applies(5000.0))

    def test_old_threshold_300_would_have_been_too_low(self):
        """Old pre-2026 threshold of RM300 is NOT the exemption threshold."""
        # Finance Bill 2025 raised it from RM300 to RM3,000
        old_threshold = 300.0
        self.assertNotEqual(EXEMPTION_THRESHOLD, old_threshold)


class TestStampDutyComplianceWindow(FrappeTestCase):
    """Test the 30-day stamping window and compliance status calculation."""

    def test_parse_date_from_string(self):
        """_parse_date must convert YYYY-MM-DD string to date object."""
        result = _parse_date("2026-01-15")
        self.assertEqual(result, date(2026, 1, 15))

    def test_parse_date_from_date_object(self):
        """_parse_date must accept a date object and return it unchanged."""
        d = date(2026, 3, 1)
        result = _parse_date(d)
        self.assertEqual(result, d)

    def test_parse_date_none_returns_none(self):
        """_parse_date(None) must return None."""
        result = _parse_date(None)
        self.assertIsNone(result)

    def test_30_day_stamping_window(self):
        """Contract signed on Jan 1 → stamping deadline is Jan 31."""
        signing_date = date(2026, 1, 1)
        deadline = signing_date + timedelta(days=STAMPING_WINDOW_DAYS)
        self.assertEqual(deadline, date(2026, 1, 31))

    def test_get_pending_stamp_records_returns_list(self):
        """get_pending_stamp_records must return a list (may be empty)."""
        result = get_pending_stamp_records()
        self.assertIsInstance(result, list)

    def test_get_pending_stamp_records_structure(self):
        """Each record in get_pending_stamp_records must have required keys."""
        result = get_pending_stamp_records()
        required_keys = [
            "name",
            "employee",
            "employee_name",
            "company",
            "contract_signing_date",
            "gross_monthly_salary",
            "stamp_duty_exempt",
            "eduti_stamp_reference",
            "stamping_deadline",
            "days_overdue",
            "compliance_status",
        ]
        for record in result:
            for key in required_keys:
                self.assertIn(key, record, f"Record missing key: {key}")


class TestStampDutyScheduledAlert(FrappeTestCase):
    """Test the scheduled email alert function."""

    def test_send_stamp_duty_alerts_no_error_when_empty(self):
        """send_stamp_duty_alerts must not raise when there are no pending records."""
        # No records → function should return silently
        try:
            send_stamp_duty_alerts()
        except Exception as e:
            self.fail(f"send_stamp_duty_alerts raised unexpected exception: {e}")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.get_pending_stamp_records")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe")
    def test_send_alert_skips_when_no_pending(self, mock_frappe, mock_get_pending):
        """When get_pending_stamp_records returns empty list, no email is sent."""
        mock_get_pending.return_value = []
        send_stamp_duty_alerts()
        mock_frappe.sendmail.assert_not_called()

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.get_pending_stamp_records")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service.frappe")
    def test_send_alert_groups_by_company(self, mock_frappe, mock_get_pending):
        """send_stamp_duty_alerts groups overdue records by company before emailing."""
        # frappe.get_all returns frappe._dict objects (attribute access); simulate with MagicMock
        mock_user = MagicMock()
        mock_user.email = "hr@test.com"
        mock_user.full_name = "HR Manager"
        mock_frappe.get_all.return_value = [mock_user]
        mock_frappe.get_roles.return_value = ["HR Manager"]
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.sendmail = MagicMock()

        today = date.today()
        overdue_date = today - timedelta(days=40)
        deadline = overdue_date + timedelta(days=30)

        mock_get_pending.return_value = [
            {
                "name": "LHDN-CONT-0001",
                "employee": "EMP-001",
                "employee_name": "Ahmad bin Abdullah",
                "company": "Test Company Sdn Bhd",
                "department": "Operations",
                "contract_signing_date": str(overdue_date),
                "gross_monthly_salary": 5000.0,
                "stamp_duty_exempt": 0,
                "eduti_stamp_reference": "",
                "contract_stamping_date": "",
                "stamping_deadline": str(deadline),
                "days_overdue": 10,
                "compliance_status": "Overdue (10 days)",
            }
        ]
        send_stamp_duty_alerts()
        # Since days_overdue >= 0, the email should be sent
        mock_frappe.sendmail.assert_called_once()
