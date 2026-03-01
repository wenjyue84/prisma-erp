"""Tests for US-242: e-Invoice Mandatory Phase Readiness Check.

Validates phase determination, credential checks, readiness assessment,
phase transition detection, notification builders, and dashboard summary.
"""

from datetime import date
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.einvoice_readiness_service import (
    # Constants
    PHASE_1_THRESHOLD,
    PHASE_2_THRESHOLD,
    PHASE_3_THRESHOLD,
    PHASE_1_LABEL,
    PHASE_2_LABEL,
    PHASE_3_LABEL,
    PHASE_4_LABEL,
    VOLUNTARY_LABEL,
    PHASE_1_DATE,
    PHASE_2_DATE,
    PHASE_3_DATE,
    PHASE_4_DATE,
    STATUS_COMPLIANT,
    STATUS_CREDENTIALS_MISSING,
    STATUS_VOLUNTARY,
    STATUS_NOT_APPLICABLE,
    FIELD_ANNUAL_REVENUE,
    FIELD_CLIENT_ID,
    FIELD_CLIENT_SECRET,
    CREDENTIALS_WARNING,
    # Functions
    determine_mandate_phase,
    get_phase_effective_date,
    is_mandatory_phase,
    is_phase_active,
    has_myinvois_credentials,
    check_credentials_complete,
    assess_company_readiness,
    assess_multiple_companies,
    generate_readiness_report,
    detect_phase_transition,
    build_phase_transition_alert,
    build_credentials_warning,
    generate_dashboard_summary,
)


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------


class TestEInvoiceReadinessConstants(FrappeTestCase):
    """Verify constant values match LHDN e-invoice mandate schedule."""

    def test_phase_1_threshold(self):
        self.assertEqual(PHASE_1_THRESHOLD, 100_000_000)

    def test_phase_2_threshold(self):
        self.assertEqual(PHASE_2_THRESHOLD, 25_000_000)

    def test_phase_3_threshold(self):
        self.assertEqual(PHASE_3_THRESHOLD, 150_000)

    def test_phase_1_label(self):
        self.assertEqual(PHASE_1_LABEL, ">RM100M (Phase 1)")

    def test_phase_2_label(self):
        self.assertEqual(PHASE_2_LABEL, ">RM25M (Phase 2)")

    def test_phase_3_label(self):
        self.assertEqual(PHASE_3_LABEL, ">RM150K (Phase 3)")

    def test_phase_4_label(self):
        self.assertEqual(PHASE_4_LABEL, "All Businesses (Phase 4+)")

    def test_voluntary_label(self):
        self.assertEqual(VOLUNTARY_LABEL, "Below RM150K (Voluntary)")

    def test_phase_1_date(self):
        self.assertEqual(PHASE_1_DATE, date(2024, 8, 1))

    def test_phase_2_date(self):
        self.assertEqual(PHASE_2_DATE, date(2025, 1, 1))

    def test_phase_3_date(self):
        self.assertEqual(PHASE_3_DATE, date(2025, 7, 1))

    def test_phase_4_date_is_tbd(self):
        self.assertIsNone(PHASE_4_DATE)

    def test_status_constants(self):
        self.assertEqual(STATUS_COMPLIANT, "Compliant")
        self.assertEqual(STATUS_CREDENTIALS_MISSING, "Credentials Missing")
        self.assertEqual(STATUS_VOLUNTARY, "Voluntary")
        self.assertEqual(STATUS_NOT_APPLICABLE, "Not Applicable")

    def test_credentials_warning_message(self):
        self.assertIn("e-Invoice mandatory", CREDENTIALS_WARNING)
        self.assertIn("MyInvois API credentials", CREDENTIALS_WARNING)


# ---------------------------------------------------------------------------
# Phase Determination Tests
# ---------------------------------------------------------------------------


class TestDetermineMandatePhase(FrappeTestCase):
    """Test determine_mandate_phase() revenue-to-phase mapping."""

    def test_phase_1_above_100m(self):
        self.assertEqual(determine_mandate_phase(150_000_000), PHASE_1_LABEL)

    def test_phase_1_just_above(self):
        self.assertEqual(determine_mandate_phase(100_000_001), PHASE_1_LABEL)

    def test_phase_1_boundary_exact_100m_not_phase1(self):
        """RM100M exactly is NOT > RM100M, so it falls to Phase 2."""
        self.assertEqual(determine_mandate_phase(100_000_000), PHASE_2_LABEL)

    def test_phase_2_above_25m(self):
        self.assertEqual(determine_mandate_phase(50_000_000), PHASE_2_LABEL)

    def test_phase_2_just_above(self):
        self.assertEqual(determine_mandate_phase(25_000_001), PHASE_2_LABEL)

    def test_phase_2_boundary_exact_25m_not_phase2(self):
        """RM25M exactly is NOT > RM25M, so it falls to Phase 3."""
        self.assertEqual(determine_mandate_phase(25_000_000), PHASE_3_LABEL)

    def test_phase_3_above_150k(self):
        self.assertEqual(determine_mandate_phase(500_000), PHASE_3_LABEL)

    def test_phase_3_just_above(self):
        self.assertEqual(determine_mandate_phase(150_001), PHASE_3_LABEL)

    def test_phase_3_boundary_exact_150k_voluntary(self):
        """RM150K exactly is NOT > RM150K, so it's voluntary."""
        self.assertEqual(determine_mandate_phase(150_000), VOLUNTARY_LABEL)

    def test_voluntary_below_150k(self):
        self.assertEqual(determine_mandate_phase(100_000), VOLUNTARY_LABEL)

    def test_voluntary_zero_revenue(self):
        self.assertEqual(determine_mandate_phase(0), VOLUNTARY_LABEL)

    def test_voluntary_none_revenue(self):
        self.assertEqual(determine_mandate_phase(None), VOLUNTARY_LABEL)

    def test_voluntary_negative_revenue(self):
        self.assertEqual(determine_mandate_phase(-50_000), VOLUNTARY_LABEL)

    def test_very_high_revenue(self):
        self.assertEqual(determine_mandate_phase(1_000_000_000), PHASE_1_LABEL)


class TestGetPhaseEffectiveDate(FrappeTestCase):
    """Test get_phase_effective_date() returns correct dates."""

    def test_phase_1_date(self):
        self.assertEqual(get_phase_effective_date(PHASE_1_LABEL), date(2024, 8, 1))

    def test_phase_2_date(self):
        self.assertEqual(get_phase_effective_date(PHASE_2_LABEL), date(2025, 1, 1))

    def test_phase_3_date(self):
        self.assertEqual(get_phase_effective_date(PHASE_3_LABEL), date(2025, 7, 1))

    def test_phase_4_date_tbd(self):
        self.assertIsNone(get_phase_effective_date(PHASE_4_LABEL))

    def test_voluntary_date_none(self):
        self.assertIsNone(get_phase_effective_date(VOLUNTARY_LABEL))

    def test_unknown_label_returns_none(self):
        self.assertIsNone(get_phase_effective_date("Unknown Phase"))


class TestIsMandatoryPhase(FrappeTestCase):
    """Test is_mandatory_phase() correctly identifies mandatory phases."""

    def test_phase_1_mandatory(self):
        self.assertTrue(is_mandatory_phase(PHASE_1_LABEL))

    def test_phase_2_mandatory(self):
        self.assertTrue(is_mandatory_phase(PHASE_2_LABEL))

    def test_phase_3_mandatory(self):
        self.assertTrue(is_mandatory_phase(PHASE_3_LABEL))

    def test_phase_4_mandatory(self):
        self.assertTrue(is_mandatory_phase(PHASE_4_LABEL))

    def test_voluntary_not_mandatory(self):
        self.assertFalse(is_mandatory_phase(VOLUNTARY_LABEL))

    def test_none_not_mandatory(self):
        self.assertFalse(is_mandatory_phase(None))

    def test_empty_not_mandatory(self):
        self.assertFalse(is_mandatory_phase(""))


class TestIsPhaseActive(FrappeTestCase):
    """Test is_phase_active() checks date-based activation."""

    def test_phase_1_active_after_aug_2024(self):
        self.assertTrue(is_phase_active(PHASE_1_LABEL, as_of=date(2025, 1, 1)))

    def test_phase_1_active_on_exact_date(self):
        self.assertTrue(is_phase_active(PHASE_1_LABEL, as_of=date(2024, 8, 1)))

    def test_phase_1_not_active_before(self):
        self.assertFalse(is_phase_active(PHASE_1_LABEL, as_of=date(2024, 7, 31)))

    def test_phase_2_active_after_jan_2025(self):
        self.assertTrue(is_phase_active(PHASE_2_LABEL, as_of=date(2025, 6, 1)))

    def test_phase_2_not_active_before(self):
        self.assertFalse(is_phase_active(PHASE_2_LABEL, as_of=date(2024, 12, 31)))

    def test_phase_3_active_after_jul_2025(self):
        self.assertTrue(is_phase_active(PHASE_3_LABEL, as_of=date(2025, 8, 1)))

    def test_phase_3_not_active_before(self):
        self.assertFalse(is_phase_active(PHASE_3_LABEL, as_of=date(2025, 6, 30)))

    def test_phase_4_not_active_tbd(self):
        """Phase 4 date is TBD, so it's never active."""
        self.assertFalse(is_phase_active(PHASE_4_LABEL, as_of=date(2030, 1, 1)))

    def test_voluntary_not_active(self):
        self.assertFalse(is_phase_active(VOLUNTARY_LABEL, as_of=date(2030, 1, 1)))


# ---------------------------------------------------------------------------
# Credential Check Tests
# ---------------------------------------------------------------------------


class TestHasMyInvoisCredentials(FrappeTestCase):
    """Test has_myinvois_credentials() validates credential presence."""

    def test_both_present(self):
        self.assertTrue(has_myinvois_credentials("abc123", "secret456"))

    def test_missing_client_id(self):
        self.assertFalse(has_myinvois_credentials("", "secret456"))

    def test_missing_client_secret(self):
        self.assertFalse(has_myinvois_credentials("abc123", ""))

    def test_both_missing(self):
        self.assertFalse(has_myinvois_credentials("", ""))

    def test_none_client_id(self):
        self.assertFalse(has_myinvois_credentials(None, "secret456"))

    def test_none_client_secret(self):
        self.assertFalse(has_myinvois_credentials("abc123", None))

    def test_both_none(self):
        self.assertFalse(has_myinvois_credentials(None, None))

    def test_whitespace_only_id(self):
        self.assertFalse(has_myinvois_credentials("  ", "secret456"))

    def test_whitespace_only_secret(self):
        self.assertFalse(has_myinvois_credentials("abc123", "   "))


class TestCheckCredentialsComplete(FrappeTestCase):
    """Test check_credentials_complete() for detailed credential status."""

    def test_both_present(self):
        data = {FIELD_CLIENT_ID: "id123", FIELD_CLIENT_SECRET: "sec456"}
        result = check_credentials_complete(data)
        self.assertTrue(result["has_client_id"])
        self.assertTrue(result["has_client_secret"])
        self.assertTrue(result["is_complete"])

    def test_missing_id(self):
        data = {FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: "sec456"}
        result = check_credentials_complete(data)
        self.assertFalse(result["has_client_id"])
        self.assertTrue(result["has_client_secret"])
        self.assertFalse(result["is_complete"])

    def test_missing_secret(self):
        data = {FIELD_CLIENT_ID: "id123", FIELD_CLIENT_SECRET: ""}
        result = check_credentials_complete(data)
        self.assertTrue(result["has_client_id"])
        self.assertFalse(result["has_client_secret"])
        self.assertFalse(result["is_complete"])

    def test_both_missing(self):
        data = {}
        result = check_credentials_complete(data)
        self.assertFalse(result["has_client_id"])
        self.assertFalse(result["has_client_secret"])
        self.assertFalse(result["is_complete"])


# ---------------------------------------------------------------------------
# Company Readiness Assessment Tests
# ---------------------------------------------------------------------------


class TestAssessCompanyReadiness(FrappeTestCase):
    """Test assess_company_readiness() for single company evaluation."""

    def _make_company(self, name, revenue, client_id="", client_secret=""):
        return {
            "name": name,
            FIELD_ANNUAL_REVENUE: revenue,
            FIELD_CLIENT_ID: client_id,
            FIELD_CLIENT_SECRET: client_secret,
        }

    def test_voluntary_company(self):
        data = self._make_company("SmallCo", 50_000)
        result = assess_company_readiness(data)
        self.assertEqual(result["company"], "SmallCo")
        self.assertEqual(result["mandate_phase"], VOLUNTARY_LABEL)
        self.assertFalse(result["is_mandatory"])
        self.assertEqual(result["compliance_status"], STATUS_VOLUNTARY)
        self.assertIsNone(result["warning"])

    def test_phase_3_with_credentials(self):
        data = self._make_company("MediumCo", 300_000, "id123", "sec456")
        result = assess_company_readiness(data)
        self.assertEqual(result["mandate_phase"], PHASE_3_LABEL)
        self.assertTrue(result["is_mandatory"])
        self.assertTrue(result["credentials_complete"])
        self.assertEqual(result["compliance_status"], STATUS_COMPLIANT)
        self.assertIsNone(result["warning"])

    def test_phase_3_without_credentials(self):
        data = self._make_company("MediumCo", 300_000)
        result = assess_company_readiness(data)
        self.assertEqual(result["mandate_phase"], PHASE_3_LABEL)
        self.assertTrue(result["is_mandatory"])
        self.assertFalse(result["credentials_complete"])
        self.assertEqual(result["compliance_status"], STATUS_CREDENTIALS_MISSING)
        self.assertIsNotNone(result["warning"])
        self.assertIn("e-Invoice mandatory", result["warning"])

    def test_phase_1_without_credentials(self):
        data = self._make_company("BigCo", 200_000_000)
        result = assess_company_readiness(data)
        self.assertEqual(result["mandate_phase"], PHASE_1_LABEL)
        self.assertTrue(result["is_mandatory"])
        self.assertEqual(result["compliance_status"], STATUS_CREDENTIALS_MISSING)

    def test_phase_2_with_credentials(self):
        data = self._make_company("MidCo", 50_000_000, "id", "sec")
        result = assess_company_readiness(data)
        self.assertEqual(result["mandate_phase"], PHASE_2_LABEL)
        self.assertEqual(result["compliance_status"], STATUS_COMPLIANT)

    def test_zero_revenue(self):
        data = self._make_company("NewCo", 0)
        result = assess_company_readiness(data)
        self.assertEqual(result["compliance_status"], STATUS_VOLUNTARY)

    def test_none_revenue(self):
        data = self._make_company("NullCo", None)
        result = assess_company_readiness(data)
        self.assertEqual(result["compliance_status"], STATUS_VOLUNTARY)

    def test_annual_revenue_in_result(self):
        data = self._make_company("TestCo", 1_000_000, "id", "sec")
        result = assess_company_readiness(data)
        self.assertEqual(result["annual_revenue"], 1_000_000.0)


class TestAssessMultipleCompanies(FrappeTestCase):
    """Test assess_multiple_companies() batch evaluation."""

    def test_empty_list(self):
        result = assess_multiple_companies([])
        self.assertEqual(result, [])

    def test_none_input(self):
        result = assess_multiple_companies(None)
        self.assertEqual(result, [])

    def test_multiple_companies(self):
        companies = [
            {"name": "A", FIELD_ANNUAL_REVENUE: 200_000_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
            {"name": "B", FIELD_ANNUAL_REVENUE: 100_000, FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: ""},
            {"name": "C", FIELD_ANNUAL_REVENUE: 500_000, FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: ""},
        ]
        result = assess_multiple_companies(companies)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["compliance_status"], STATUS_COMPLIANT)
        self.assertEqual(result[1]["compliance_status"], STATUS_VOLUNTARY)
        self.assertEqual(result[2]["compliance_status"], STATUS_CREDENTIALS_MISSING)


# ---------------------------------------------------------------------------
# Readiness Report Tests
# ---------------------------------------------------------------------------


class TestGenerateReadinessReport(FrappeTestCase):
    """Test generate_readiness_report() aggregation."""

    def _sample_companies(self):
        return [
            {"name": "BigCo", FIELD_ANNUAL_REVENUE: 200_000_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
            {"name": "MidCo", FIELD_ANNUAL_REVENUE: 50_000_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
            {"name": "SMECo", FIELD_ANNUAL_REVENUE: 300_000, FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: ""},
            {"name": "MicroCo", FIELD_ANNUAL_REVENUE: 80_000, FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: ""},
        ]

    def test_total_companies(self):
        report = generate_readiness_report(self._sample_companies())
        self.assertEqual(report["total_companies"], 4)

    def test_compliant_count(self):
        report = generate_readiness_report(self._sample_companies())
        self.assertEqual(report["compliant"], 2)  # BigCo, MidCo

    def test_credentials_missing_count(self):
        report = generate_readiness_report(self._sample_companies())
        self.assertEqual(report["credentials_missing"], 1)  # SMECo

    def test_voluntary_count(self):
        report = generate_readiness_report(self._sample_companies())
        self.assertEqual(report["voluntary"], 1)  # MicroCo

    def test_compliance_rate(self):
        report = generate_readiness_report(self._sample_companies())
        # 2 compliant out of 3 mandatory = 66.67%
        self.assertAlmostEqual(report["compliance_rate"], 66.67, places=2)

    def test_action_required_list(self):
        report = generate_readiness_report(self._sample_companies())
        self.assertEqual(len(report["action_required"]), 1)
        self.assertEqual(report["action_required"][0]["company"], "SMECo")

    def test_empty_companies(self):
        report = generate_readiness_report([])
        self.assertEqual(report["total_companies"], 0)
        self.assertEqual(report["compliance_rate"], 100.0)

    def test_all_compliant(self):
        companies = [
            {"name": "A", FIELD_ANNUAL_REVENUE: 200_000_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
            {"name": "B", FIELD_ANNUAL_REVENUE: 50_000_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
        ]
        report = generate_readiness_report(companies)
        self.assertEqual(report["compliance_rate"], 100.0)
        self.assertEqual(len(report["action_required"]), 0)

    def test_all_voluntary(self):
        companies = [
            {"name": "A", FIELD_ANNUAL_REVENUE: 50_000},
            {"name": "B", FIELD_ANNUAL_REVENUE: 100_000},
        ]
        report = generate_readiness_report(companies)
        self.assertEqual(report["compliant"], 0)
        self.assertEqual(report["voluntary"], 2)
        self.assertEqual(report["compliance_rate"], 100.0)


# ---------------------------------------------------------------------------
# Phase Transition Detection Tests
# ---------------------------------------------------------------------------


class TestDetectPhaseTransition(FrappeTestCase):
    """Test detect_phase_transition() for revenue-change-driven phase changes."""

    def test_no_change_same_phase(self):
        result = detect_phase_transition(50_000_000, 60_000_000)
        self.assertIsNone(result)  # Both Phase 2

    def test_voluntary_to_phase_3(self):
        result = detect_phase_transition(100_000, 200_000)
        self.assertIsNotNone(result)
        self.assertEqual(result["old_phase"], VOLUNTARY_LABEL)
        self.assertEqual(result["new_phase"], PHASE_3_LABEL)
        self.assertTrue(result["now_mandatory"])
        self.assertTrue(result["is_upgrade"])

    def test_phase_3_to_phase_2(self):
        result = detect_phase_transition(300_000, 30_000_000)
        self.assertIsNotNone(result)
        self.assertEqual(result["old_phase"], PHASE_3_LABEL)
        self.assertEqual(result["new_phase"], PHASE_2_LABEL)
        self.assertTrue(result["is_upgrade"])
        self.assertFalse(result["now_mandatory"])  # Was already mandatory

    def test_phase_2_to_phase_1(self):
        result = detect_phase_transition(50_000_000, 200_000_000)
        self.assertIsNotNone(result)
        self.assertEqual(result["new_phase"], PHASE_1_LABEL)
        self.assertTrue(result["is_upgrade"])

    def test_phase_3_to_voluntary_downgrade(self):
        result = detect_phase_transition(200_000, 100_000)
        self.assertIsNotNone(result)
        self.assertEqual(result["old_phase"], PHASE_3_LABEL)
        self.assertEqual(result["new_phase"], VOLUNTARY_LABEL)
        self.assertTrue(result["is_downgrade"])

    def test_phase_1_to_phase_2_downgrade(self):
        result = detect_phase_transition(200_000_000, 50_000_000)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_downgrade"])

    def test_revenue_values_preserved(self):
        result = detect_phase_transition(100_000, 200_000)
        self.assertEqual(result["old_revenue"], 100_000.0)
        self.assertEqual(result["new_revenue"], 200_000.0)

    def test_none_to_positive(self):
        result = detect_phase_transition(None, 500_000)
        self.assertIsNotNone(result)
        self.assertEqual(result["old_phase"], VOLUNTARY_LABEL)
        self.assertEqual(result["new_phase"], PHASE_3_LABEL)


# ---------------------------------------------------------------------------
# Notification Builder Tests
# ---------------------------------------------------------------------------


class TestBuildPhaseTransitionAlert(FrappeTestCase):
    """Test build_phase_transition_alert() notification generation."""

    def test_none_transition_returns_none(self):
        result = build_phase_transition_alert("TestCo", None)
        self.assertIsNone(result)

    def test_now_mandatory_warning(self):
        transition = detect_phase_transition(100_000, 200_000)
        alert = build_phase_transition_alert("SMECo", transition)
        self.assertEqual(alert["severity"], "warning")
        self.assertIn("SMECo", alert["subject"])
        self.assertIn("MANDATORY", alert["message"])
        self.assertIn("MyInvois API credentials", alert["message"])

    def test_upgrade_info(self):
        transition = detect_phase_transition(300_000, 30_000_000)
        alert = build_phase_transition_alert("GrowCo", transition)
        self.assertEqual(alert["severity"], "info")
        self.assertEqual(alert["company"], "GrowCo")

    def test_downgrade_info(self):
        transition = detect_phase_transition(200_000, 100_000)
        alert = build_phase_transition_alert("ShrinkCo", transition)
        self.assertEqual(alert["severity"], "info")
        self.assertIn("verify", alert["message"].lower())

    def test_alert_has_phases(self):
        transition = detect_phase_transition(100_000, 200_000)
        alert = build_phase_transition_alert("TestCo", transition)
        self.assertEqual(alert["old_phase"], VOLUNTARY_LABEL)
        self.assertEqual(alert["new_phase"], PHASE_3_LABEL)


class TestBuildCredentialsWarning(FrappeTestCase):
    """Test build_credentials_warning() for missing credential alerts."""

    def test_mandatory_phase_returns_warning(self):
        result = build_credentials_warning("TestCo", PHASE_3_LABEL)
        self.assertIsNotNone(result)
        self.assertEqual(result["company"], "TestCo")
        self.assertEqual(result["severity"], "warning")
        self.assertIn("e-Invoice mandatory", result["message"])
        self.assertIn("LHDN Malaysia Setup", result["action"])

    def test_voluntary_returns_none(self):
        result = build_credentials_warning("TestCo", VOLUNTARY_LABEL)
        self.assertIsNone(result)

    def test_phase_1_returns_warning(self):
        result = build_credentials_warning("BigCo", PHASE_1_LABEL)
        self.assertIsNotNone(result)
        self.assertEqual(result["mandate_phase"], PHASE_1_LABEL)

    def test_phase_2_returns_warning(self):
        result = build_credentials_warning("MidCo", PHASE_2_LABEL)
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# Dashboard Summary Tests
# ---------------------------------------------------------------------------


class TestGenerateDashboardSummary(FrappeTestCase):
    """Test generate_dashboard_summary() aggregation and structure."""

    def _sample_companies(self):
        return [
            {"name": "BigCo", FIELD_ANNUAL_REVENUE: 200_000_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
            {"name": "MidCo", FIELD_ANNUAL_REVENUE: 50_000_000, FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: ""},
            {"name": "SMECo", FIELD_ANNUAL_REVENUE: 300_000, FIELD_CLIENT_ID: "id", FIELD_CLIENT_SECRET: "sec"},
            {"name": "MicroCo", FIELD_ANNUAL_REVENUE: 80_000, FIELD_CLIENT_ID: "", FIELD_CLIENT_SECRET: ""},
        ]

    def test_total_companies(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertEqual(summary["total_companies"], 4)

    def test_by_phase_counts(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertEqual(summary["by_phase"].get(PHASE_1_LABEL, 0), 1)
        self.assertEqual(summary["by_phase"].get(PHASE_2_LABEL, 0), 1)
        self.assertEqual(summary["by_phase"].get(PHASE_3_LABEL, 0), 1)
        self.assertEqual(summary["by_phase"].get(VOLUNTARY_LABEL, 0), 1)

    def test_by_status_counts(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertEqual(summary["by_status"].get(STATUS_COMPLIANT, 0), 2)
        self.assertEqual(summary["by_status"].get(STATUS_CREDENTIALS_MISSING, 0), 1)
        self.assertEqual(summary["by_status"].get(STATUS_VOLUNTARY, 0), 1)

    def test_mandatory_count(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertEqual(summary["mandatory_count"], 3)

    def test_voluntary_count(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertEqual(summary["voluntary_count"], 1)

    def test_compliance_rate(self):
        summary = generate_dashboard_summary(self._sample_companies())
        # 2 compliant out of 3 mandatory = 66.67%
        self.assertAlmostEqual(summary["compliance_rate"], 66.67, places=2)

    def test_action_items(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertEqual(len(summary["action_items"]), 1)
        self.assertEqual(summary["action_items"][0]["company"], "MidCo")

    def test_phase_4_note(self):
        summary = generate_dashboard_summary(self._sample_companies())
        self.assertIn("Phase 4", summary["phase_4_note"])
        self.assertIn("TBD", summary["phase_4_note"])

    def test_empty_companies(self):
        summary = generate_dashboard_summary([])
        self.assertEqual(summary["total_companies"], 0)
        self.assertEqual(summary["mandatory_count"], 0)
        self.assertEqual(summary["compliance_rate"], 100.0)
        self.assertEqual(len(summary["action_items"]), 0)
