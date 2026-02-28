"""Tests for US-095: Multi-Tier Levy Model (MTLM) Rate Calculation for Foreign Workers."""

import json
import os
from frappe.tests.utils import FrappeTestCase

CUSTOM_FIELD_FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "fixtures",
    "custom_field.json",
)


class TestMTLMFixture(FrappeTestCase):
    def _load_fixture(self):
        with open(CUSTOM_FIELD_FIXTURE) as f:
            return json.load(f)

    def test_local_employee_count_field_exists(self):
        fields = self._load_fixture()
        names = {f.get("fieldname") for f in fields}
        self.assertIn("custom_local_employee_count", names)

    def test_foreign_employee_count_field_exists(self):
        fields = self._load_fixture()
        names = {f.get("fieldname") for f in fields}
        self.assertIn("custom_foreign_employee_count", names)

    def test_local_count_is_int_on_company(self):
        fields = self._load_fixture()
        field = next((f for f in fields if f.get("fieldname") == "custom_local_employee_count"), None)
        self.assertIsNotNone(field)
        self.assertEqual(field.get("dt"), "Company")
        self.assertEqual(field.get("fieldtype"), "Int")

    def test_foreign_count_is_int_on_company(self):
        fields = self._load_fixture()
        field = next((f for f in fields if f.get("fieldname") == "custom_foreign_employee_count"), None)
        self.assertIsNotNone(field)
        self.assertEqual(field.get("dt"), "Company")
        self.assertEqual(field.get("fieldtype"), "Int")


class TestCalculateFwLevyTier(FrappeTestCase):
    def _calc(self, local, foreign, sector=None):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import calculate_fw_levy_tier
        return calculate_fw_levy_tier(local, foreign, sector)

    def test_all_local_returns_tier1(self):
        tier, rate = self._calc(100, 0)
        self.assertEqual(tier, "Tier 1")
        self.assertEqual(rate, 410)

    def test_zero_total_returns_tier1(self):
        tier, rate = self._calc(0, 0)
        self.assertEqual(tier, "Tier 1")
        self.assertEqual(rate, 410)

    def test_ratio_below_15_percent_is_tier1(self):
        # 10 foreign, 90 local → ratio = 10/100 = 0.10 < 0.15
        tier, rate = self._calc(90, 10)
        self.assertEqual(tier, "Tier 1")
        self.assertEqual(rate, 410)

    def test_ratio_at_15_percent_is_tier2(self):
        # 15 foreign, 85 local → ratio = 15/100 = 0.15 == Tier 2 lower bound
        tier, rate = self._calc(85, 15)
        self.assertEqual(tier, "Tier 2")
        self.assertEqual(rate, 1230)

    def test_ratio_in_tier2_range(self):
        # 25 foreign, 75 local → ratio = 0.25 → Tier 2
        tier, rate = self._calc(75, 25)
        self.assertEqual(tier, "Tier 2")
        self.assertEqual(rate, 1230)

    def test_ratio_at_30_percent_is_tier3(self):
        # 30 foreign, 70 local → ratio = 0.30 → Tier 3
        tier, rate = self._calc(70, 30)
        self.assertEqual(tier, "Tier 3")
        self.assertEqual(rate, 2500)

    def test_ratio_above_30_percent_returns_tier3_highest_rate(self):
        # 50 foreign, 50 local → ratio = 0.50 → Tier 3 (highest rate)
        tier, rate = self._calc(50, 50)
        self.assertEqual(tier, "Tier 3")
        self.assertEqual(rate, 2500)

    def test_all_foreign_returns_tier3(self):
        # 100 foreign, 0 local → ratio = 1.0 → Tier 3
        tier, rate = self._calc(0, 100)
        self.assertEqual(tier, "Tier 3")
        self.assertEqual(rate, 2500)

    def test_high_dependency_returns_highest_rate(self):
        """Acceptance criterion: dependency ratio above Tier 3 threshold returns highest rate."""
        # 80 foreign, 20 local → ratio = 0.80 → well above 0.30 threshold
        tier, rate = self._calc(20, 80)
        self.assertEqual(tier, "Tier 3")
        self.assertEqual(rate, 2500)
        # Verify it returns the maximum available rate
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        max_rate = max(v[2] for v in MTLM_TIERS.values())
        self.assertEqual(rate, max_rate)

    def test_sector_parameter_accepted(self):
        # sector param is reserved for future use — should not raise
        tier, rate = self._calc(80, 20, sector="Manufacturing")
        self.assertIn(tier, ["Tier 1", "Tier 2", "Tier 3"])
        self.assertIn(rate, [410, 1230, 2500])


class TestMTLMTiersConstant(FrappeTestCase):
    def test_mtlm_tiers_constant_exists(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        self.assertIsInstance(MTLM_TIERS, dict)

    def test_mtlm_tiers_has_three_tiers(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        self.assertEqual(len(MTLM_TIERS), 3)

    def test_tier1_rate_is_410(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        self.assertEqual(MTLM_TIERS["Tier 1"][2], 410)

    def test_tier2_rate_is_1230(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        self.assertEqual(MTLM_TIERS["Tier 2"][2], 1230)

    def test_tier3_rate_is_2500(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        self.assertEqual(MTLM_TIERS["Tier 3"][2], 2500)

    def test_tiers_cover_0_to_1_range(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.fw_levy_service import MTLM_TIERS
        # Tier boundaries should start at 0.0 and end at 1.0
        lows = sorted(v[0] for v in MTLM_TIERS.values())
        highs = sorted(v[1] for v in MTLM_TIERS.values())
        self.assertEqual(lows[0], 0.0)
        self.assertEqual(highs[-1], 1.0)


class TestFWLevyReportMTLMColumns(FrappeTestCase):
    def test_report_columns_include_levy_tier(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.foreign_worker_levy.foreign_worker_levy import get_columns
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("levy_tier", fieldnames)

    def test_report_columns_include_mtlm_annual_levy(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.foreign_worker_levy.foreign_worker_levy import get_columns
        cols = get_columns()
        fieldnames = [c["fieldname"] for c in cols]
        self.assertIn("mtlm_annual_levy", fieldnames)

    def test_levy_tier_column_is_data_type(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.foreign_worker_levy.foreign_worker_levy import get_columns
        cols = get_columns()
        col = next((c for c in cols if c["fieldname"] == "levy_tier"), None)
        self.assertIsNotNone(col)
        self.assertEqual(col["fieldtype"], "Data")

    def test_mtlm_annual_levy_column_is_currency(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.report.foreign_worker_levy.foreign_worker_levy import get_columns
        cols = get_columns()
        col = next((c for c in cols if c["fieldname"] == "mtlm_annual_levy"), None)
        self.assertIsNotNone(col)
        self.assertEqual(col["fieldtype"], "Currency")
