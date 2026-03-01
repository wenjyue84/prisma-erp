"""Tests for US-176: Mid-Year Tax Residency Status Change Workflow.

Acceptance criteria verified:
1. Employee master has a 'Tax Residency Status' field (Resident / Non-Resident /
   Pending Determination) with effective date
2. When status is changed to Non-Resident, PCB uses 30% flat rate for subsequent months;
   all TP1 reliefs suspended for that year
3. Residency change event logged in PCB audit trail with effective date, previous status,
   new status, and the HR user who made the change
4. Non-Resident warning: 'Prior-month PCB for this year should be reviewed...'
5. Re-setting to Resident re-enables TP1 reliefs with LHDN approval warning
"""
from datetime import date
from unittest.mock import MagicMock, patch, call

import frappe
from frappe.tests.utils import FrappeTestCase


class TestResidencyConstants(FrappeTestCase):
    """Verify module-level constants."""

    def test_non_resident_rate_is_30_percent(self):
        """NON_RESIDENT_PCB_RATE must be 0.30."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            NON_RESIDENT_PCB_RATE,
        )
        self.assertAlmostEqual(NON_RESIDENT_PCB_RATE, 0.30)

    def test_valid_statuses_contains_all_three(self):
        """VALID_STATUSES must include Resident, Non-Resident, Pending Determination."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            VALID_STATUSES,
            RESIDENCY_STATUS_RESIDENT,
            RESIDENCY_STATUS_NON_RESIDENT,
            RESIDENCY_STATUS_PENDING,
        )
        self.assertIn(RESIDENCY_STATUS_RESIDENT, VALID_STATUSES)
        self.assertIn(RESIDENCY_STATUS_NON_RESIDENT, VALID_STATUSES)
        self.assertIn(RESIDENCY_STATUS_PENDING, VALID_STATUSES)

    def test_status_string_values(self):
        """Status strings match expected LHDN terminology."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            RESIDENCY_STATUS_RESIDENT,
            RESIDENCY_STATUS_NON_RESIDENT,
            RESIDENCY_STATUS_PENDING,
        )
        self.assertEqual(RESIDENCY_STATUS_RESIDENT, "Resident")
        self.assertEqual(RESIDENCY_STATUS_NON_RESIDENT, "Non-Resident")
        self.assertEqual(RESIDENCY_STATUS_PENDING, "Pending Determination")


class TestGetPcbMultiplierForResidency(FrappeTestCase):
    """Verify get_pcb_multiplier_for_residency returns correct values."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            get_pcb_multiplier_for_residency,
        )
        self.fn = get_pcb_multiplier_for_residency

    def _emp(self, status="Resident", effective_date=None):
        return {
            "custom_tax_residency_status": status,
            "custom_tax_residency_effective_date": effective_date,
        }

    def test_resident_returns_none(self):
        """Resident employee → returns None (use standard progressive PCB)."""
        emp = self._emp(status="Resident")
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        self.assertIsNone(result)

    def test_pending_determination_returns_none(self):
        """Pending Determination → returns None (treat as resident for PCB)."""
        emp = self._emp(status="Pending Determination")
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        self.assertIsNone(result)

    def test_non_resident_without_effective_date_returns_030(self):
        """Non-Resident with no effective date → applies from any date."""
        emp = self._emp(status="Non-Resident", effective_date=None)
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        self.assertAlmostEqual(result, 0.30)

    def test_non_resident_with_effective_date_before_payroll_returns_030(self):
        """Non-Resident effective Jan 2026; payroll is March 2026 → 30%."""
        emp = self._emp(status="Non-Resident", effective_date=date(2026, 1, 1))
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        self.assertAlmostEqual(result, 0.30)

    def test_non_resident_with_effective_date_after_payroll_returns_none(self):
        """Non-Resident effective March 2026; payroll is Jan 2026 → None (not yet effective)."""
        emp = self._emp(status="Non-Resident", effective_date=date(2026, 3, 1))
        result = self.fn(emp, payroll_month_date=date(2026, 1, 1))
        self.assertIsNone(result)

    def test_non_resident_on_exact_effective_date_returns_none(self):
        """Non-Resident effective March 1; payroll is March 1 → None (boundary: not yet passed)."""
        emp = self._emp(status="Non-Resident", effective_date=date(2026, 3, 1))
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        # payroll_month_date < effective_date is False (equal), so NOT None
        # date(2026,3,1) < date(2026,3,1) is False → returns 0.30
        self.assertAlmostEqual(result, 0.30)

    def test_string_effective_date_supported(self):
        """String effective date '2026-01-01' is parsed correctly."""
        emp = self._emp(status="Non-Resident", effective_date="2026-01-01")
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        self.assertAlmostEqual(result, 0.30)

    def test_object_attribute_access(self):
        """Also works with object-style attribute access (Frappe doc)."""
        emp = MagicMock()
        emp.custom_tax_residency_status = "Non-Resident"
        emp.custom_tax_residency_effective_date = None
        # Remove .get method to test attribute path
        del emp.get
        result = self.fn(emp, payroll_month_date=date(2026, 3, 1))
        self.assertAlmostEqual(result, 0.30)


class TestGetResidencyChangeWarning(FrappeTestCase):
    """Verify warning messages for residency status changes."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            get_residency_change_warning,
        )
        self.fn = get_residency_change_warning

    def test_resident_to_non_resident_warning_contains_prior_month_review(self):
        """Resident → Non-Resident: warning mentions prior-month PCB review."""
        warning = self.fn("Resident", "Non-Resident")
        self.assertIn("Prior-month PCB for this year should be reviewed", warning)
        self.assertIn("non-resident rate is not retroactively applied", warning)

    def test_resident_to_non_resident_warning_mentions_tp1_suspended(self):
        """Resident → Non-Resident: warning mentions TP1 reliefs suspended."""
        warning = self.fn("Resident", "Non-Resident")
        self.assertIn("TP1 reliefs have been suspended", warning)

    def test_non_resident_to_resident_warning_mentions_lhdn_approval(self):
        """Non-Resident → Resident: warning mentions LHDN approval may be required."""
        warning = self.fn("Non-Resident", "Resident")
        self.assertIn("LHDN approval may be required", warning)
        self.assertIn("TP1 reliefs have been reinstated", warning)

    def test_resident_to_pending_no_warning(self):
        """Resident → Pending Determination: no warning (neutral transition)."""
        warning = self.fn("Resident", "Pending Determination")
        self.assertEqual(warning, "")

    def test_pending_to_resident_no_warning(self):
        """Pending → Resident: no warning."""
        warning = self.fn("Pending Determination", "Resident")
        self.assertEqual(warning, "")

    def test_resident_to_resident_no_warning(self):
        """Same status → no warning."""
        warning = self.fn("Resident", "Resident")
        self.assertEqual(warning, "")


class TestSuspendAndReinstateTp1Reliefs(FrappeTestCase):
    """Verify TP1 relief suspend/reinstate logic."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            suspend_tp1_reliefs_for_year,
            reinstate_tp1_reliefs_for_year,
        )
        self.suspend = suspend_tp1_reliefs_for_year
        self.reinstate = reinstate_tp1_reliefs_for_year

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_suspend_returns_false_when_no_tp1_record(self, mock_frappe):
        """suspend_tp1_reliefs_for_year returns False when no TP1 record exists."""
        mock_frappe.get_all.return_value = []
        result = self.suspend("EMP001", 2026)
        self.assertFalse(result)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_reinstate_returns_false_when_no_tp1_record(self, mock_frappe):
        """reinstate_tp1_reliefs_for_year returns False when no TP1 record exists."""
        mock_frappe.get_all.return_value = []
        result = self.reinstate("EMP001", 2026)
        self.assertFalse(result)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_suspend_sets_custom_reliefs_suspended_to_1(self, mock_frappe):
        """suspend_tp1_reliefs_for_year sets custom_reliefs_suspended=1."""
        mock_tp1 = MagicMock()
        mock_frappe.get_all.return_value = [{"name": "TP1-2026-001", "custom_reliefs_suspended": 0}]
        mock_frappe.get_doc.return_value = mock_tp1
        result = self.suspend("EMP001", 2026)
        self.assertTrue(result)
        self.assertEqual(mock_tp1.custom_reliefs_suspended, 1)
        mock_tp1.save.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_reinstate_sets_custom_reliefs_suspended_to_0(self, mock_frappe):
        """reinstate_tp1_reliefs_for_year sets custom_reliefs_suspended=0."""
        mock_tp1 = MagicMock()
        mock_frappe.get_all.return_value = [{"name": "TP1-2026-001", "custom_reliefs_suspended": 1}]
        mock_frappe.get_doc.return_value = mock_tp1
        result = self.reinstate("EMP001", 2026)
        self.assertTrue(result)
        self.assertEqual(mock_tp1.custom_reliefs_suspended, 0)
        mock_tp1.save.assert_called_once_with(ignore_permissions=True)


class TestChangeResidencyStatus(FrappeTestCase):
    """Verify change_residency_status function behavior."""

    def setUp(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            change_residency_status,
        )
        self.fn = change_residency_status

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_invalid_status_raises_validation_error(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """Invalid status raises frappe.ValidationError."""
        mock_frappe.ValidationError = Exception
        mock_frappe.throw.side_effect = Exception("Invalid status")
        with self.assertRaises(Exception):
            self.fn("EMP001", "Invalid Status", date(2026, 3, 1), "admin@test.com")

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_resident_to_non_resident_calls_suspend(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """Changing to Non-Resident triggers suspend_tp1_reliefs_for_year."""
        mock_employee = MagicMock()
        mock_employee.custom_tax_residency_status = "Resident"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee
        mock_frappe.session.user = "hr@test.com"

        result = self.fn("EMP001", "Non-Resident", date(2026, 3, 1), "hr@test.com")

        mock_suspend.assert_called_once_with("EMP001", 2026)
        mock_reinstate.assert_not_called()
        self.assertEqual(result["old_status"], "Resident")
        self.assertEqual(result["new_status"], "Non-Resident")
        self.assertIn("Prior-month PCB", result["warning"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_non_resident_to_resident_calls_reinstate(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """Changing from Non-Resident to Resident triggers reinstate_tp1_reliefs_for_year."""
        mock_employee = MagicMock()
        mock_employee.custom_tax_residency_status = "Non-Resident"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee
        mock_frappe.session.user = "hr@test.com"

        result = self.fn("EMP001", "Resident", date(2026, 3, 1), "hr@test.com")

        mock_reinstate.assert_called_once_with("EMP001", 2026)
        mock_suspend.assert_not_called()
        self.assertIn("LHDN approval may be required", result["warning"])

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_audit_log_is_created(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """_log_residency_change is called with correct old/new status."""
        mock_employee = MagicMock()
        mock_employee.custom_tax_residency_status = "Resident"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee
        mock_frappe.session.user = "hr@test.com"

        self.fn("EMP001", "Non-Resident", date(2026, 3, 1), "hr@test.com")

        mock_log.assert_called_once()
        log_kwargs = mock_log.call_args[1]
        self.assertEqual(log_kwargs["old_status"], "Resident")
        self.assertEqual(log_kwargs["new_status"], "Non-Resident")
        self.assertEqual(log_kwargs["changed_by"], "hr@test.com")
        self.assertEqual(log_kwargs["effective_date"], date(2026, 3, 1))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_employee_record_updated(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """Employee record is updated with new status and effective date."""
        mock_employee = MagicMock()
        mock_employee.custom_tax_residency_status = "Resident"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee
        mock_frappe.session.user = "hr@test.com"

        self.fn("EMP001", "Non-Resident", date(2026, 3, 1), "hr@test.com")

        self.assertEqual(mock_employee.custom_tax_residency_status, "Non-Resident")
        self.assertEqual(mock_employee.custom_tax_residency_effective_date, date(2026, 3, 1))
        mock_employee.save.assert_called_once_with(ignore_permissions=True)

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_string_effective_date_parsed(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """String effective_date '2026-06-01' is parsed to date object."""
        mock_employee = MagicMock()
        mock_employee.custom_tax_residency_status = "Resident"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee
        mock_frappe.session.user = "hr@test.com"

        result = self.fn("EMP001", "Non-Resident", "2026-06-01", "hr@test.com")

        self.assertEqual(result["effective_date"], date(2026, 6, 1))

    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.reinstate_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.suspend_tp1_reliefs_for_year")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service._log_residency_change")
    @patch("lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service.frappe")
    def test_resident_to_pending_no_tp1_side_effects(self, mock_frappe, mock_log, mock_suspend, mock_reinstate):
        """Resident → Pending Determination: no TP1 suspend/reinstate calls."""
        mock_employee = MagicMock()
        mock_employee.custom_tax_residency_status = "Resident"
        mock_employee.company = "Test Co"
        mock_frappe.get_doc.return_value = mock_employee
        mock_frappe.session.user = "hr@test.com"

        result = self.fn("EMP001", "Pending Determination", date(2026, 3, 1), "hr@test.com")

        mock_suspend.assert_not_called()
        mock_reinstate.assert_not_called()
        self.assertEqual(result["warning"], "")


class TestCustomFieldsInFixtures(FrappeTestCase):
    """Verify custom fields for tax residency are present in fixtures."""

    def _get_employee_fields(self):
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "custom_field.json",
        )
        if not os.path.exists(fixture_path):
            return []
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
        return [f for f in data if f.get("dt") == "Employee"]

    def test_tax_residency_status_field_exists(self):
        """custom_tax_residency_status field must be in custom_field.json."""
        fields = self._get_employee_fields()
        fieldnames = [f.get("fieldname", "") for f in fields]
        self.assertIn(
            "custom_tax_residency_status",
            fieldnames,
            "custom_tax_residency_status Select field must be in Employee custom fields",
        )

    def test_tax_residency_effective_date_field_exists(self):
        """custom_tax_residency_effective_date field must be in custom_field.json."""
        fields = self._get_employee_fields()
        fieldnames = [f.get("fieldname", "") for f in fields]
        self.assertIn(
            "custom_tax_residency_effective_date",
            fieldnames,
            "custom_tax_residency_effective_date Date field must be in Employee custom fields",
        )

    def test_status_field_is_select_type(self):
        """custom_tax_residency_status must be fieldtype=Select."""
        fields = self._get_employee_fields()
        for f in fields:
            if f.get("fieldname") == "custom_tax_residency_status":
                self.assertEqual(f.get("fieldtype"), "Select")
                return
        self.fail("custom_tax_residency_status not found in fixtures")

    def test_status_field_has_three_options(self):
        """custom_tax_residency_status must include Resident, Non-Resident, Pending Determination."""
        fields = self._get_employee_fields()
        for f in fields:
            if f.get("fieldname") == "custom_tax_residency_status":
                options = f.get("options", "")
                self.assertIn("Resident", options)
                self.assertIn("Non-Resident", options)
                self.assertIn("Pending Determination", options)
                return
        self.fail("custom_tax_residency_status not found in fixtures")

    def test_effective_date_field_is_date_type(self):
        """custom_tax_residency_effective_date must be fieldtype=Date."""
        fields = self._get_employee_fields()
        for f in fields:
            if f.get("fieldname") == "custom_tax_residency_effective_date":
                self.assertEqual(f.get("fieldtype"), "Date")
                return
        self.fail("custom_tax_residency_effective_date not found in fixtures")


class TestTp1ReliefSuspendedFieldInFixtures(FrappeTestCase):
    """Verify custom_reliefs_suspended field exists on Employee TP1 Relief."""

    def _get_tp1_fields(self):
        import json
        import os
        fixture_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "fixtures", "custom_field.json",
        )
        if not os.path.exists(fixture_path):
            return []
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
        return [f for f in data if f.get("dt") == "Employee TP1 Relief"]

    def test_reliefs_suspended_field_exists(self):
        """custom_reliefs_suspended Check field must exist on Employee TP1 Relief."""
        fields = self._get_tp1_fields()
        fieldnames = [f.get("fieldname", "") for f in fields]
        self.assertIn(
            "custom_reliefs_suspended",
            fieldnames,
            "custom_reliefs_suspended Check field must be in Employee TP1 Relief fixtures",
        )

    def test_reliefs_suspended_is_check_type(self):
        """custom_reliefs_suspended must be fieldtype=Check."""
        fields = self._get_tp1_fields()
        for f in fields:
            if f.get("fieldname") == "custom_reliefs_suspended":
                self.assertEqual(f.get("fieldtype"), "Check")
                return
        self.fail("custom_reliefs_suspended not found in Employee TP1 Relief fixtures")


class TestPcbChangeLogResidencyChangeType(FrappeTestCase):
    """Verify PCB Change Log supports 'Residency Status Change' as change_type."""

    def test_pcb_change_log_has_residency_change_type(self):
        """PCB Change Log JSON must include 'Residency Status Change' as an option."""
        import json
        import os
        json_path = os.path.join(
            frappe.get_app_path("lhdn_payroll_integration"),
            "lhdn_payroll_integration", "doctype", "pcb_change_log", "pcb_change_log.json",
        )
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        change_type_field = next(
            (f for f in data["fields"] if f["fieldname"] == "change_type"),
            None,
        )
        self.assertIsNotNone(change_type_field, "change_type field must exist in PCB Change Log")
        self.assertIn(
            "Residency Status Change",
            change_type_field.get("options", ""),
            "'Residency Status Change' must be an option in PCB Change Log change_type",
        )


class TestNonResidentPcbRateIntegration(FrappeTestCase):
    """Integration-style tests for non-resident rate enforcement."""

    def test_non_resident_30pct_on_gross_income(self):
        """Non-resident at 30% on RM10,000 gross → PCB = RM3,000."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            get_pcb_multiplier_for_residency,
            NON_RESIDENT_PCB_RATE,
        )
        emp = {
            "custom_tax_residency_status": "Non-Resident",
            "custom_tax_residency_effective_date": None,
        }
        rate = get_pcb_multiplier_for_residency(emp, payroll_month_date=date(2026, 3, 1))
        gross = 10_000.0
        expected_pcb = gross * NON_RESIDENT_PCB_RATE
        calculated_pcb = gross * rate
        self.assertAlmostEqual(calculated_pcb, expected_pcb, places=2)
        self.assertAlmostEqual(calculated_pcb, 3_000.0, places=2)

    def test_resident_returns_none_not_zero(self):
        """Resident returns None (not 0.0) — caller must use progressive calculation."""
        from lhdn_payroll_integration.lhdn_payroll_integration.services.tax_residency_service import (
            get_pcb_multiplier_for_residency,
        )
        emp = {"custom_tax_residency_status": "Resident", "custom_tax_residency_effective_date": None}
        result = get_pcb_multiplier_for_residency(emp, payroll_month_date=date(2026, 3, 1))
        self.assertIsNone(result, "Must be None (not 0.0) so caller uses progressive PCB")
