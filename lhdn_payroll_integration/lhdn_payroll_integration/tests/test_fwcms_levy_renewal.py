"""Tests for FWCMS Foreign Worker Annual Levy Renewal Service (US-207).

Covers:
- Sector rate table correctness
- Expiry calculation helpers
- Alert tier classification (90/60/30/14 days + expired)
- Critical escalation logic
- Renewal validation and recording
- Dashboard widget data aggregation
- Alert generation for scheduler
"""

import unittest
from datetime import date
from unittest.mock import patch, MagicMock, call

from lhdn_payroll_integration.services.fwcms_levy_renewal_service import (
    SECTOR_RATES,
    VALID_SECTORS,
    ALERT_TIERS,
    CRITICAL_ALERT_DAYS,
    DEFAULT_RENEWAL_DAYS,
    get_sector_rate,
    get_all_sector_rates,
    get_days_until_expiry,
    is_levy_expired,
    classify_alert_tier,
    needs_critical_escalation,
    validate_renewal_record,
    calculate_next_expiry,
    record_levy_renewal,
    get_noncompliant_workers_summary,
    get_workers_needing_alerts,
)


class TestSectorRateConstants(unittest.TestCase):
    """Verify sector rate table values and structure."""

    def test_manufacturing_rate(self):
        self.assertEqual(SECTOR_RATES["Manufacturing"], 1850)

    def test_construction_rate(self):
        self.assertEqual(SECTOR_RATES["Construction"], 1850)

    def test_services_rate(self):
        self.assertEqual(SECTOR_RATES["Services"], 1850)

    def test_plantation_rate(self):
        self.assertEqual(SECTOR_RATES["Plantation"], 640)

    def test_agriculture_rate(self):
        self.assertEqual(SECTOR_RATES["Agriculture"], 640)

    def test_five_sectors_defined(self):
        self.assertEqual(len(SECTOR_RATES), 5)

    def test_valid_sectors_matches_rate_keys(self):
        self.assertEqual(set(VALID_SECTORS), set(SECTOR_RATES.keys()))

    def test_alert_tiers(self):
        self.assertEqual(ALERT_TIERS, [90, 60, 30])

    def test_critical_alert_days(self):
        self.assertEqual(CRITICAL_ALERT_DAYS, 14)

    def test_default_renewal_days(self):
        self.assertEqual(DEFAULT_RENEWAL_DAYS, 365)


class TestGetSectorRate(unittest.TestCase):
    """Test get_sector_rate() helper."""

    def test_manufacturing(self):
        self.assertEqual(get_sector_rate("Manufacturing"), 1850)

    def test_plantation(self):
        self.assertEqual(get_sector_rate("Plantation"), 640)

    def test_agriculture(self):
        self.assertEqual(get_sector_rate("Agriculture"), 640)

    def test_invalid_sector_raises(self):
        with self.assertRaises(ValueError):
            get_sector_rate("Mining")

    def test_none_sector_raises(self):
        with self.assertRaises(ValueError):
            get_sector_rate(None)

    def test_empty_sector_raises(self):
        with self.assertRaises(ValueError):
            get_sector_rate("")

    def test_get_all_returns_copy(self):
        rates = get_all_sector_rates()
        self.assertEqual(rates, SECTOR_RATES)
        rates["Test"] = 999
        self.assertNotIn("Test", SECTOR_RATES)


class TestGetDaysUntilExpiry(unittest.TestCase):
    """Test get_days_until_expiry() helper."""

    def test_future_expiry(self):
        days = get_days_until_expiry("2026-06-01", "2026-03-01")
        self.assertEqual(days, 92)

    def test_today_expiry(self):
        days = get_days_until_expiry("2026-03-01", "2026-03-01")
        self.assertEqual(days, 0)

    def test_past_expiry(self):
        days = get_days_until_expiry("2026-02-01", "2026-03-01")
        self.assertEqual(days, -28)

    def test_none_expiry_date(self):
        self.assertIsNone(get_days_until_expiry(None, "2026-03-01"))

    def test_date_objects(self):
        days = get_days_until_expiry(date(2026, 4, 1), date(2026, 3, 1))
        self.assertEqual(days, 31)


class TestIsLevyExpired(unittest.TestCase):
    """Test is_levy_expired() helper."""

    def test_past_date_is_expired(self):
        self.assertTrue(is_levy_expired("2026-02-01", "2026-03-01"))

    def test_today_is_not_expired(self):
        self.assertFalse(is_levy_expired("2026-03-01", "2026-03-01"))

    def test_future_date_is_not_expired(self):
        self.assertFalse(is_levy_expired("2026-06-01", "2026-03-01"))

    def test_none_is_not_expired(self):
        self.assertFalse(is_levy_expired(None, "2026-03-01"))


class TestClassifyAlertTier(unittest.TestCase):
    """Test classify_alert_tier() — multi-tier alert classification."""

    def test_expired(self):
        self.assertEqual(
            classify_alert_tier("2026-02-28", "2026-03-01"),
            "expired",
        )

    def test_critical_14_boundary(self):
        # Exactly 14 days out
        self.assertEqual(
            classify_alert_tier("2026-03-15", "2026-03-01"),
            "critical_14",
        )

    def test_critical_14_within(self):
        # 7 days out
        self.assertEqual(
            classify_alert_tier("2026-03-08", "2026-03-01"),
            "critical_14",
        )

    def test_critical_14_today(self):
        # 0 days = expiring today
        self.assertEqual(
            classify_alert_tier("2026-03-01", "2026-03-01"),
            "critical_14",
        )

    def test_alert_30_boundary(self):
        # Exactly 30 days
        self.assertEqual(
            classify_alert_tier("2026-03-31", "2026-03-01"),
            "alert_30",
        )

    def test_alert_30_within(self):
        # 20 days
        self.assertEqual(
            classify_alert_tier("2026-03-21", "2026-03-01"),
            "alert_30",
        )

    def test_alert_60_boundary(self):
        # Exactly 60 days
        self.assertEqual(
            classify_alert_tier("2026-04-30", "2026-03-01"),
            "alert_60",
        )

    def test_alert_60_within(self):
        # 45 days
        self.assertEqual(
            classify_alert_tier("2026-04-15", "2026-03-01"),
            "alert_60",
        )

    def test_alert_90_boundary(self):
        # Exactly 90 days
        self.assertEqual(
            classify_alert_tier("2026-05-30", "2026-03-01"),
            "alert_90",
        )

    def test_alert_90_within(self):
        # 75 days
        self.assertEqual(
            classify_alert_tier("2026-05-15", "2026-03-01"),
            "alert_90",
        )

    def test_no_alert_beyond_90(self):
        # 100 days out
        self.assertIsNone(
            classify_alert_tier("2026-06-09", "2026-03-01")
        )

    def test_none_expiry(self):
        self.assertIsNone(classify_alert_tier(None, "2026-03-01"))

    def test_15_days_is_alert_30(self):
        # 15 days is > 14 (critical) and <= 30 (alert_30)
        self.assertEqual(
            classify_alert_tier("2026-03-16", "2026-03-01"),
            "alert_30",
        )

    def test_31_days_is_alert_60(self):
        # 31 days is > 30 and <= 60
        self.assertEqual(
            classify_alert_tier("2026-04-01", "2026-03-01"),
            "alert_60",
        )

    def test_61_days_is_alert_90(self):
        # 61 days is > 60 and <= 90
        self.assertEqual(
            classify_alert_tier("2026-05-01", "2026-03-01"),
            "alert_90",
        )


class TestNeedsCriticalEscalation(unittest.TestCase):
    """Test needs_critical_escalation() — receipt-aware escalation."""

    def test_critical_no_receipt(self):
        self.assertTrue(
            needs_critical_escalation("2026-03-10", False, "2026-03-01")
        )

    def test_critical_with_receipt(self):
        self.assertFalse(
            needs_critical_escalation("2026-03-10", True, "2026-03-01")
        )

    def test_not_critical_no_receipt(self):
        # 45 days out — not in critical window
        self.assertFalse(
            needs_critical_escalation("2026-04-15", False, "2026-03-01")
        )

    def test_expired_no_receipt(self):
        # Already expired, days <= 14 is true (negative), no receipt
        self.assertTrue(
            needs_critical_escalation("2026-02-28", False, "2026-03-01")
        )

    def test_none_expiry(self):
        self.assertFalse(
            needs_critical_escalation(None, False, "2026-03-01")
        )


class TestValidateRenewalRecord(unittest.TestCase):
    """Test validate_renewal_record() validation logic."""

    def test_valid_record(self):
        errors = validate_renewal_record("2026-03-01", "FWCMS-2026-001", "Manufacturing")
        self.assertEqual(errors, [])

    def test_missing_payment_date(self):
        errors = validate_renewal_record(None, "FWCMS-2026-001", "Manufacturing")
        self.assertIn("Payment date is required", errors)

    def test_missing_receipt_reference(self):
        errors = validate_renewal_record("2026-03-01", "", "Manufacturing")
        self.assertIn("Receipt reference is required", errors)

    def test_none_receipt_reference(self):
        errors = validate_renewal_record("2026-03-01", None, "Manufacturing")
        self.assertIn("Receipt reference is required", errors)

    def test_whitespace_only_receipt(self):
        errors = validate_renewal_record("2026-03-01", "  ", "Manufacturing")
        self.assertIn("Receipt reference is required", errors)

    def test_invalid_sector(self):
        errors = validate_renewal_record("2026-03-01", "FWCMS-001", "Mining")
        self.assertTrue(any("Invalid sector" in e for e in errors))

    def test_none_sector(self):
        errors = validate_renewal_record("2026-03-01", "FWCMS-001", None)
        self.assertTrue(any("Invalid sector" in e for e in errors))

    def test_multiple_errors(self):
        errors = validate_renewal_record(None, "", "Mining")
        self.assertEqual(len(errors), 3)


class TestCalculateNextExpiry(unittest.TestCase):
    """Test calculate_next_expiry() — expiry date calculation."""

    def test_default_365_days(self):
        result = calculate_next_expiry("2026-03-01")
        self.assertEqual(result, date(2027, 3, 1))

    def test_custom_plks_duration(self):
        result = calculate_next_expiry("2026-03-01", plks_duration_days=730)
        self.assertEqual(result, date(2028, 2, 29))  # 2028 is a leap year

    def test_leap_year_handling(self):
        # 2028 is a leap year; 2027-03-01 + 365 = 2028-02-29 (wait, not right)
        # Actually: 2027-03-01 + 365 = 2028-02-29 (2028 is leap)
        result = calculate_next_expiry("2027-03-01")
        self.assertEqual(result, date(2028, 2, 29))

    def test_short_permit(self):
        result = calculate_next_expiry("2026-03-01", plks_duration_days=180)
        self.assertEqual(result, date(2026, 8, 28))


class TestRecordLevyRenewal(unittest.TestCase):
    """Test record_levy_renewal() — full renewal recording."""

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_successful_renewal(self, mock_frappe):
        result = record_levy_renewal(
            employee_id="EMP-001",
            payment_date="2026-03-01",
            receipt_reference="FWCMS-2026-001",
            sector="Manufacturing",
        )
        self.assertEqual(result["employee"], "EMP-001")
        self.assertEqual(result["payment_date"], date(2026, 3, 1))
        self.assertEqual(result["expiry_date"], date(2027, 3, 1))
        self.assertEqual(result["receipt_reference"], "FWCMS-2026-001")
        self.assertEqual(result["sector"], "Manufacturing")
        self.assertEqual(result["rate"], 1850)

        mock_frappe.db.set_value.assert_called_once_with(
            "Employee",
            "EMP-001",
            {
                "custom_fwcms_levy_payment_date": date(2026, 3, 1),
                "custom_fwcms_levy_expiry_date": date(2027, 3, 1),
                "custom_fwcms_receipt_reference": "FWCMS-2026-001",
                "custom_fwcms_levy_sector": "Manufacturing",
            },
        )

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_renewal_agriculture_rate(self, mock_frappe):
        result = record_levy_renewal(
            employee_id="EMP-002",
            payment_date="2026-06-15",
            receipt_reference="FWCMS-2026-100",
            sector="Agriculture",
        )
        self.assertEqual(result["rate"], 640)
        self.assertEqual(result["expiry_date"], date(2027, 6, 15))

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_renewal_custom_plks_duration(self, mock_frappe):
        result = record_levy_renewal(
            employee_id="EMP-003",
            payment_date="2026-01-01",
            receipt_reference="FWCMS-2026-200",
            sector="Construction",
            plks_duration_days=730,
        )
        self.assertEqual(result["expiry_date"], date(2028, 1, 1))

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_renewal_validation_fails(self, mock_frappe):
        mock_frappe.ValidationError = type("ValidationError", (Exception,), {})
        mock_frappe.throw = MagicMock(side_effect=mock_frappe.ValidationError("fail"))

        with self.assertRaises(mock_frappe.ValidationError):
            record_levy_renewal(
                employee_id="EMP-001",
                payment_date=None,
                receipt_reference="",
                sector="Mining",
            )
        mock_frappe.throw.assert_called_once()

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_renewal_strips_receipt_whitespace(self, mock_frappe):
        result = record_levy_renewal(
            employee_id="EMP-004",
            payment_date="2026-03-01",
            receipt_reference="  FWCMS-001  ",
            sector="Services",
        )
        self.assertEqual(result["receipt_reference"], "FWCMS-001")


class TestGetNoncompliantWorkersSummary(unittest.TestCase):
    """Test get_noncompliant_workers_summary() — dashboard widget data."""

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_empty_result(self, mock_frappe):
        mock_frappe.db.get_all.return_value = []
        result = get_noncompliant_workers_summary(reference_date="2026-03-01")
        self.assertEqual(result["expired"], [])
        self.assertEqual(result["expiring_30"], [])
        self.assertEqual(result["expiring_60"], [])
        self.assertEqual(result["counts"]["expired"], 0)

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_mixed_workers(self, mock_frappe):
        mock_frappe.db.get_all.return_value = [
            {
                "employee": "EMP-001",
                "employee_name": "Worker A",
                "company": "Test Co",
                "expiry_date": "2026-02-15",  # expired
                "sector": "Manufacturing",
                "receipt_reference": None,
            },
            {
                "employee": "EMP-002",
                "employee_name": "Worker B",
                "company": "Test Co",
                "expiry_date": "2026-03-20",  # 19 days = expiring_30
                "sector": "Construction",
                "receipt_reference": "FWCMS-001",
            },
            {
                "employee": "EMP-003",
                "employee_name": "Worker C",
                "company": "Test Co",
                "expiry_date": "2026-04-15",  # 45 days = expiring_60
                "sector": "Plantation",
                "receipt_reference": None,
            },
            {
                "employee": "EMP-004",
                "employee_name": "Worker D",
                "company": "Test Co",
                "expiry_date": "2026-07-01",  # 122 days = no alert
                "sector": "Services",
                "receipt_reference": None,
            },
        ]

        result = get_noncompliant_workers_summary(reference_date="2026-03-01")

        self.assertEqual(result["counts"]["expired"], 1)
        self.assertEqual(result["counts"]["expiring_30"], 1)
        self.assertEqual(result["counts"]["expiring_60"], 1)
        self.assertEqual(result["expired"][0]["employee"], "EMP-001")
        self.assertEqual(result["expiring_30"][0]["employee"], "EMP-002")
        self.assertEqual(result["expiring_60"][0]["employee"], "EMP-003")

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_company_filter_passed(self, mock_frappe):
        mock_frappe.db.get_all.return_value = []
        get_noncompliant_workers_summary(company="Test Co", reference_date="2026-03-01")

        call_kwargs = mock_frappe.db.get_all.call_args
        filters = call_kwargs[1]["filters"] if "filters" in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(filters.get("company"), "Test Co")

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_sorted_by_urgency(self, mock_frappe):
        mock_frappe.db.get_all.return_value = [
            {
                "employee": "EMP-002",
                "employee_name": "B",
                "company": "Co",
                "expiry_date": "2026-03-25",  # 24 days
                "sector": "Services",
                "receipt_reference": None,
            },
            {
                "employee": "EMP-001",
                "employee_name": "A",
                "company": "Co",
                "expiry_date": "2026-03-10",  # 9 days
                "sector": "Services",
                "receipt_reference": None,
            },
        ]

        result = get_noncompliant_workers_summary(reference_date="2026-03-01")
        # Both in expiring_30, sorted by days_remaining ascending
        self.assertEqual(result["expiring_30"][0]["employee"], "EMP-001")
        self.assertEqual(result["expiring_30"][1]["employee"], "EMP-002")


class TestGetWorkersNeedingAlerts(unittest.TestCase):
    """Test get_workers_needing_alerts() — scheduler alert data."""

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_no_workers(self, mock_frappe):
        mock_frappe.db.get_all.return_value = []
        result = get_workers_needing_alerts(reference_date="2026-03-01")
        self.assertEqual(result, [])

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_workers_with_alerts(self, mock_frappe):
        mock_frappe.db.get_all.return_value = [
            {
                "employee": "EMP-001",
                "employee_name": "A",
                "company": "Co",
                "expiry_date": "2026-03-10",  # 9 days → critical_14
                "sector": "Manufacturing",
                "receipt_reference": None,
            },
            {
                "employee": "EMP-002",
                "employee_name": "B",
                "company": "Co",
                "expiry_date": "2026-04-15",  # 45 days → alert_60
                "sector": "Construction",
                "receipt_reference": "FWCMS-001",
            },
            {
                "employee": "EMP-003",
                "employee_name": "C",
                "company": "Co",
                "expiry_date": "2026-08-01",  # 153 days → no alert
                "sector": "Plantation",
                "receipt_reference": None,
            },
        ]

        result = get_workers_needing_alerts(reference_date="2026-03-01")
        self.assertEqual(len(result), 2)

        # Sorted by days_remaining, EMP-001 first
        self.assertEqual(result[0]["employee"], "EMP-001")
        self.assertEqual(result[0]["alert_tier"], "critical_14")
        self.assertTrue(result[0]["needs_critical_escalation"])

        self.assertEqual(result[1]["employee"], "EMP-002")
        self.assertEqual(result[1]["alert_tier"], "alert_60")
        self.assertFalse(result[1]["needs_critical_escalation"])

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_critical_with_receipt_no_escalation(self, mock_frappe):
        mock_frappe.db.get_all.return_value = [
            {
                "employee": "EMP-001",
                "employee_name": "A",
                "company": "Co",
                "expiry_date": "2026-03-10",  # 9 days → critical_14
                "sector": "Manufacturing",
                "receipt_reference": "FWCMS-001",  # has receipt
            },
        ]

        result = get_workers_needing_alerts(reference_date="2026-03-01")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["alert_tier"], "critical_14")
        self.assertFalse(result[0]["needs_critical_escalation"])

    @patch("lhdn_payroll_integration.services.fwcms_levy_renewal_service.frappe")
    def test_expired_worker_included(self, mock_frappe):
        mock_frappe.db.get_all.return_value = [
            {
                "employee": "EMP-001",
                "employee_name": "A",
                "company": "Co",
                "expiry_date": "2026-02-15",  # expired
                "sector": "Manufacturing",
                "receipt_reference": None,
            },
        ]

        result = get_workers_needing_alerts(reference_date="2026-03-01")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["alert_tier"], "expired")


if __name__ == "__main__":
    unittest.main()
