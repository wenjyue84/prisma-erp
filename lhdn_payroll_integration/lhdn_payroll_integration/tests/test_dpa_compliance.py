"""Tests for PDPA 2024 Data Processor Agreement Compliance Service (US-208).

Covers:
- Constants and configuration values
- Processor record validation
- DPA status classification (active, expiring_soon, expired)
- Days-until-expiry calculation
- DPA expiry alert generation
- Export audit logging
- Compliance checklist report generation
- Bulk export DPA gate (warn if no active DPA)
- Processor summary aggregation
"""

import unittest
from datetime import date
from unittest.mock import patch, MagicMock, call

from lhdn_payroll_integration.services.dpa_compliance_service import (
    DPA_EXPIRY_WARNING_DAYS,
    SENSITIVE_DATA_CATEGORIES,
    REQUIRED_DPA_FIELDS,
    MAX_PENALTY_MYR,
    EFFECTIVE_DATE,
    validate_processor_record,
    get_dpa_status,
    get_days_until_dpa_expiry,
    is_dpa_expired,
    is_dpa_expiring_soon,
    get_processors_needing_alerts,
    log_data_export,
    generate_compliance_checklist,
    check_active_dpa_for_processor,
    warn_if_no_active_dpa,
    get_all_processors_summary,
)


class TestDpaConstants(unittest.TestCase):
    """Verify module-level constants."""

    def test_warning_days_is_30(self):
        self.assertEqual(DPA_EXPIRY_WARNING_DAYS, 30)

    def test_sensitive_categories_count(self):
        self.assertGreaterEqual(len(SENSITIVE_DATA_CATEGORIES), 5)

    def test_salary_in_categories(self):
        self.assertIn("Salary", SENSITIVE_DATA_CATEGORIES)

    def test_ic_number_in_categories(self):
        self.assertIn("IC Number", SENSITIVE_DATA_CATEGORIES)

    def test_tin_in_categories(self):
        self.assertIn("TIN", SENSITIVE_DATA_CATEGORIES)

    def test_bank_account_in_categories(self):
        self.assertIn("Bank Account", SENSITIVE_DATA_CATEGORIES)

    def test_required_fields_count(self):
        self.assertEqual(len(REQUIRED_DPA_FIELDS), 4)

    def test_processor_name_required(self):
        self.assertIn("processor_name", REQUIRED_DPA_FIELDS)

    def test_services_provided_required(self):
        self.assertIn("services_provided", REQUIRED_DPA_FIELDS)

    def test_signed_date_required(self):
        self.assertIn("dpa_signed_date", REQUIRED_DPA_FIELDS)

    def test_expiry_date_required(self):
        self.assertIn("dpa_expiry_date", REQUIRED_DPA_FIELDS)

    def test_max_penalty(self):
        self.assertEqual(MAX_PENALTY_MYR, 1_000_000)

    def test_effective_date(self):
        self.assertEqual(EFFECTIVE_DATE, "2025-06-01")


class TestValidateProcessorRecord(unittest.TestCase):
    """Test processor record validation logic."""

    def _valid_record(self):
        return {
            "processor_name": "PayrollBureau Sdn Bhd",
            "services_provided": "PCB submission, EPF filing",
            "dpa_signed_date": "2025-01-15",
            "dpa_expiry_date": "2026-01-14",
        }

    def test_valid_record(self):
        result = validate_processor_record(self._valid_record())
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_empty_record(self):
        # Empty dict is falsy in Python → early "Record is empty" return
        result = validate_processor_record({})
        self.assertFalse(result["valid"])
        self.assertIn("Record is empty", result["errors"])

    def test_none_record(self):
        result = validate_processor_record(None)
        self.assertFalse(result["valid"])
        self.assertIn("Record is empty", result["errors"])

    def test_missing_processor_name(self):
        rec = self._valid_record()
        del rec["processor_name"]
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])
        self.assertTrue(any("processor_name" in e for e in result["errors"]))

    def test_missing_services_provided(self):
        rec = self._valid_record()
        rec["services_provided"] = ""
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])

    def test_missing_signed_date(self):
        rec = self._valid_record()
        rec["dpa_signed_date"] = None
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])

    def test_missing_expiry_date(self):
        rec = self._valid_record()
        rec["dpa_expiry_date"] = ""
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])

    def test_expiry_before_signed_invalid(self):
        rec = self._valid_record()
        rec["dpa_signed_date"] = "2026-06-01"
        rec["dpa_expiry_date"] = "2025-01-01"
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])
        self.assertTrue(any("after" in e for e in result["errors"]))

    def test_expiry_equals_signed_invalid(self):
        rec = self._valid_record()
        rec["dpa_signed_date"] = "2025-06-01"
        rec["dpa_expiry_date"] = "2025-06-01"
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])

    def test_whitespace_only_processor_name(self):
        rec = self._valid_record()
        rec["processor_name"] = "   "
        result = validate_processor_record(rec)
        self.assertFalse(result["valid"])


class TestGetDpaStatus(unittest.TestCase):
    """Test DPA status classification."""

    def test_active_dpa(self):
        status = get_dpa_status("2027-06-01", reference_date="2026-03-01")
        self.assertEqual(status, "active")

    def test_expiring_soon_30_days(self):
        status = get_dpa_status("2026-03-31", reference_date="2026-03-01")
        self.assertEqual(status, "expiring_soon")

    def test_expiring_soon_1_day(self):
        status = get_dpa_status("2026-03-02", reference_date="2026-03-01")
        self.assertEqual(status, "expiring_soon")

    def test_expiring_soon_boundary_exact_30(self):
        status = get_dpa_status("2026-03-31", reference_date="2026-03-01")
        self.assertEqual(status, "expiring_soon")

    def test_active_31_days_out(self):
        status = get_dpa_status("2026-04-01", reference_date="2026-03-01")
        self.assertEqual(status, "active")

    def test_expired_yesterday(self):
        status = get_dpa_status("2026-02-28", reference_date="2026-03-01")
        self.assertEqual(status, "expired")

    def test_expired_long_ago(self):
        status = get_dpa_status("2024-01-01", reference_date="2026-03-01")
        self.assertEqual(status, "expired")

    def test_expires_today_is_expiring_soon(self):
        # 0 days remaining → within the 30-day window
        status = get_dpa_status("2026-03-01", reference_date="2026-03-01")
        self.assertEqual(status, "expiring_soon")


class TestDaysUntilDpaExpiry(unittest.TestCase):
    """Test days-until-expiry calculation."""

    def test_positive_days(self):
        days = get_days_until_dpa_expiry("2026-04-01", reference_date="2026-03-01")
        self.assertEqual(days, 31)

    def test_zero_days(self):
        days = get_days_until_dpa_expiry("2026-03-01", reference_date="2026-03-01")
        self.assertEqual(days, 0)

    def test_negative_days(self):
        days = get_days_until_dpa_expiry("2026-02-28", reference_date="2026-03-01")
        self.assertEqual(days, -1)

    def test_large_positive(self):
        days = get_days_until_dpa_expiry("2028-03-01", reference_date="2026-03-01")
        self.assertGreater(days, 700)


class TestIsDpaExpired(unittest.TestCase):
    """Test DPA expired check."""

    def test_not_expired_future(self):
        self.assertFalse(is_dpa_expired("2027-01-01", reference_date="2026-03-01"))

    def test_expired_past(self):
        self.assertTrue(is_dpa_expired("2026-02-28", reference_date="2026-03-01"))

    def test_not_expired_today(self):
        # Expiry date == today → 0 days remaining → NOT expired
        self.assertFalse(is_dpa_expired("2026-03-01", reference_date="2026-03-01"))


class TestIsDpaExpiringSoon(unittest.TestCase):
    """Test DPA expiring-soon check."""

    def test_expiring_in_15_days(self):
        self.assertTrue(is_dpa_expiring_soon("2026-03-16", reference_date="2026-03-01"))

    def test_expiring_in_30_days(self):
        self.assertTrue(is_dpa_expiring_soon("2026-03-31", reference_date="2026-03-01"))

    def test_not_expiring_31_days(self):
        self.assertFalse(is_dpa_expiring_soon("2026-04-01", reference_date="2026-03-01"))

    def test_already_expired(self):
        self.assertFalse(is_dpa_expiring_soon("2026-02-28", reference_date="2026-03-01"))

    def test_expiring_today(self):
        self.assertTrue(is_dpa_expiring_soon("2026-03-01", reference_date="2026-03-01"))


class TestGetProcessorsNeedingAlerts(unittest.TestCase):
    """Test alert generation for expiring/expired DPAs."""

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_no_processors(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        result = get_processors_needing_alerts("TestCo", reference_date="2026-03-01")
        self.assertEqual(result["total_alerts"], 0)
        self.assertEqual(result["expiring_soon"], [])
        self.assertEqual(result["expired"], [])

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_one_expired_processor(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-001",
                "processor_name": "Old Bureau",
                "services_provided": "PCB",
                "dpa_signed_date": "2024-01-01",
                "dpa_expiry_date": "2025-12-31",
                "last_security_audit_date": None,
            }
        ]
        result = get_processors_needing_alerts("TestCo", reference_date="2026-03-01")
        self.assertEqual(result["total_alerts"], 1)
        self.assertEqual(len(result["expired"]), 1)
        self.assertEqual(result["expired"][0]["status"], "expired")

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_one_expiring_soon_processor(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-002",
                "processor_name": "Almost Expiring Bureau",
                "services_provided": "EPF filing",
                "dpa_signed_date": "2025-04-01",
                "dpa_expiry_date": "2026-03-20",
                "last_security_audit_date": None,
            }
        ]
        result = get_processors_needing_alerts("TestCo", reference_date="2026-03-01")
        self.assertEqual(result["total_alerts"], 1)
        self.assertEqual(len(result["expiring_soon"]), 1)
        self.assertEqual(result["expiring_soon"][0]["days_remaining"], 19)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_active_processor_not_alerted(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-003",
                "processor_name": "Good Bureau",
                "services_provided": "Payroll",
                "dpa_signed_date": "2025-06-01",
                "dpa_expiry_date": "2027-06-01",
                "last_security_audit_date": "2026-01-15",
            }
        ]
        result = get_processors_needing_alerts("TestCo", reference_date="2026-03-01")
        self.assertEqual(result["total_alerts"], 0)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_missing_expiry_treated_as_expired(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-004",
                "processor_name": "No Expiry Bureau",
                "services_provided": "SOCSO",
                "dpa_signed_date": "2025-01-01",
                "dpa_expiry_date": None,
                "last_security_audit_date": None,
            }
        ]
        result = get_processors_needing_alerts("TestCo", reference_date="2026-03-01")
        self.assertEqual(result["total_alerts"], 1)
        self.assertEqual(len(result["expired"]), 1)
        self.assertEqual(result["expired"][0]["status"], "no_expiry_date")

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_mixed_statuses(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "A", "processor_name": "Active", "services_provided": "X",
             "dpa_signed_date": "2025-01-01", "dpa_expiry_date": "2027-01-01",
             "last_security_audit_date": None},
            {"name": "B", "processor_name": "Expiring", "services_provided": "Y",
             "dpa_signed_date": "2025-01-01", "dpa_expiry_date": "2026-03-15",
             "last_security_audit_date": None},
            {"name": "C", "processor_name": "Expired", "services_provided": "Z",
             "dpa_signed_date": "2024-01-01", "dpa_expiry_date": "2025-06-01",
             "last_security_audit_date": None},
        ]
        result = get_processors_needing_alerts("TestCo", reference_date="2026-03-01")
        self.assertEqual(result["total_alerts"], 2)
        self.assertEqual(len(result["expiring_soon"]), 1)
        self.assertEqual(len(result["expired"]), 1)


class TestLogDataExport(unittest.TestCase):
    """Test export audit logging."""

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_log_creates_entry(self, mock_frappe):
        mock_doc = MagicMock()
        mock_doc.name = "EAL-001"
        mock_frappe.get_doc.return_value = mock_doc

        result = log_data_export(
            user="admin@example.com",
            data_categories=["Salary", "TIN"],
            downstream_processor="PayrollBureau Sdn Bhd",
            employee="HR-EMP-001",
        )
        self.assertEqual(result["user"], "admin@example.com")
        self.assertEqual(result["downstream_processor"], "PayrollBureau Sdn Bhd")
        self.assertIn("Salary", result["data_categories"])
        self.assertIn("TIN", result["data_categories"])
        mock_frappe.get_doc.assert_called_once()

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_log_empty_categories(self, mock_frappe):
        mock_doc = MagicMock()
        mock_doc.name = "EAL-002"
        mock_frappe.get_doc.return_value = mock_doc

        result = log_data_export(
            user="admin@example.com",
            data_categories=[],
            downstream_processor="BankX",
        )
        self.assertEqual(result["data_categories"], "")

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_log_includes_timestamp(self, mock_frappe):
        mock_doc = MagicMock()
        mock_doc.name = "EAL-003"
        mock_frappe.get_doc.return_value = mock_doc

        result = log_data_export(
            user="hr@example.com",
            data_categories=["IC Number"],
            downstream_processor="EPF Agent",
        )
        self.assertIn("timestamp", result)
        self.assertIsNotNone(result["timestamp"])

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_log_handles_exception_gracefully(self, mock_frappe):
        mock_frappe.get_doc.side_effect = Exception("DB error")
        mock_frappe.get_traceback.return_value = "traceback"

        # Should not raise
        result = log_data_export(
            user="admin@example.com",
            data_categories=["Salary"],
            downstream_processor="BadBureau",
        )
        self.assertEqual(result["user"], "admin@example.com")
        mock_frappe.log_error.assert_called_once()


class TestGenerateComplianceChecklist(unittest.TestCase):
    """Test compliance checklist report generation."""

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_empty_registry(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        result = generate_compliance_checklist("TestCo")
        self.assertEqual(result["summary"]["total_processors"], 0)
        self.assertEqual(result["summary"]["compliance_rate"], 0.0)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_fully_compliant_processor(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-001",
                "processor_name": "Good Bureau",
                "services_provided": "PCB",
                "dpa_signed_date": "2025-06-01",
                "dpa_expiry_date": "2027-06-01",
                "dpa_document_attachment": "/files/dpa_good.pdf",
                "dpo_notified": 1,
                "last_security_audit_date": "2026-01-01",
            }
        ]
        result = generate_compliance_checklist("TestCo")
        proc = result["processors"][0]
        self.assertEqual(proc["dpa_on_file"], "Yes")
        self.assertEqual(proc["dpa_current"], "Yes")
        self.assertEqual(proc["dpo_notified"], "Yes")
        self.assertTrue(proc["compliant"])
        self.assertEqual(result["summary"]["compliant"], 1)
        self.assertEqual(result["summary"]["compliance_rate"], 100.0)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_non_compliant_no_attachment(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-002",
                "processor_name": "No Doc Bureau",
                "services_provided": "EPF",
                "dpa_signed_date": "2025-06-01",
                "dpa_expiry_date": "2027-06-01",
                "dpa_document_attachment": None,
                "dpo_notified": 1,
                "last_security_audit_date": None,
            }
        ]
        result = generate_compliance_checklist("TestCo")
        proc = result["processors"][0]
        self.assertEqual(proc["dpa_on_file"], "No")
        self.assertFalse(proc["compliant"])
        self.assertEqual(result["summary"]["non_compliant"], 1)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_non_compliant_expired_dpa(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-003",
                "processor_name": "Expired Bureau",
                "services_provided": "SOCSO",
                "dpa_signed_date": "2024-01-01",
                "dpa_expiry_date": "2025-12-31",
                "dpa_document_attachment": "/files/dpa.pdf",
                "dpo_notified": 1,
                "last_security_audit_date": None,
            }
        ]
        result = generate_compliance_checklist("TestCo")
        proc = result["processors"][0]
        self.assertEqual(proc["dpa_current"], "No")
        self.assertFalse(proc["compliant"])

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_non_compliant_dpo_not_notified(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-004",
                "processor_name": "No DPO Bureau",
                "services_provided": "Bank disbursement",
                "dpa_signed_date": "2025-06-01",
                "dpa_expiry_date": "2027-06-01",
                "dpa_document_attachment": "/files/dpa.pdf",
                "dpo_notified": 0,
                "last_security_audit_date": None,
            }
        ]
        result = generate_compliance_checklist("TestCo")
        proc = result["processors"][0]
        self.assertEqual(proc["dpo_notified"], "No")
        self.assertFalse(proc["compliant"])

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_mixed_compliance(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {
                "name": "DPR-A", "processor_name": "Compliant",
                "services_provided": "PCB",
                "dpa_signed_date": "2025-06-01", "dpa_expiry_date": "2027-06-01",
                "dpa_document_attachment": "/files/a.pdf",
                "dpo_notified": 1, "last_security_audit_date": None,
            },
            {
                "name": "DPR-B", "processor_name": "NonCompliant",
                "services_provided": "EPF",
                "dpa_signed_date": "2025-06-01", "dpa_expiry_date": "2027-06-01",
                "dpa_document_attachment": None,
                "dpo_notified": 0, "last_security_audit_date": None,
            },
        ]
        result = generate_compliance_checklist("TestCo")
        self.assertEqual(result["summary"]["total_processors"], 2)
        self.assertEqual(result["summary"]["compliant"], 1)
        self.assertEqual(result["summary"]["non_compliant"], 1)
        self.assertEqual(result["summary"]["compliance_rate"], 50.0)


class TestCheckActiveDpaForProcessor(unittest.TestCase):
    """Test bulk export DPA gate."""

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_no_record_found(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        result = check_active_dpa_for_processor("TestCo", "UnknownBureau")
        self.assertFalse(result["has_active_dpa"])
        self.assertIn("No processor record found", result["reason"])

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_active_dpa_found(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "DPR-001", "dpa_expiry_date": "2027-06-01", "dpa_signed_date": "2025-06-01"}
        ]
        result = check_active_dpa_for_processor("TestCo", "GoodBureau")
        self.assertTrue(result["has_active_dpa"])

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_all_dpas_expired(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "DPR-001", "dpa_expiry_date": "2025-01-01", "dpa_signed_date": "2024-01-01"},
            {"name": "DPR-002", "dpa_expiry_date": "2024-06-01", "dpa_signed_date": "2023-06-01"},
        ]
        result = check_active_dpa_for_processor("TestCo", "ExpiredBureau")
        self.assertFalse(result["has_active_dpa"])
        self.assertIn("expired", result["reason"])


class TestWarnIfNoActiveDpa(unittest.TestCase):
    """Test warning message generation for missing DPA."""

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_no_warning_when_active(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "DPR-001", "dpa_expiry_date": "2027-06-01", "dpa_signed_date": "2025-06-01"}
        ]
        warning = warn_if_no_active_dpa("TestCo", "GoodBureau")
        self.assertIsNone(warning)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_warning_when_no_record(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        warning = warn_if_no_active_dpa("TestCo", "UnknownBureau")
        self.assertIsNotNone(warning)
        self.assertIn("WARNING", warning)
        self.assertIn("PDPA 2024", warning)
        self.assertIn("UnknownBureau", warning)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_warning_when_all_expired(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "DPR-001", "dpa_expiry_date": "2024-01-01", "dpa_signed_date": "2023-01-01"}
        ]
        warning = warn_if_no_active_dpa("TestCo", "OldBureau")
        self.assertIsNotNone(warning)
        self.assertIn("expired", warning)


class TestGetAllProcessorsSummary(unittest.TestCase):
    """Test processor summary aggregation."""

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_empty_registry(self, mock_frappe):
        mock_frappe.get_all.return_value = []
        result = get_all_processors_summary("TestCo")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["active"], 0)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_mixed_statuses(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "A", "processor_name": "Active", "dpa_expiry_date": "2027-06-01"},
            {"name": "B", "processor_name": "Expiring", "dpa_expiry_date": "2026-03-15"},
            {"name": "C", "processor_name": "Expired", "dpa_expiry_date": "2025-01-01"},
            {"name": "D", "processor_name": "NoDPA", "dpa_expiry_date": None},
        ]
        result = get_all_processors_summary("TestCo")
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["active"], 1)
        self.assertEqual(result["expiring_soon"], 1)
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["no_dpa"], 1)

    @patch("lhdn_payroll_integration.services.dpa_compliance_service.frappe")
    def test_all_active(self, mock_frappe):
        mock_frappe.get_all.return_value = [
            {"name": "A", "processor_name": "Bureau1", "dpa_expiry_date": "2028-01-01"},
            {"name": "B", "processor_name": "Bureau2", "dpa_expiry_date": "2029-06-01"},
        ]
        result = get_all_processors_summary("TestCo")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["active"], 2)
        self.assertEqual(result["expired"], 0)
