"""Tests for US-204: EP Category Internship Obligation Tracker (1:3 Policy).

Covers all 6 acceptance criteria:
  AC1 - Employee stores EP category, approval reference, approval date
  AC2 - Quota calculation: sum(Cat I × 3 + Cat II × 2 + Cat III × 1), 2% headcount cap
  AC3 - Internship Placement doctype with required fields
  AC4 - Stipend validation (RM600/month degree/master/DLKM; RM500/month diploma/SKM/cert)
  AC5 - Compliance summary: quota vs fulfilled, gap highlighted
  AC6 - EP renewal alert 60 days before expiry when quota unfulfilled
"""
from unittest.mock import patch, MagicMock, call
from frappe.tests.utils import FrappeTestCase


class TestEpCategoryCustomFields(FrappeTestCase):
    """AC1 — Employee stores EP category, approval reference number, and approval date."""

    def test_ep_category_field_exists_on_employee(self):
        """custom_ep_category field exists in Employee DocType custom fields."""
        fields = frappe.get_all(
            "Custom Field",
            filters={"dt": "Employee", "fieldname": "custom_ep_category"},
            fields=["fieldname", "fieldtype", "options"],
        )
        self.assertTrue(len(fields) > 0, "custom_ep_category custom field missing on Employee")

    def test_ep_category_has_correct_options(self):
        """EP category select field has Cat I / Cat II / Cat III options."""
        fields = frappe.get_all(
            "Custom Field",
            filters={"dt": "Employee", "fieldname": "custom_ep_category"},
            fields=["options"],
        )
        self.assertTrue(len(fields) > 0)
        options = fields[0].get("options") or ""
        self.assertIn("Cat I", options)
        self.assertIn("Cat II", options)
        self.assertIn("Cat III", options)

    def test_ep_number_field_exists_on_employee(self):
        """custom_ep_number (EP approval reference) field exists on Employee."""
        fields = frappe.get_all(
            "Custom Field",
            filters={"dt": "Employee", "fieldname": "custom_ep_number"},
            fields=["fieldname"],
        )
        self.assertTrue(len(fields) > 0, "custom_ep_number custom field missing on Employee")

    def test_ep_expiry_date_field_exists_on_employee(self):
        """custom_ep_expiry_date field exists on Employee."""
        fields = frappe.get_all(
            "Custom Field",
            filters={"dt": "Employee", "fieldname": "custom_ep_expiry_date"},
            fields=["fieldname"],
        )
        self.assertTrue(len(fields) > 0, "custom_ep_expiry_date custom field missing on Employee")


class TestInternshipQuotaCalculation(FrappeTestCase):
    """AC2 — Quota = sum(EP Cat I × 3 + Cat II × 2 + Cat III × 1), capped at 2% headcount."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service import (
            compute_internship_quota,
            QUOTA_PER_EP_CAT,
            HEADCOUNT_CAP_RATE,
        )
        self.compute = compute_internship_quota
        self.quota_map = QUOTA_PER_EP_CAT
        self.cap_rate = HEADCOUNT_CAP_RATE

    def test_quota_constants_correct(self):
        """Multipliers: Cat I=3, Cat II=2, Cat III=1."""
        self.assertEqual(self.quota_map["Cat I"], 3)
        self.assertEqual(self.quota_map["Cat II"], 2)
        self.assertEqual(self.quota_map["Cat III"], 1)

    def test_headcount_cap_rate_is_2_percent(self):
        """Headcount cap rate is 2%."""
        self.assertAlmostEqual(self.cap_rate, 0.02, places=4)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_quota_calculation_mixed_categories(self, mock_frappe):
        """1 Cat I + 2 Cat II + 1 Cat III = 3 + 4 + 1 = 8 raw; 500 employees → cap=10."""
        def mock_count(doctype, filters):
            if filters.get("custom_ep_category") == "Cat I":
                return 1
            elif filters.get("custom_ep_category") == "Cat II":
                return 2
            elif filters.get("custom_ep_category") == "Cat III":
                return 1
            else:
                return 500  # total headcount

        mock_frappe.db.count.side_effect = mock_count
        result = self.compute("Test Co")

        self.assertEqual(result["raw_required"], 8)  # 1×3 + 2×2 + 1×1
        self.assertEqual(result["headcount"], 500)
        self.assertEqual(result["headcount_cap"], 10)  # int(500 × 0.02) = 10
        self.assertEqual(result["effective_required"], 8)  # min(8, 10) = 8

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_headcount_cap_limits_quota(self, mock_frappe):
        """Many EPs in a small company: cap kicks in."""
        def mock_count(doctype, filters):
            if filters.get("custom_ep_category") == "Cat I":
                return 10
            elif filters.get("custom_ep_category") == "Cat II":
                return 5
            elif filters.get("custom_ep_category") == "Cat III":
                return 3
            else:
                return 50  # 50 total employees

        mock_frappe.db.count.side_effect = mock_count
        result = self.compute("Small Co")

        # raw = 10×3 + 5×2 + 3×1 = 30 + 10 + 3 = 43
        # cap = int(50 × 0.02) = 1
        self.assertEqual(result["raw_required"], 43)
        self.assertEqual(result["headcount_cap"], 1)
        self.assertEqual(result["effective_required"], 1)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_no_ep_workers_returns_zero_quota(self, mock_frappe):
        """No EP holders → zero internship requirement."""
        mock_frappe.db.count.return_value = 0
        result = self.compute("Test Co")
        self.assertEqual(result["raw_required"], 0)
        self.assertEqual(result["effective_required"], 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_result_has_ep_breakdown(self, mock_frappe):
        """Result includes ep_breakdown dict with per-category counts."""
        mock_frappe.db.count.return_value = 0
        result = self.compute("Test Co")
        self.assertIn("ep_breakdown", result)
        self.assertIn("Cat I", result["ep_breakdown"])
        self.assertIn("Cat II", result["ep_breakdown"])
        self.assertIn("Cat III", result["ep_breakdown"])


class TestInternshipPlacementDoctype(FrappeTestCase):
    """AC3 — Internship Placement doctype with required fields."""

    def test_internship_placement_doctype_exists(self):
        """Internship Placement DocType is registered in Frappe."""
        exists = frappe.db.exists("DocType", "Internship Placement")
        self.assertTrue(exists, "Internship Placement DocType not found")

    def test_required_fields_exist(self):
        """All required fields present on Internship Placement."""
        meta = frappe.get_meta("Internship Placement")
        fieldnames = [f.fieldname for f in meta.fields]
        required = [
            "intern_name",
            "qualification_level",
            "talentcorp_reference",
            "start_date",
            "end_date",
            "monthly_stipend",
            "status",
            "company",
        ]
        for field in required:
            self.assertIn(field, fieldnames, f"Field '{field}' missing from Internship Placement")

    def test_qualification_level_options(self):
        """qualification_level has all required options."""
        meta = frappe.get_meta("Internship Placement")
        ql_field = next((f for f in meta.fields if f.fieldname == "qualification_level"), None)
        self.assertIsNotNone(ql_field)
        options = ql_field.options or ""
        for qual in ["Degree", "Master", "DLKM", "Diploma", "SKM", "Certificate"]:
            self.assertIn(qual, options, f"Missing qualification option: {qual}")

    def test_status_options(self):
        """Status field has Pending / Active / Completed options."""
        meta = frappe.get_meta("Internship Placement")
        status_field = next((f for f in meta.fields if f.fieldname == "status"), None)
        self.assertIsNotNone(status_field)
        options = status_field.options or ""
        for s in ["Pending", "Active", "Completed"]:
            self.assertIn(s, options)


class TestStipendValidation(FrappeTestCase):
    """AC4 — Stipend validation: RM600/month for degree/master/DLKM; RM500/month for diploma."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service import (
            validate_intern_stipend,
            STIPEND_MIN,
        )
        self.validate = validate_intern_stipend
        self.minimums = STIPEND_MIN

    def test_degree_minimum_is_600(self):
        self.assertAlmostEqual(self.minimums["Degree"], 600.0, places=2)

    def test_master_minimum_is_600(self):
        self.assertAlmostEqual(self.minimums["Master"], 600.0, places=2)

    def test_dlkm_minimum_is_600(self):
        self.assertAlmostEqual(self.minimums["DLKM"], 600.0, places=2)

    def test_diploma_minimum_is_500(self):
        self.assertAlmostEqual(self.minimums["Diploma"], 500.0, places=2)

    def test_skm_minimum_is_500(self):
        self.assertAlmostEqual(self.minimums["SKM"], 500.0, places=2)

    def test_certificate_minimum_is_500(self):
        self.assertAlmostEqual(self.minimums["Certificate"], 500.0, places=2)

    def test_valid_degree_stipend(self):
        result = self.validate("Degree", 600.0)
        self.assertTrue(result["valid"])
        self.assertEqual(result["shortfall"], 0.0)

    def test_invalid_degree_stipend_below_minimum(self):
        result = self.validate("Degree", 500.0)
        self.assertFalse(result["valid"])
        self.assertAlmostEqual(result["shortfall"], 100.0, places=2)

    def test_valid_diploma_stipend(self):
        result = self.validate("Diploma", 500.0)
        self.assertTrue(result["valid"])

    def test_invalid_diploma_stipend(self):
        result = self.validate("Diploma", 400.0)
        self.assertFalse(result["valid"])
        self.assertAlmostEqual(result["shortfall"], 100.0, places=2)

    def test_above_minimum_is_valid(self):
        result = self.validate("Master", 800.0)
        self.assertTrue(result["valid"])
        self.assertEqual(result["shortfall"], 0.0)

    def test_unknown_qualification_returns_invalid(self):
        result = self.validate("PhD", 1000.0)
        self.assertFalse(result["valid"])
        self.assertIn("Unknown", result["message"])

    def test_zero_stipend_is_invalid_for_degree(self):
        result = self.validate("Degree", 0.0)
        self.assertFalse(result["valid"])
        self.assertAlmostEqual(result["shortfall"], 600.0, places=2)

    def test_result_includes_min_required_field(self):
        result = self.validate("Diploma", 550.0)
        self.assertIn("min_required", result)
        self.assertAlmostEqual(result["min_required"], 500.0, places=2)


class TestComplianceSummary(FrappeTestCase):
    """AC5 — Compliance summary: quota vs fulfilled, gap highlighted."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service import (
            get_compliance_summary,
        )
        self.get_summary = get_compliance_summary

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_compliant_when_gap_is_zero(self, mock_frappe):
        """Compliant=True when fulfilled >= quota_required."""
        # compute_internship_quota: 1 Cat I → 3 raw; 200 headcount → cap=4; effective=3
        def mock_count(doctype, filters):
            if filters.get("custom_ep_category") == "Cat I":
                return 1
            elif filters.get("custom_ep_category") == "Cat II":
                return 0
            elif filters.get("custom_ep_category") == "Cat III":
                return 0
            elif "end_date" in filters and "status" in filters:
                return 3  # 3 completed placements
            else:
                return 200  # headcount

        mock_frappe.db.count.side_effect = mock_count
        result = self.get_summary("Test Co", 2026)

        self.assertEqual(result["quota_required"], 3)
        self.assertEqual(result["fulfilled"], 3)
        self.assertEqual(result["gap"], 0)
        self.assertTrue(result["compliant"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_gap_highlighted_when_unfulfilled(self, mock_frappe):
        """Gap > 0 and compliant=False when placements insufficient."""
        def mock_count(doctype, filters):
            if filters.get("custom_ep_category") == "Cat I":
                return 2
            elif filters.get("custom_ep_category") == "Cat II":
                return 1
            elif filters.get("custom_ep_category") == "Cat III":
                return 0
            elif "end_date" in filters and "status" in filters:
                return 2  # only 2 of 8 fulfilled
            else:
                return 500  # headcount

        mock_frappe.db.count.side_effect = mock_count
        result = self.get_summary("Test Co", 2026)

        # raw = 2×3 + 1×2 = 8; cap = int(500×0.02) = 10; effective = 8
        self.assertEqual(result["quota_required"], 8)
        self.assertEqual(result["fulfilled"], 2)
        self.assertEqual(result["gap"], 6)
        self.assertFalse(result["compliant"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_summary_has_ep_breakdown(self, mock_frappe):
        """Summary includes ep_breakdown for dashboard display."""
        mock_frappe.db.count.return_value = 0
        result = self.get_summary("Test Co", 2026)
        self.assertIn("ep_breakdown", result)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_gap_is_never_negative(self, mock_frappe):
        """Gap is clamped to 0 when fulfilled exceeds quota."""
        def mock_count(doctype, filters):
            if "end_date" in filters and "status" in filters:
                return 10  # over-fulfilled
            elif filters.get("custom_ep_category") in ("Cat I", "Cat II", "Cat III"):
                return 1
            else:
                return 100
        mock_frappe.db.count.side_effect = mock_count
        result = self.get_summary("Test Co", 2026)
        self.assertGreaterEqual(result["gap"], 0)


class TestEpRenewalAlerts(FrappeTestCase):
    """AC6 — Alert triggered 60 days before EP renewal when quota not met."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service import (
            check_ep_renewal_alerts,
            EP_RENEWAL_ALERT_DAYS,
        )
        self.check_alerts = check_ep_renewal_alerts
        self.alert_days = EP_RENEWAL_ALERT_DAYS

    def test_alert_window_is_60_days(self):
        self.assertEqual(self.alert_days, 60)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_alert_triggered_when_ep_expiring_and_quota_unmet(self, mock_frappe):
        """EP expiring within 60 days + gap > 0 → alert returned."""
        # EP holder expiring in 30 days
        mock_ep_holder = {
            "name": "EMP-001",
            "employee_name": "John Smith",
            "custom_ep_category": "Cat I",
            "custom_ep_expiry_date": "2026-04-01",
        }
        mock_frappe.get_all.return_value = [mock_ep_holder]

        # get_compliance_summary needs frappe.db.count
        def mock_count(doctype, filters):
            if "end_date" in filters and "status" in filters:
                return 0  # 0 fulfilled
            elif filters.get("custom_ep_category") == "Cat I":
                return 1
            elif filters.get("custom_ep_category") in ("Cat II", "Cat III"):
                return 0
            else:
                return 100
        mock_frappe.db.count.side_effect = mock_count

        alerts = self.check_alerts("Test Co", as_of_date="2026-03-01")
        self.assertGreater(len(alerts), 0)
        alert = alerts[0]
        self.assertEqual(alert["employee"], "EMP-001")
        self.assertIn("quota_gap", alert)
        self.assertGreater(alert["quota_gap"], 0)
        self.assertIn("message", alert)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_no_alert_when_quota_fully_met(self, mock_frappe):
        """No alert when internship quota is fully fulfilled."""
        mock_ep_holder = {
            "name": "EMP-002",
            "employee_name": "Jane Doe",
            "custom_ep_category": "Cat II",
            "custom_ep_expiry_date": "2026-04-01",
        }
        mock_frappe.get_all.return_value = [mock_ep_holder]

        def mock_count(doctype, filters):
            if "end_date" in filters and "status" in filters:
                return 10  # quota fully met
            elif filters.get("custom_ep_category") in ("Cat I", "Cat II", "Cat III"):
                return 1
            else:
                return 200
        mock_frappe.db.count.side_effect = mock_count

        alerts = self.check_alerts("Test Co", as_of_date="2026-03-01")
        self.assertEqual(len(alerts), 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_no_alert_when_no_ep_holders_expiring(self, mock_frappe):
        """No alert when no EP holders have upcoming expiry."""
        mock_frappe.get_all.return_value = []
        mock_frappe.db.count.return_value = 0
        alerts = self.check_alerts("Test Co", as_of_date="2026-03-01")
        self.assertEqual(len(alerts), 0)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service.frappe")
    def test_alert_includes_days_remaining(self, mock_frappe):
        """Alert dict includes days_remaining field."""
        mock_ep_holder = {
            "name": "EMP-003",
            "employee_name": "Ahmad bin Ali",
            "custom_ep_category": "Cat III",
            "custom_ep_expiry_date": "2026-04-15",
        }
        mock_frappe.get_all.return_value = [mock_ep_holder]

        def mock_count(doctype, filters):
            if "end_date" in filters and "status" in filters:
                return 0
            elif filters.get("custom_ep_category") == "Cat III":
                return 1
            elif filters.get("custom_ep_category") in ("Cat I", "Cat II"):
                return 0
            else:
                return 50
        mock_frappe.db.count.side_effect = mock_count

        alerts = self.check_alerts("Test Co", as_of_date="2026-03-01")
        if alerts:
            self.assertIn("days_remaining", alerts[0])
            self.assertGreater(alerts[0]["days_remaining"], 0)


import frappe
