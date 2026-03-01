"""Tests for US-118: YA2025 PCB Schedule 1 Tax Brackets (LHDN PCB Specification 2025).

Covers:
- All 10 YA2025 bracket tiers are correctly encoded
- Tax computation at the 6 LHDN-specified income checkpoints
- PCB calculator routes through YA2025 brackets when assessment_year=2025
- YA2024 calculations are unaffected (backward compatibility)
- RM400 personal rebate still applies for CI <= RM35,000 in YA2025
- 30% top tier correctly applied to chargeable income above RM2,000,000
"""
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.pcb_tax_brackets import get_tax_bands
from lhdn_payroll_integration.services.pcb_calculator import (
    _compute_tax_for_year,
    calculate_pcb,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ya2025_tax(chargeable_income: float) -> float:
    """Compute annual income tax on chargeable income under YA2025 brackets."""
    return _compute_tax_for_year(chargeable_income, 2025)


def _ya2024_tax(chargeable_income: float) -> float:
    """Compute annual income tax on chargeable income under YA2024 brackets."""
    return _compute_tax_for_year(chargeable_income, 2024)


# ---------------------------------------------------------------------------
# Tests — pcb_tax_brackets.get_tax_bands()
# ---------------------------------------------------------------------------

class TestGetTaxBands(FrappeTestCase):
    """get_tax_bands() returns the correct bracket tables for each year."""

    def test_ya2025_has_ten_tiers(self):
        """YA2025 Schedule 1 has exactly 10 progressive tiers."""
        bands, _ = get_tax_bands(2025)
        self.assertEqual(len(bands), 10, "YA2025 must have 10 tax tiers")

    def test_ya2024_has_ten_tiers(self):
        """YA2024 Schedule 1 has exactly 10 progressive tiers."""
        bands, _ = get_tax_bands(2024)
        self.assertEqual(len(bands), 10, "YA2024 must have 10 tax tiers")

    def test_ya2025_top_tier_rate_is_30_percent(self):
        """YA2025 top tier (above RM2M) must be 30%."""
        bands, _ = get_tax_bands(2025)
        top_upper, top_rate, _ = bands[-1]
        self.assertEqual(top_rate, 0.30, "YA2025 top tier must be 30%")

    def test_ya2024_top_tier_rate_is_26_percent(self):
        """YA2024 top tier (above RM2M) must be 26% (pre-restructure)."""
        bands, _ = get_tax_bands(2024)
        top_upper, top_rate, _ = bands[-1]
        self.assertEqual(top_rate, 0.26, "YA2024 top tier must be 26%")

    def test_ya2025_band_35001_50000_is_6_percent(self):
        """YA2025 band 35,001–50,000 is 6% (was 8% in YA2024)."""
        bands, _ = get_tax_bands(2025)
        # Band index 3 = 35001-50000
        upper, rate, _ = bands[3]
        self.assertEqual(upper, 50_000)
        self.assertAlmostEqual(rate, 0.06, places=4,
                               msg="YA2025 35001–50000 tier must be 6%")

    def test_ya2025_band_50001_70000_is_11_percent(self):
        """YA2025 band 50,001–70,000 is 11% (was 13% in YA2024)."""
        bands, _ = get_tax_bands(2025)
        upper, rate, _ = bands[4]
        self.assertEqual(upper, 70_000)
        self.assertAlmostEqual(rate, 0.11, places=4)

    def test_ya2025_band_70001_100000_is_19_percent(self):
        """YA2025 band 70,001–100,000 is 19% (was 21% in YA2024)."""
        bands, _ = get_tax_bands(2025)
        upper, rate, _ = bands[5]
        self.assertEqual(upper, 100_000)
        self.assertAlmostEqual(rate, 0.19, places=4)

    def test_ya2025_has_250k_inflection(self):
        """YA2025 introduces RM250,000 inflection point (not present in YA2024)."""
        bands_2025, _ = get_tax_bands(2025)
        uppers_2025 = [b[0] for b in bands_2025]
        self.assertIn(250_000, uppers_2025,
                      "YA2025 must have RM250,000 as a band upper limit")

        bands_2024, _ = get_tax_bands(2024)
        uppers_2024 = [b[0] for b in bands_2024]
        self.assertNotIn(250_000, uppers_2024,
                         "YA2024 must NOT have RM250,000 as a band upper limit")

    def test_ya2025_cumulative_at_lower_bounds_correct(self):
        """YA2025 cumulative tax values at each band lower bound are correct."""
        bands, _ = get_tax_bands(2025)
        expected_cumulatives = [
            0.0,        # 0–5,000 : 0%
            0.0,        # 5,001–20,000 : 1%
            150.0,      # 20,001–35,000 : 3%
            600.0,      # 35,001–50,000 : 6%
            1_500.0,    # 50,001–70,000 : 11%
            3_700.0,    # 70,001–100,000 : 19%
            9_400.0,    # 100,001–250,000 : 25%
            46_900.0,   # 250,001–400,000 : 26%
            85_900.0,   # 400,001–2,000,000 : 28%
            533_900.0,  # above 2,000,000 : 30%
        ]
        for i, (expected, band) in enumerate(zip(expected_cumulatives, bands)):
            self.assertAlmostEqual(
                band[2], expected, places=1,
                msg=f"Band {i} cumulative should be {expected}, got {band[2]}"
            )

    def test_future_year_falls_back_to_latest(self):
        """Requesting a year beyond the latest defined falls back to YA2025."""
        bands_future, _ = get_tax_bands(2099)
        bands_2025, _ = get_tax_bands(2025)
        self.assertEqual(bands_future, bands_2025,
                         "Year 2099 should fall back to the YA2025 brackets")


# ---------------------------------------------------------------------------
# Tests — _compute_tax_for_year() at the 6 LHDN checkpoints (YA2025)
# ---------------------------------------------------------------------------

class TestComputeTaxYA2025(FrappeTestCase):
    """Verify annual tax at the 6 LHDN-specified chargeable income checkpoints.

    Reference: LHDN PCB Specification 2025 / Official tax rate table.
    """

    def test_chargeable_income_5000_tax_is_zero(self):
        """RM5,000 chargeable income → RM0 tax (0% tier)."""
        self.assertAlmostEqual(_ya2025_tax(5_000), 0.0, places=2)

    def test_chargeable_income_35000_tax_is_600(self):
        """RM35,000 chargeable income → RM600 tax.

        Computation: 150 (cumul at RM20,000) + 15,000 × 3% = 600
        """
        self.assertAlmostEqual(_ya2025_tax(35_000), 600.0, places=2)

    def test_chargeable_income_100000_tax_is_9400(self):
        """RM100,000 chargeable income → RM9,400 tax.

        Computation: 3,700 (cumul at RM70,000) + 30,000 × 19% = 9,400
        """
        self.assertAlmostEqual(_ya2025_tax(100_000), 9_400.0, places=2)

    def test_chargeable_income_400000_tax_is_85900(self):
        """RM400,000 chargeable income → RM85,900 tax.

        Computation: 46,900 (cumul at RM250,000) + 150,000 × 26% = 85,900
        """
        self.assertAlmostEqual(_ya2025_tax(400_000), 85_900.0, places=2)

    def test_chargeable_income_2000000_tax_is_533900(self):
        """RM2,000,000 chargeable income → RM533,900 tax.

        Computation: 85,900 (cumul at RM400,000) + 1,600,000 × 28% = 533,900
        """
        self.assertAlmostEqual(_ya2025_tax(2_000_000), 533_900.0, places=2)

    def test_chargeable_income_2500000_tax_is_683900(self):
        """RM2,500,000 chargeable income → RM683,900 tax (30% top tier).

        Computation: 533,900 (cumul at RM2,000,000) + 500,000 × 30% = 683,900
        """
        self.assertAlmostEqual(_ya2025_tax(2_500_000), 683_900.0, places=2)

    def test_zero_chargeable_income_returns_zero(self):
        """Zero chargeable income → zero tax."""
        self.assertEqual(_ya2025_tax(0), 0.0)

    def test_negative_chargeable_income_returns_zero(self):
        """Negative chargeable income → zero tax."""
        self.assertEqual(_ya2025_tax(-1000), 0.0)


# ---------------------------------------------------------------------------
# Tests — calculate_pcb() with assessment_year=2025
# ---------------------------------------------------------------------------

class TestCalculatePcbYA2025(FrappeTestCase):
    """calculate_pcb() routes through YA2025 brackets when assessment_year=2025."""

    # Self-relief = RM9,000 for a single resident.
    # To get chargeable_income = X, pass annual_income = X + 9,000.

    def test_pcb_ya2025_ci_100000_uses_new_brackets(self):
        """YA2025: single resident with CI RM100,000 → monthly PCB RM9,400/12.

        Annual income = 109,000 → CI = 100,000 → annual tax = 9,400.
        Monthly PCB = 9,400 / 12 ≈ 783.33
        """
        result = calculate_pcb(109_000, resident=True, category=1, assessment_year=2025)
        self.assertAlmostEqual(result, round(9_400 / 12, 2), places=2)

    def test_pcb_ya2024_ci_100000_uses_old_brackets(self):
        """YA2024: single resident with CI RM100,000 → monthly PCB RM10,700/12.

        Annual income = 109,000 → CI = 100,000 → annual tax under YA2024 = 10,700.
        (Band 70001–100000 was 21% in YA2024 → 4400 + 30000*21% = 10,700)
        """
        result = calculate_pcb(109_000, resident=True, category=1, assessment_year=2024)
        self.assertAlmostEqual(result, round(10_700 / 12, 2), places=2)

    def test_pcb_ya2025_differs_from_ya2024_for_mid_income(self):
        """YA2025 rates produce lower PCB than YA2024 for mid-range income (50001–400000)."""
        annual_income = 160_000  # CI = 151,000 after RM9,000 relief
        pcb_2024 = calculate_pcb(annual_income, resident=True, category=1, assessment_year=2024)
        pcb_2025 = calculate_pcb(annual_income, resident=True, category=1, assessment_year=2025)
        self.assertLess(pcb_2025, pcb_2024,
                        "YA2025 mid-range rates (lower than YA2024) should produce lower PCB")

    def test_pcb_ya2025_top_tier_income_applies_30_percent(self):
        """YA2025: income above RM2M CI hits the 30% top tier."""
        # annual_income = 2,509,000 → CI = 2,500,000 → annual tax = 683,900
        result = calculate_pcb(2_509_000, resident=True, category=1, assessment_year=2025)
        self.assertAlmostEqual(result, round(683_900 / 12, 2), places=2)

    def test_pcb_ya2024_top_tier_income_applies_26_percent(self):
        """YA2024: income above RM2M CI hits the 26% top tier (not 30%)."""
        # annual_income = 2,009,000 → CI = 2,000,000
        # YA2024: 481,700 (cumul at 2M) + 0 = 481,700
        result_2024 = calculate_pcb(2_009_000, resident=True, category=1, assessment_year=2024)
        result_2025 = calculate_pcb(2_009_000, resident=True, category=1, assessment_year=2025)
        self.assertLess(result_2024, result_2025,
                        "YA2024 top-tier tax should be less than YA2025 at RM2M+")

    def test_pcb_backward_compat_no_year_uses_ya2024(self):
        """Without assessment_year, calculate_pcb() uses YA2024 bands (backward compat)."""
        annual_income = 109_000
        result_no_year = calculate_pcb(annual_income, resident=True, category=1)
        result_ya2024 = calculate_pcb(annual_income, resident=True, category=1, assessment_year=2024)
        self.assertAlmostEqual(result_no_year, result_ya2024, places=2,
                               msg="Default (no year) must equal explicit YA2024 results")


# ---------------------------------------------------------------------------
# Tests — Personal rebate (RM400) unchanged for YA2025
# ---------------------------------------------------------------------------

class TestPersonalRebateYA2025(FrappeTestCase):
    """ITA 1967 s.6A RM400 personal rebate still applies for CI <= RM35,000 in YA2025."""

    def test_rebate_applied_when_ci_equals_35000_ya2025(self):
        """Single resident, YA2025, CI = RM35,000 → tax RM600 − rebate RM400 = RM200/yr."""
        # annual_income = 44,000 → CI = 35,000 (after RM9,000 self-relief)
        result = calculate_pcb(44_000, resident=True, category=1, assessment_year=2025)
        expected_annual = 600.0 - 400.0  # tax 600, rebate 400 → net 200
        self.assertAlmostEqual(result, round(expected_annual / 12, 2), places=2)

    def test_rebate_not_applied_when_ci_above_35000_ya2025(self):
        """CI above RM35,000 — rebate does NOT apply."""
        # CI = 36,000 → annual tax = 600 + (36000-35000)*0.06 = 600+60 = 660; no rebate
        result = calculate_pcb(45_000, resident=True, category=1, assessment_year=2025)
        expected_annual = 600.0 + (45_000 - 9_000 - 35_000) * 0.06
        self.assertAlmostEqual(result, round(expected_annual / 12, 2), places=2)

    def test_rebate_applied_for_ya2024_at_ci_35000(self):
        """Rebate still applies for YA2024 at CI RM35,000 (backward compat)."""
        # CI = 35,000 → YA2024 annual tax = 600 → rebate 400 → net 200
        result = calculate_pcb(44_000, resident=True, category=1, assessment_year=2024)
        expected_annual = 600.0 - 400.0
        self.assertAlmostEqual(result, round(expected_annual / 12, 2), places=2)


# ---------------------------------------------------------------------------
# Tests — YA2024 backward compatibility
# ---------------------------------------------------------------------------

class TestYA2024BackwardCompat(FrappeTestCase):
    """YA2024 calculations remain correct after YA2025 bracket addition."""

    def test_ya2024_ci_35000_tax_is_600(self):
        """YA2024: CI RM35,000 → annual tax RM600 (unchanged)."""
        self.assertAlmostEqual(_ya2024_tax(35_000), 600.0, places=2)

    def test_ya2024_ci_50000_tax_is_1800(self):
        """YA2024: CI RM50,000 → annual tax RM1,800 (8% on 35001–50000)."""
        # 600 + 15000 * 0.08 = 600 + 1200 = 1800
        self.assertAlmostEqual(_ya2024_tax(50_000), 1_800.0, places=2)

    def test_ya2024_ci_100000_tax_is_10700(self):
        """YA2024: CI RM100,000 → annual tax RM10,700."""
        # 4400 + 30000 * 0.21 = 4400 + 6300 = 10700
        self.assertAlmostEqual(_ya2024_tax(100_000), 10_700.0, places=2)

    def test_ya2024_and_ya2025_differ_at_50000(self):
        """RM50,000 CI: YA2024 tax (1,800) differs from YA2025 tax (1,500)."""
        tax_2024 = _ya2024_tax(50_000)
        tax_2025 = _ya2025_tax(50_000)
        # YA2025: 600 + 15000 * 0.06 = 600+900 = 1500
        self.assertAlmostEqual(tax_2024, 1_800.0, places=2)
        self.assertAlmostEqual(tax_2025, 1_500.0, places=2)
        self.assertNotEqual(tax_2024, tax_2025)
