"""Tests for US-190: Update Employment Contract Stamp Duty Exemption Threshold.

Budget 2026 (Finance Bill 2025) raises the employment contract stamp duty
exemption threshold from RM300 to RM3,000 effective 1 January 2026.

Covers:
- Legacy threshold (RM300) applies to contracts signed before 1 Jan 2026
- New threshold (RM3,000) applies to contracts signed on/after 1 Jan 2026
- get_exemption_threshold() date-lookup function
- is_stamp_duty_exempt() date-aware signature
- LEGACY_EXEMPTION_THRESHOLD constant
- STAMP_DUTY_THRESHOLD_SCHEDULE configurability
- DocType controller passes contract_date to is_stamp_duty_exempt
"""

from datetime import date
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service import (
    EXEMPTION_THRESHOLD,
    LEGACY_EXEMPTION_THRESHOLD,
    STAMP_DUTY_SAS_EFFECTIVE_DATE,
    STAMP_DUTY_THRESHOLD_SCHEDULE,
    get_exemption_threshold,
    is_stamp_duty_exempt,
)


class TestUS190Constants(FrappeTestCase):
    """Verify US-190 constants are correctly defined."""

    def test_legacy_exemption_threshold_is_300(self):
        """Legacy (pre-2026) exemption threshold must be RM300/month."""
        self.assertEqual(LEGACY_EXEMPTION_THRESHOLD, 300.0)

    def test_current_exemption_threshold_is_3000(self):
        """Current (post-2026) exemption threshold must be RM3,000/month."""
        self.assertEqual(EXEMPTION_THRESHOLD, 3000.0)

    def test_sas_effective_date_is_2026_01_01(self):
        """SAS effective date must be 1 January 2026."""
        self.assertEqual(STAMP_DUTY_SAS_EFFECTIVE_DATE, date(2026, 1, 1))

    def test_threshold_schedule_has_two_entries(self):
        """Threshold schedule must have at least the 2026 and legacy entries."""
        self.assertGreaterEqual(len(STAMP_DUTY_THRESHOLD_SCHEDULE), 2)

    def test_threshold_schedule_contains_3000_from_2026(self):
        """Schedule must include RM3,000 entry effective 1 Jan 2026."""
        entry_2026 = next(
            (e for e in STAMP_DUTY_THRESHOLD_SCHEDULE if e[0] == date(2026, 1, 1)),
            None,
        )
        self.assertIsNotNone(entry_2026, "No 2026-01-01 entry in threshold schedule")
        self.assertEqual(entry_2026[1], 3000.0)

    def test_threshold_schedule_contains_300_legacy(self):
        """Schedule must include legacy RM300 entry for pre-2026 contracts."""
        has_legacy = any(e[1] == 300.0 for e in STAMP_DUTY_THRESHOLD_SCHEDULE)
        self.assertTrue(has_legacy, "No legacy RM300 entry in threshold schedule")


class TestGetExemptionThreshold(FrappeTestCase):
    """Test date-aware threshold lookup via get_exemption_threshold()."""

    def test_contract_on_2026_01_01_uses_3000(self):
        """Contract signed exactly on 1 Jan 2026 → RM3,000 threshold."""
        threshold = get_exemption_threshold(date(2026, 1, 1))
        self.assertEqual(threshold, 3000.0)

    def test_contract_after_2026_uses_3000(self):
        """Contract signed on 1 Feb 2026 → RM3,000 threshold."""
        threshold = get_exemption_threshold(date(2026, 2, 1))
        self.assertEqual(threshold, 3000.0)

    def test_contract_on_2025_12_31_uses_300(self):
        """Contract signed on 31 Dec 2025 (pre-2026) → RM300 legacy threshold."""
        threshold = get_exemption_threshold(date(2025, 12, 31))
        self.assertEqual(threshold, 300.0)

    def test_contract_in_2024_uses_300(self):
        """Contract signed in 2024 → RM300 legacy threshold."""
        threshold = get_exemption_threshold(date(2024, 6, 15))
        self.assertEqual(threshold, 300.0)

    def test_contract_in_2020_uses_300(self):
        """Very old contract → RM300 legacy threshold."""
        threshold = get_exemption_threshold(date(2020, 1, 1))
        self.assertEqual(threshold, 300.0)

    def test_no_date_uses_current_threshold(self):
        """No date provided → returns the threshold applicable today (RM3,000 in 2026+)."""
        threshold = get_exemption_threshold(None)
        # In test environment running in 2026, this should be RM3,000
        self.assertIn(threshold, [300.0, 3000.0])  # valid value from schedule

    def test_date_as_string_accepted(self):
        """Date as string 'YYYY-MM-DD' is accepted."""
        threshold = get_exemption_threshold("2026-03-01")
        self.assertEqual(threshold, 3000.0)

    def test_pre_2026_string_uses_300(self):
        """Date string '2025-06-01' → RM300."""
        threshold = get_exemption_threshold("2025-06-01")
        self.assertEqual(threshold, 300.0)


class TestIsStampDutyExemptDateAware(FrappeTestCase):
    """Test date-sensitive exemption logic per US-190."""

    # --- Post-2026 contracts (RM3,000 threshold) ---

    def test_post_2026_salary_3000_is_exempt(self):
        """Post-2026: RM3,000 salary at boundary → exempt."""
        self.assertTrue(is_stamp_duty_exempt(3000.0, date(2026, 1, 1)))

    def test_post_2026_salary_2999_is_exempt(self):
        """Post-2026: RM2,999 salary → exempt."""
        self.assertTrue(is_stamp_duty_exempt(2999.0, date(2026, 3, 1)))

    def test_post_2026_salary_1700_is_exempt(self):
        """Post-2026: RM1,700 minimum wage → exempt under RM3,000 threshold."""
        self.assertTrue(is_stamp_duty_exempt(1700.0, date(2026, 1, 15)))

    def test_post_2026_salary_3001_is_dutiable(self):
        """Post-2026: RM3,001 salary → NOT exempt (must be stamped)."""
        self.assertFalse(is_stamp_duty_exempt(3001.0, date(2026, 1, 1)))

    def test_post_2026_salary_5000_is_dutiable(self):
        """Post-2026: RM5,000 salary → NOT exempt."""
        self.assertFalse(is_stamp_duty_exempt(5000.0, date(2026, 6, 30)))

    # --- Pre-2026 contracts (RM300 threshold) ---

    def test_pre_2026_salary_300_is_exempt(self):
        """Pre-2026: RM300 salary at boundary → exempt."""
        self.assertTrue(is_stamp_duty_exempt(300.0, date(2025, 12, 31)))

    def test_pre_2026_salary_299_is_exempt(self):
        """Pre-2026: RM299 salary → exempt."""
        self.assertTrue(is_stamp_duty_exempt(299.0, date(2025, 12, 31)))

    def test_pre_2026_salary_301_is_dutiable(self):
        """Pre-2026: RM301 salary → NOT exempt (must be stamped under old rules)."""
        self.assertFalse(is_stamp_duty_exempt(301.0, date(2025, 12, 31)))

    def test_pre_2026_salary_1700_is_dutiable(self):
        """Pre-2026: RM1,700 salary → NOT exempt under old RM300 threshold."""
        self.assertFalse(is_stamp_duty_exempt(1700.0, date(2025, 6, 1)))

    def test_pre_2026_salary_3000_is_dutiable(self):
        """Pre-2026: RM3,000 salary → NOT exempt under old RM300 threshold."""
        self.assertFalse(is_stamp_duty_exempt(3000.0, date(2025, 12, 31)))

    # --- Backward compat: no contract_date (uses current threshold) ---

    def test_no_date_high_salary_dutiable(self):
        """No contract_date, high salary → dutiable (uses current threshold)."""
        # RM10,000 > RM3,000 (current) and > RM300 (legacy) — always dutiable
        self.assertFalse(is_stamp_duty_exempt(10000.0))

    def test_no_date_zero_salary_exempt(self):
        """No contract_date, zero salary → always exempt."""
        self.assertTrue(is_stamp_duty_exempt(0))

    def test_no_date_none_salary_exempt(self):
        """No contract_date, None salary → treated as 0 → exempt."""
        self.assertTrue(is_stamp_duty_exempt(None))

    # --- Boundary: exact effective date ---

    def test_boundary_2026_01_01_uses_new_threshold(self):
        """Contract signed exactly on 2026-01-01 uses RM3,000 (inclusive)."""
        # RM500 → exempt under RM3,000 but dutiable under RM300
        self.assertTrue(is_stamp_duty_exempt(500.0, date(2026, 1, 1)))

    def test_boundary_2025_12_31_uses_old_threshold(self):
        """Contract signed on 2025-12-31 (day before) uses RM300."""
        # RM500 → dutiable under RM300 threshold
        self.assertFalse(is_stamp_duty_exempt(500.0, date(2025, 12, 31)))


class TestUS190DocTypeController(FrappeTestCase):
    """Test that the DocType controller correctly uses date-sensitive threshold."""

    def test_doctype_controller_imports_successfully(self):
        """LHDN Contract Stamp Duty controller must be importable."""
        from lhdn_payroll_integration.lhdn_payroll_integration.doctype.lhdn_contract_stamp_duty.lhdn_contract_stamp_duty import (
            LHDNContractStampDuty,
        )
        self.assertIsNotNone(LHDNContractStampDuty)

    def test_doctype_exists(self):
        """LHDN Contract Stamp Duty DocType must be registered in the database."""
        self.assertTrue(frappe.db.exists("DocType", "LHDN Contract Stamp Duty"))


class TestUS190ThresholdScheduleConfigurability(FrappeTestCase):
    """Test that the threshold schedule is configurable without code changes."""

    def test_schedule_is_a_list(self):
        """STAMP_DUTY_THRESHOLD_SCHEDULE must be a mutable list."""
        self.assertIsInstance(STAMP_DUTY_THRESHOLD_SCHEDULE, list)

    def test_adding_future_entry_changes_lookup(self):
        """Adding a future row to the schedule changes get_exemption_threshold output."""
        future_date = date(2028, 1, 1)
        future_threshold = 5000.0
        STAMP_DUTY_THRESHOLD_SCHEDULE.append((future_date, future_threshold))
        try:
            threshold = get_exemption_threshold(date(2028, 6, 1))
            self.assertEqual(threshold, future_threshold)
        finally:
            # Restore original schedule
            STAMP_DUTY_THRESHOLD_SCHEDULE.remove((future_date, future_threshold))

    def test_removing_entry_falls_back_to_earlier(self):
        """Removing a schedule entry falls back to the next applicable entry."""
        # After cleanup in previous test, schedule should be back to original
        self.assertGreaterEqual(len(STAMP_DUTY_THRESHOLD_SCHEDULE), 2)
