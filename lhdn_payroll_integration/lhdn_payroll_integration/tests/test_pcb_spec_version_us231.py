"""Tests for US-231: LHDN PCB 2026 Specification Annual Update Checklist and Version Flag.

Acceptance criteria:
  1. LHDN Payroll Settings Single DocType has pcb_specification_version and
     pcb_specification_url fields.
  2. get_spec_changelog() returns a non-empty list of changed parameters when
     switching between known spec versions (e.g. 2025 → 2026).
  3. get_active_pcb_spec_version() reads from LHDN Payroll Settings and PCB
     calculate_pcb() uses the active spec year when assessment_year is None.
  4. get_pcb_spec_version_label() returns a human-readable audit trail label
     matching the active spec year (e.g. "2025 Spec Compliant").
  5. check_january_spec_alert() function exists and is callable without error
     in non-January months (no-op path).
"""
import datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_spec_service import (
    check_january_spec_alert,
    get_active_pcb_spec_version,
    get_pcb_spec_version_label,
    get_spec_changelog,
    get_spec_url_for_version,
)


# ---------------------------------------------------------------------------
# AC1 — LHDN Payroll Settings DocType structure
# ---------------------------------------------------------------------------


class TestLHDNPayrollSettingsDocType(FrappeTestCase):
    """LHDN Payroll Settings Single DocType must exist with correct fields."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.meta = frappe.get_meta("LHDN Payroll Settings")

    def test_doctype_exists(self):
        """LHDN Payroll Settings DocType must exist."""
        self.assertIsNotNone(self.meta)

    def test_doctype_is_single(self):
        """LHDN Payroll Settings must be a Single DocType."""
        self.assertTrue(
            self.meta.issingle,
            "LHDN Payroll Settings must be a Single DocType (issingle=1)",
        )

    def test_pcb_specification_version_field_exists(self):
        """pcb_specification_version Select field must exist."""
        field = self.meta.get_field("pcb_specification_version")
        self.assertIsNotNone(
            field,
            "pcb_specification_version field missing from LHDN Payroll Settings",
        )
        self.assertEqual(
            field.fieldtype,
            "Select",
            "pcb_specification_version must be a Select field",
        )

    def test_pcb_specification_version_options(self):
        """pcb_specification_version must include 2025 and 2026 as options."""
        field = self.meta.get_field("pcb_specification_version")
        options = field.options or ""
        self.assertIn("2025", options)
        self.assertIn("2026", options)

    def test_pcb_specification_url_field_exists(self):
        """pcb_specification_url Data field must exist."""
        field = self.meta.get_field("pcb_specification_url")
        self.assertIsNotNone(
            field,
            "pcb_specification_url field missing from LHDN Payroll Settings",
        )
        self.assertEqual(field.fieldtype, "Data")

    def test_last_confirmed_date_field_exists(self):
        """last_confirmed_date Date field must exist for HR confirmation tracking."""
        field = self.meta.get_field("last_confirmed_date")
        self.assertIsNotNone(
            field,
            "last_confirmed_date field missing — HR must confirm version annually",
        )

    def test_module_is_lhdn_payroll_integration(self):
        """Module must be 'LHDN Payroll Integration'."""
        self.assertEqual(
            self.meta.module,
            "LHDN Payroll Integration",
        )


# ---------------------------------------------------------------------------
# AC2 — Spec changelog (checklist) between versions
# ---------------------------------------------------------------------------


class TestSpecChangelog(FrappeTestCase):
    """get_spec_changelog() must return changed parameters between spec years."""

    def test_changelog_2024_to_2025_is_non_empty(self):
        """YA2024 → YA2025 changelog must list changed parameters."""
        changes = get_spec_changelog(2024, 2025)
        self.assertIsInstance(changes, list)
        self.assertGreater(len(changes), 0, "2024→2025 changelog must have entries")

    def test_changelog_2025_to_2026_is_non_empty(self):
        """YA2025 → YA2026 changelog must list changed parameters."""
        changes = get_spec_changelog(2025, 2026)
        self.assertIsInstance(changes, list)
        self.assertGreater(len(changes), 0, "2025→2026 changelog must have entries")

    def test_changelog_2025_to_2026_mentions_budget_2026(self):
        """YA2025 → YA2026 changelog must mention Budget 2026 items."""
        changes = get_spec_changelog(2025, 2026)
        combined = " ".join(changes).lower()
        self.assertIn("2026", combined, "Changelog must reference YA2026 / Budget 2026")

    def test_changelog_returns_list_of_strings(self):
        """Each changelog item must be a non-empty string."""
        for year_pair in [(2024, 2025), (2025, 2026)]:
            changes = get_spec_changelog(*year_pair)
            for item in changes:
                self.assertIsInstance(item, str)
                self.assertGreater(len(item), 0)

    def test_unknown_year_pair_returns_empty_list(self):
        """Unknown year pair must return empty list (not raise)."""
        result = get_spec_changelog(2020, 2023)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_changelog_is_independent_list(self):
        """get_spec_changelog must return a new list each call (no shared state)."""
        a = get_spec_changelog(2025, 2026)
        b = get_spec_changelog(2025, 2026)
        self.assertIsNot(a, b, "Should return independent list objects")


# ---------------------------------------------------------------------------
# AC2 (bonus) — Spec URL lookup
# ---------------------------------------------------------------------------


class TestSpecUrl(FrappeTestCase):
    """get_spec_url_for_version() must return LHDN PDF URLs."""

    def test_url_2025(self):
        url = get_spec_url_for_version(2025)
        self.assertIn("hasil.gov.my", url)
        self.assertIn("2025", url)

    def test_url_2026(self):
        url = get_spec_url_for_version(2026)
        self.assertIn("hasil.gov.my", url)
        self.assertIn("2026", url)

    def test_url_unknown_year_returns_string(self):
        result = get_spec_url_for_version(2020)
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# AC3 — PCB engine reads active spec year from settings
# ---------------------------------------------------------------------------


class TestGetActiveSpecVersion(FrappeTestCase):
    """get_active_pcb_spec_version() must read from LHDN Payroll Settings."""

    def test_returns_int(self):
        """Return value must be an integer (year)."""
        result = get_active_pcb_spec_version()
        self.assertIsInstance(result, int)

    def test_returns_valid_year(self):
        """Return value must be a known spec year (2024, 2025, or 2026)."""
        result = get_active_pcb_spec_version()
        self.assertIn(result, (2024, 2025, 2026))

    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.frappe.db.get_single_value",
        return_value="2026",
    )
    def test_reads_2026_from_settings(self, mock_gsv):
        """When settings store '2026', function must return 2026."""
        result = get_active_pcb_spec_version()
        self.assertEqual(result, 2026)

    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.frappe.db.get_single_value",
        return_value=None,
    )
    def test_falls_back_to_2025_when_not_configured(self, mock_gsv):
        """When settings value is None, fall back to 2025."""
        result = get_active_pcb_spec_version()
        self.assertEqual(result, 2025)

    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.frappe.db.get_single_value",
        side_effect=Exception("DB error"),
    )
    def test_falls_back_on_exception(self, mock_gsv):
        """On any DB error, fall back to default year without raising."""
        result = get_active_pcb_spec_version()
        self.assertIsInstance(result, int)
        self.assertEqual(result, 2025)


class TestPCBCalculatorReadsSpecYear(FrappeTestCase):
    """PCB calculate_pcb() must use active spec year from settings when
    assessment_year is not explicitly provided (US-231, AC3)."""

    def test_calculate_pcb_uses_spec_year_from_settings(self):
        """calculate_pcb() with no assessment_year must call get_active_pcb_spec_version."""
        from lhdn_payroll_integration.services import pcb_calculator

        with patch.object(
            pcb_calculator,
            "_get_active_spec_year",
            return_value=2025,
        ) as mock_spec:
            from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb

            result = calculate_pcb(annual_income=60000, resident=True)
            mock_spec.assert_called_once()
            self.assertIsInstance(result, float)
            self.assertGreater(result, 0)

    def test_calculate_pcb_explicit_year_overrides_settings(self):
        """When assessment_year is provided, settings must NOT be called."""
        from lhdn_payroll_integration.services import pcb_calculator

        with patch.object(
            pcb_calculator,
            "_get_active_spec_year",
            return_value=9999,  # Would cause an error if called
        ) as mock_spec:
            from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb

            result = calculate_pcb(
                annual_income=60000, resident=True, assessment_year=2025
            )
            mock_spec.assert_not_called()
            self.assertIsInstance(result, float)

    def test_ya2025_rate_applied_when_spec_is_2025(self):
        """With 2025 spec active, a high-income employee should use the 2025 30% band."""
        from lhdn_payroll_integration.services import pcb_calculator

        with patch.object(pcb_calculator, "_get_active_spec_year", return_value=2025):
            from lhdn_payroll_integration.services.pcb_calculator import calculate_pcb

            # RM2,500,000 annual income — triggers 30% top band in YA2025
            result_2025 = calculate_pcb(
                annual_income=2_500_000, resident=True, assessment_year=2025
            )
            result_2024 = calculate_pcb(
                annual_income=2_500_000, resident=True, assessment_year=2024
            )
            # YA2025 has 30% vs YA2024's 26% for top income — 2025 should be higher
            self.assertGreater(result_2025, result_2024)


# ---------------------------------------------------------------------------
# AC4 — Audit trail: get_pcb_spec_version_label
# ---------------------------------------------------------------------------


class TestPCBSpecVersionLabel(FrappeTestCase):
    """get_pcb_spec_version_label() must return a readable audit label."""

    def test_label_contains_year(self):
        """Label must include the spec year."""
        label = get_pcb_spec_version_label(2025)
        self.assertIn("2025", label)

    def test_label_contains_spec_compliant(self):
        """Label must include 'Spec Compliant' text."""
        label = get_pcb_spec_version_label(2025)
        self.assertIn("Spec Compliant", label)

    def test_label_2026(self):
        """Label for 2026 must say '2026 Spec Compliant'."""
        label = get_pcb_spec_version_label(2026)
        self.assertEqual(label, "2026 Spec Compliant")

    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.frappe.db.get_single_value",
        return_value="2026",
    )
    def test_label_reads_from_settings_when_no_year_given(self, mock_gsv):
        """When no year arg, label must reflect the active settings version."""
        label = get_pcb_spec_version_label()
        self.assertIn("2026", label)

    def test_pcb_spec_version_constant_exists(self):
        """PCB_SPEC_VERSION constant must still be importable for backward compat."""
        from lhdn_payroll_integration.services.pcb_calculator import PCB_SPEC_VERSION

        self.assertIsInstance(PCB_SPEC_VERSION, str)
        self.assertIn("Spec Compliant", PCB_SPEC_VERSION)


# ---------------------------------------------------------------------------
# AC5 — January scheduler check_january_spec_alert
# ---------------------------------------------------------------------------


class TestJanuarySpecAlert(FrappeTestCase):
    """check_january_spec_alert() must exist and be a no-op outside January."""

    def test_function_is_importable(self):
        """check_january_spec_alert must be importable from pcb_spec_service."""
        self.assertTrue(callable(check_january_spec_alert))

    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.datetime.date",
    )
    def test_no_op_in_non_january(self, mock_date):
        """Must not insert any records when called outside January."""
        mock_today = MagicMock()
        mock_today.month = 6  # June — not January
        mock_date.today.return_value = mock_today

        # Should return silently without any DB writes
        try:
            check_january_spec_alert()
        except Exception as exc:
            self.fail(f"check_january_spec_alert raised in non-January: {exc}")

    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.datetime.date",
    )
    @patch(
        "lhdn_payroll_integration.services.pcb_spec_service.frappe.db.get_single_value",
        return_value="2026",
    )
    def test_no_op_when_spec_already_current_year(self, mock_gsv, mock_date):
        """Must not alert when active spec year >= current year (already up-to-date)."""
        mock_today = MagicMock()
        mock_today.month = 1
        mock_today.year = 2026
        mock_date.today.return_value = mock_today

        # active spec = 2026, current year = 2026 → no alert needed
        with patch(
            "lhdn_payroll_integration.services.pcb_spec_service.frappe.db.sql_list",
            return_value=[],
        ):
            try:
                check_january_spec_alert()
            except Exception as exc:
                self.fail(f"check_january_spec_alert raised unexpectedly: {exc}")

    def test_function_is_in_hooks_daily_scheduler(self):
        """check_january_spec_alert must be registered in hooks.py daily scheduler."""
        import importlib

        hooks = importlib.import_module("lhdn_payroll_integration.hooks")
        daily_tasks = hooks.scheduler_events.get("daily", [])
        self.assertIn(
            "lhdn_payroll_integration.services.pcb_spec_service.check_january_spec_alert",
            daily_tasks,
            "check_january_spec_alert not found in hooks.scheduler_events['daily']",
        )
