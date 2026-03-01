"""Tests for US-180: Gig Workers Act 2025 — Service Agreement Compliance Tracker.

Verifies the mandatory service agreement compliance tracking for platform
providers under the Gig Workers Act 2025 (Act 872).

Test coverage:
  - Constants (retention years, alert window, suspension limit, mandatory terms)
  - validate_agreement_terms() — 7 mandatory terms validation
  - get_agreement_status() — Valid/Expired/Pending Renewal determination
  - check_payment_eligibility() — payment blocking logic
  - get_expiring_agreements() — expiry alert query (mocked)
  - generate_compliance_report() — full compliance report (mocked)
  - check_retention_compliance() — MOHR 7-year retention (mocked)
  - check_grievance_window() — 30-day complaint window
  - check_suspension_compliance() — 14-day max suspension
"""
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase


class TestConstants(FrappeTestCase):
    """Module-level constants are correct per Gig Workers Act 2025 (Act 872)."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            GIG_WORKER_EMPLOYMENT_TYPE,
            MOHR_RETENTION_YEARS,
            EXPIRY_ALERT_DAYS,
            MAX_SUSPENSION_DAYS,
            GRIEVANCE_COMPLAINT_WINDOW_DAYS,
            MANDATORY_AGREEMENT_TERMS,
            STATUS_VALID,
            STATUS_EXPIRED,
            STATUS_MISSING,
            STATUS_PENDING_RENEWAL,
        )
        self.gig_type = GIG_WORKER_EMPLOYMENT_TYPE
        self.retention = MOHR_RETENTION_YEARS
        self.alert_days = EXPIRY_ALERT_DAYS
        self.max_suspension = MAX_SUSPENSION_DAYS
        self.grievance_days = GRIEVANCE_COMPLAINT_WINDOW_DAYS
        self.terms = MANDATORY_AGREEMENT_TERMS
        self.status_valid = STATUS_VALID
        self.status_expired = STATUS_EXPIRED
        self.status_missing = STATUS_MISSING
        self.status_pending = STATUS_PENDING_RENEWAL

    def test_gig_worker_employment_type(self):
        self.assertEqual(self.gig_type, "Gig / Platform Worker")

    def test_mohr_retention_7_years(self):
        self.assertEqual(self.retention, 7)

    def test_expiry_alert_30_days(self):
        self.assertEqual(self.alert_days, 30)

    def test_max_suspension_14_days(self):
        self.assertEqual(self.max_suspension, 14)

    def test_grievance_window_30_days(self):
        self.assertEqual(self.grievance_days, 30)

    def test_mandatory_terms_count_is_7(self):
        self.assertEqual(len(self.terms), 7)

    def test_mandatory_terms_content(self):
        expected = [
            "parties", "period", "services_description", "obligations",
            "earnings_rate", "payment_method", "entitled_benefits",
        ]
        self.assertEqual(self.terms, expected)

    def test_status_constants(self):
        self.assertEqual(self.status_valid, "Valid")
        self.assertEqual(self.status_expired, "Expired")
        self.assertEqual(self.status_missing, "Missing")
        self.assertEqual(self.status_pending, "Pending Renewal")


class TestValidateAgreementTerms(FrappeTestCase):
    """validate_agreement_terms() checks all 7 mandatory terms."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            validate_agreement_terms,
        )
        self.validate = validate_agreement_terms

    def _full_agreement(self):
        return {
            "parties": "Platform X and Worker Y",
            "period": "1 year",
            "services_description": "Food delivery services",
            "obligations": "Complete deliveries within SLA",
            "earnings_rate": "RM5 per delivery",
            "payment_method": "Bank transfer, weekly",
            "entitled_benefits": "SOCSO/SEIA coverage",
        }

    def test_all_terms_present_is_valid(self):
        result = self.validate(self._full_agreement())
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["missing"]), 0)
        self.assertEqual(len(result["present"]), 7)

    def test_missing_one_term_is_invalid(self):
        agr = self._full_agreement()
        del agr["parties"]
        result = self.validate(agr)
        self.assertFalse(result["valid"])
        self.assertIn("parties", result["missing"])

    def test_missing_multiple_terms(self):
        agr = self._full_agreement()
        del agr["obligations"]
        del agr["entitled_benefits"]
        result = self.validate(agr)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["missing"]), 2)

    def test_empty_string_term_is_invalid(self):
        agr = self._full_agreement()
        agr["earnings_rate"] = ""
        result = self.validate(agr)
        self.assertFalse(result["valid"])
        self.assertIn("earnings_rate", result["missing"])

    def test_whitespace_only_term_is_invalid(self):
        agr = self._full_agreement()
        agr["payment_method"] = "   "
        result = self.validate(agr)
        self.assertFalse(result["valid"])
        self.assertIn("payment_method", result["missing"])

    def test_empty_dict_all_terms_missing(self):
        result = self.validate({})
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["missing"]), 7)

    def test_none_term_is_invalid(self):
        agr = self._full_agreement()
        agr["services_description"] = None
        result = self.validate(agr)
        self.assertFalse(result["valid"])
        self.assertIn("services_description", result["missing"])


class TestGetAgreementStatus(FrappeTestCase):
    """get_agreement_status() determines Valid/Expired/Pending Renewal."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            get_agreement_status,
            STATUS_VALID,
            STATUS_EXPIRED,
            STATUS_PENDING_RENEWAL,
        )
        self.get_status = get_agreement_status
        self.VALID = STATUS_VALID
        self.EXPIRED = STATUS_EXPIRED
        self.PENDING = STATUS_PENDING_RENEWAL

    def test_no_end_date_is_valid(self):
        """Indefinite agreements are always valid."""
        agr = {"start_date": "2025-01-01", "end_date": None}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.VALID)

    def test_no_end_date_future_start_is_pending(self):
        """Agreement not yet started."""
        agr = {"start_date": "2027-01-01", "end_date": None}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.PENDING)

    def test_past_end_date_is_expired(self):
        agr = {"start_date": "2025-01-01", "end_date": "2026-01-01"}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.EXPIRED)

    def test_within_alert_window_is_pending_renewal(self):
        """End date within 30 days triggers pending renewal status."""
        agr = {"start_date": "2025-01-01", "end_date": "2026-07-10"}
        # 25 days remaining → within 30-day alert window
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.PENDING)

    def test_end_date_exactly_30_days_away(self):
        """Exactly 30 days remaining is within alert window."""
        agr = {"start_date": "2025-01-01", "end_date": "2026-07-15"}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.PENDING)

    def test_end_date_31_days_away_is_valid(self):
        """31 days remaining is outside alert window — still valid."""
        agr = {"start_date": "2025-01-01", "end_date": "2026-07-16"}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.VALID)

    def test_end_date_far_future_is_valid(self):
        agr = {"start_date": "2025-01-01", "end_date": "2028-12-31"}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.VALID)

    def test_end_date_is_today_is_pending(self):
        """Agreement ending today is within alert window (0 days remaining)."""
        agr = {"start_date": "2025-01-01", "end_date": "2026-06-15"}
        self.assertEqual(self.get_status(agr, "2026-06-15"), self.PENDING)


class TestCheckPaymentEligibility(FrappeTestCase):
    """check_payment_eligibility() blocks payment for missing/expired/incomplete agreements."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            check_payment_eligibility,
            STATUS_MISSING,
            STATUS_EXPIRED,
            STATUS_VALID,
            STATUS_PENDING_RENEWAL,
        )
        self.check = check_payment_eligibility
        self.MISSING = STATUS_MISSING
        self.EXPIRED = STATUS_EXPIRED
        self.VALID = STATUS_VALID
        self.PENDING = STATUS_PENDING_RENEWAL

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_agreement")
    def test_no_agreement_blocks_payment(self, mock_get):
        mock_get.return_value = None
        result = self.check("EMP-001", "2026-06-15")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], self.MISSING)
        self.assertIn("No service agreement", result["reason"])

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_agreement")
    def test_expired_agreement_blocks_payment(self, mock_get):
        mock_get.return_value = {
            "name": "GSA-001",
            "start_date": "2025-01-01",
            "end_date": "2026-01-01",
            "parties": "X", "period": "1y", "services_description": "Delivery",
            "obligations": "SLA", "earnings_rate": "RM5", "payment_method": "Bank",
            "entitled_benefits": "SOCSO",
        }
        result = self.check("EMP-001", "2026-06-15")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], self.EXPIRED)

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_agreement")
    def test_valid_complete_agreement_allows_payment(self, mock_get):
        mock_get.return_value = {
            "name": "GSA-002",
            "start_date": "2025-01-01",
            "end_date": "2028-12-31",
            "parties": "Platform X and Worker Y",
            "period": "3 years",
            "services_description": "Food delivery",
            "obligations": "Complete deliveries",
            "earnings_rate": "RM5/delivery",
            "payment_method": "Bank transfer weekly",
            "entitled_benefits": "SOCSO/SEIA",
        }
        result = self.check("EMP-001", "2026-06-15")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["status"], self.VALID)
        self.assertEqual(result["agreement"], "GSA-002")

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_agreement")
    def test_incomplete_agreement_blocks_payment(self, mock_get):
        """Agreement with missing mandatory terms blocks payment."""
        mock_get.return_value = {
            "name": "GSA-003",
            "start_date": "2025-01-01",
            "end_date": "2028-12-31",
            "parties": "Platform X and Worker Y",
            "period": "3 years",
            "services_description": "",  # missing
            "obligations": "",  # missing
            "earnings_rate": "RM5",
            "payment_method": "Bank",
            "entitled_benefits": "SOCSO",
        }
        result = self.check("EMP-001", "2026-06-15")
        self.assertFalse(result["eligible"])
        self.assertIn("missing mandatory terms", result["reason"])

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_agreement")
    def test_pending_renewal_allows_payment(self, mock_get):
        """Agreement within renewal window still allows payment (not yet expired)."""
        mock_get.return_value = {
            "name": "GSA-004",
            "start_date": "2025-01-01",
            "end_date": "2026-07-10",
            "parties": "X", "period": "1y", "services_description": "Delivery",
            "obligations": "SLA", "earnings_rate": "RM5", "payment_method": "Bank",
            "entitled_benefits": "SOCSO",
        }
        result = self.check("EMP-001", "2026-06-15")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["status"], self.PENDING)


class TestGetExpiringAgreements(FrappeTestCase):
    """get_expiring_agreements() returns agreements within alert window."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            get_expiring_agreements,
        )
        self.get_expiring = get_expiring_agreements

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.nowdate")
    def test_returns_empty_when_no_doctype(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-06-15"
        mock_frappe.db.exists.return_value = False
        result = self.get_expiring()
        self.assertEqual(result, [])

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.nowdate")
    def test_returns_expiring_agreements(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-06-15"
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_all.return_value = [
            {
                "name": "GSA-010",
                "employee": "EMP-010",
                "employee_name": "Ahmad",
                "start_date": "2025-06-15",
                "end_date": "2026-07-01",
                "company": "Test Sdn Bhd",
            }
        ]
        result = self.get_expiring()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["agreement"], "GSA-010")
        self.assertEqual(result[0]["employee"], "EMP-010")
        self.assertIn("days_remaining", result[0])

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.nowdate")
    def test_company_filter_passed(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-06-15"
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_all.return_value = []
        self.get_expiring(company="Test Sdn Bhd")
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(filters.get("company"), "Test Sdn Bhd")

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.nowdate")
    def test_custom_days_ahead(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-06-15"
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_all.return_value = []
        self.get_expiring(days_ahead=60)
        call_kwargs = mock_frappe.get_all.call_args
        filters = call_kwargs[1]["filters"] if call_kwargs[1] else call_kwargs[0][1]
        # Cutoff should be 60 days from 2026-06-15 = 2026-08-14
        between_range = filters.get("end_date")
        self.assertIsNotNone(between_range)


class TestGenerateComplianceReport(FrappeTestCase):
    """generate_compliance_report() produces correct report structure."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            generate_compliance_report,
        )
        self.report = generate_compliance_report

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_gig_workers")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.check_payment_eligibility")
    def test_report_structure(self, mock_check, mock_workers):
        mock_workers.return_value = [
            {"name": "EMP-001", "employee_name": "Ahmad", "company": "Test Co"},
        ]
        mock_check.return_value = {
            "eligible": True, "status": "Valid",
            "agreement": "GSA-001", "reason": "",
        }
        result = self.report()
        self.assertIn("total_workers", result)
        self.assertIn("valid", result)
        self.assertIn("expired", result)
        self.assertIn("missing", result)
        self.assertIn("pending_renewal", result)
        self.assertIn("workers", result)

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_gig_workers")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.check_payment_eligibility")
    def test_counts_valid_workers(self, mock_check, mock_workers):
        mock_workers.return_value = [
            {"name": "EMP-001", "employee_name": "Ahmad", "company": "Test Co"},
            {"name": "EMP-002", "employee_name": "Siti", "company": "Test Co"},
        ]
        mock_check.return_value = {
            "eligible": True, "status": "Valid",
            "agreement": "GSA-001", "reason": "",
        }
        result = self.report()
        self.assertEqual(result["total_workers"], 2)
        self.assertEqual(result["valid"], 2)

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_gig_workers")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.check_payment_eligibility")
    def test_counts_mixed_statuses(self, mock_check, mock_workers):
        mock_workers.return_value = [
            {"name": "EMP-001", "employee_name": "A", "company": "C"},
            {"name": "EMP-002", "employee_name": "B", "company": "C"},
            {"name": "EMP-003", "employee_name": "C", "company": "C"},
        ]
        mock_check.side_effect = [
            {"eligible": True, "status": "Valid", "agreement": "GSA-1", "reason": ""},
            {"eligible": False, "status": "Expired", "agreement": "GSA-2", "reason": "expired"},
            {"eligible": False, "status": "Missing", "agreement": None, "reason": "no agreement"},
        ]
        result = self.report()
        self.assertEqual(result["valid"], 1)
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["missing"], 1)

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service._get_active_gig_workers")
    def test_empty_workforce(self, mock_workers):
        mock_workers.return_value = []
        result = self.report()
        self.assertEqual(result["total_workers"], 0)
        self.assertEqual(result["workers"], [])


class TestCheckRetentionCompliance(FrappeTestCase):
    """check_retention_compliance() verifies 7-year MOHR retention."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            check_retention_compliance,
            MOHR_RETENTION_YEARS,
        )
        self.check = check_retention_compliance
        self.retention_years = MOHR_RETENTION_YEARS

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    def test_no_doctype_returns_non_compliant(self, mock_frappe):
        mock_frappe.db.exists.return_value = False
        result = self.check("GSA-001")
        self.assertFalse(result["compliant"])

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    def test_indefinite_agreement_is_compliant(self, mock_frappe):
        mock_frappe.db.exists.return_value = True
        mock_doc = MagicMock()
        mock_doc.get.return_value = None  # no end_date
        mock_frappe.get_doc.return_value = mock_doc
        result = self.check("GSA-001")
        self.assertTrue(result["compliant"])
        self.assertFalse(result["can_archive"])

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.nowdate")
    def test_recent_agreement_cannot_be_archived(self, mock_now, mock_frappe):
        mock_now.return_value = "2026-06-15"
        mock_frappe.db.exists.return_value = True
        mock_doc = MagicMock()
        mock_doc.get.return_value = "2026-01-01"  # ended 6 months ago
        mock_frappe.get_doc.return_value = mock_doc
        result = self.check("GSA-001")
        self.assertTrue(result["compliant"])
        self.assertFalse(result["can_archive"])  # Must keep for 7 more years

    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.frappe")
    @patch("lhdn_payroll_integration.services.gig_worker_agreement_service.nowdate")
    def test_old_agreement_can_be_archived(self, mock_now, mock_frappe):
        mock_now.return_value = "2036-06-15"
        mock_frappe.db.exists.return_value = True
        mock_doc = MagicMock()
        mock_doc.get.return_value = "2025-01-01"  # ended 11+ years ago
        mock_frappe.get_doc.return_value = mock_doc
        result = self.check("GSA-001")
        self.assertTrue(result["compliant"])
        self.assertTrue(result["can_archive"])

    def test_retention_constant_is_7(self):
        self.assertEqual(self.retention_years, 7)


class TestGrievanceWindow(FrappeTestCase):
    """check_grievance_window() validates 30-day complaint window."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            check_grievance_window,
        )
        self.check = check_grievance_window

    def test_within_window(self):
        result = self.check("2026-06-01", "2026-06-15")
        self.assertTrue(result["within_window"])
        self.assertEqual(result["days_elapsed"], 14)
        self.assertGreater(result["days_remaining"], 0)

    def test_exactly_at_deadline(self):
        """30 days from complaint = last day of window (still within)."""
        result = self.check("2026-06-01", "2026-07-01")
        self.assertTrue(result["within_window"])
        self.assertEqual(result["days_remaining"], 0)

    def test_past_deadline(self):
        result = self.check("2026-06-01", "2026-07-02")
        self.assertFalse(result["within_window"])
        self.assertEqual(result["days_remaining"], 0)

    def test_same_day_complaint(self):
        result = self.check("2026-06-15", "2026-06-15")
        self.assertTrue(result["within_window"])
        self.assertEqual(result["days_elapsed"], 0)
        self.assertEqual(result["days_remaining"], 30)

    def test_deadline_is_30_days_from_complaint(self):
        result = self.check("2026-06-01", "2026-06-15")
        self.assertEqual(result["deadline"], "2026-07-01")


class TestSuspensionCompliance(FrappeTestCase):
    """check_suspension_compliance() validates 14-day max suspension."""

    def setUp(self):
        from lhdn_payroll_integration.services.gig_worker_agreement_service import (
            check_suspension_compliance,
        )
        self.check = check_suspension_compliance

    def test_within_14_days_is_compliant(self):
        result = self.check("2026-06-01", as_of_date="2026-06-10")
        self.assertTrue(result["compliant"])
        self.assertEqual(result["suspension_days"], 9)

    def test_exactly_14_days_is_compliant(self):
        result = self.check("2026-06-01", as_of_date="2026-06-15")
        self.assertTrue(result["compliant"])
        self.assertEqual(result["suspension_days"], 14)

    def test_15_days_without_inquiry_is_non_compliant(self):
        result = self.check("2026-06-01", as_of_date="2026-06-16")
        self.assertFalse(result["compliant"])
        self.assertEqual(result["suspension_days"], 15)

    def test_inquiry_held_within_14_days_is_compliant(self):
        result = self.check("2026-06-01", inquiry_date="2026-06-10")
        self.assertTrue(result["compliant"])
        self.assertTrue(result["inquiry_held"])

    def test_inquiry_held_after_14_days_is_non_compliant(self):
        result = self.check("2026-06-01", inquiry_date="2026-06-20")
        self.assertFalse(result["compliant"])
        self.assertTrue(result["inquiry_held"])

    def test_max_days_is_14(self):
        result = self.check("2026-06-01", as_of_date="2026-06-01")
        self.assertEqual(result["max_days"], 14)

    def test_inquiry_deadline_date_correct(self):
        result = self.check("2026-06-01", as_of_date="2026-06-01")
        self.assertEqual(result["inquiry_required_by"], "2026-06-15")
