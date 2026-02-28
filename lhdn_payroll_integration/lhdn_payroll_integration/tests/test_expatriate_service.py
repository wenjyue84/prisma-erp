"""Tests for US-083: Expatriate Gross-Up Calculator and DTA Country Table.

Covers:
1. calculate_gross_up: net RM10,000/month converges to correct gross (resident)
2. calculate_gross_up: non-resident gross-up uses flat 30% rate
3. calculate_gross_up: with annual_reliefs reduces the gross required
4. calculate_gross_up: converged flag is True on successful convergence
5. calculate_gross_up: net_monthly in result is within tolerance of desired_net
6. is_resident: 182+ days -> True
7. is_resident: < 182 days -> False (non-resident)
8. is_resident: exactly 182 days -> True
9. is_resident: 0 days -> False
10. get_dta_country: Singapore returns correct treaty info
11. get_dta_country: unknown code returns None
12. DTA_COUNTRIES: contains at least 5 key DTA countries
13. calculate_gross_up: high desired net (RM50,000/month) still converges
14. calculate_gross_up: gross > net (tax is always positive for taxable income)
"""
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.services.expatriate_service import (
    DTA_COUNTRIES,
    calculate_gross_up,
    get_dta_country,
    is_resident,
)


class TestCalculateGrossUp(FrappeTestCase):
    """Unit tests for calculate_gross_up()."""

    def test_convergence_for_resident_10k_net(self):
        """Net RM10,000/month resident should converge and produce correct gross."""
        result = calculate_gross_up(desired_net_monthly=10_000.0, resident=True)

        self.assertTrue(result["converged"], "Solver should converge within max_iterations")
        # Gross must be greater than desired net (tax is positive)
        self.assertGreater(result["gross_monthly"], 10_000.0)

    def test_net_monthly_within_tolerance(self):
        """Achieved net_monthly should be within RM0.01 of desired net."""
        desired = 10_000.0
        result = calculate_gross_up(desired_net_monthly=desired, resident=True)

        self.assertAlmostEqual(result["net_monthly"], desired, delta=0.01,
                               msg="Net monthly should match desired net within 1 cent")

    def test_non_resident_uses_flat_30_percent(self):
        """Non-resident gross-up should use 30% flat rate — higher gross than resident."""
        resident_result = calculate_gross_up(desired_net_monthly=10_000.0, resident=True)
        non_resident_result = calculate_gross_up(desired_net_monthly=10_000.0, resident=False)

        # Non-resident gross is always higher because 30% rate > effective resident rate
        self.assertGreater(
            non_resident_result["gross_monthly"],
            resident_result["gross_monthly"],
            msg="Non-resident gross should exceed resident gross for same desired net",
        )

    def test_non_resident_net_within_tolerance(self):
        """Non-resident: achieved net_monthly should be within RM0.01 of desired."""
        desired = 10_000.0
        result = calculate_gross_up(desired_net_monthly=desired, resident=False)

        self.assertAlmostEqual(result["net_monthly"], desired, delta=0.01)

    def test_annual_reliefs_reduce_required_gross(self):
        """Higher annual reliefs should reduce the gross-up required."""
        result_no_relief = calculate_gross_up(desired_net_monthly=10_000.0, annual_reliefs=0.0)
        result_with_relief = calculate_gross_up(desired_net_monthly=10_000.0, annual_reliefs=20_000.0)

        self.assertLess(
            result_with_relief["gross_monthly"],
            result_no_relief["gross_monthly"],
            msg="Reliefs should reduce required gross",
        )

    def test_converged_flag_true(self):
        """converged flag should be True for a standard case."""
        result = calculate_gross_up(desired_net_monthly=5_000.0, resident=True)
        self.assertTrue(result["converged"])

    def test_gross_greater_than_net(self):
        """gross_monthly must always exceed desired_net_monthly (tax is positive)."""
        for desired in [3_000.0, 10_000.0, 30_000.0]:
            result = calculate_gross_up(desired_net_monthly=desired, resident=True)
            self.assertGreater(
                result["gross_monthly"], desired,
                msg=f"gross_monthly should exceed {desired}",
            )

    def test_high_income_convergence(self):
        """RM50,000/month desired net should also converge."""
        result = calculate_gross_up(desired_net_monthly=50_000.0, resident=True)
        self.assertTrue(result["converged"])
        self.assertAlmostEqual(result["net_monthly"], 50_000.0, delta=0.01)

    def test_result_keys_present(self):
        """Result dict must contain all required keys."""
        result = calculate_gross_up(desired_net_monthly=10_000.0)
        expected_keys = {
            "gross_monthly", "gross_annual", "annual_tax",
            "monthly_tax", "net_monthly", "converged", "iterations", "resident",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_annual_equals_monthly_times_12(self):
        """gross_annual should equal gross_monthly * 12 (within rounding)."""
        result = calculate_gross_up(desired_net_monthly=10_000.0, resident=True)
        self.assertAlmostEqual(result["gross_annual"], result["gross_monthly"] * 12, delta=1.0)

    def test_annual_tax_equals_monthly_tax_times_12(self):
        """annual_tax should equal monthly_tax * 12 (within rounding)."""
        result = calculate_gross_up(desired_net_monthly=10_000.0, resident=True)
        self.assertAlmostEqual(result["annual_tax"], result["monthly_tax"] * 12, delta=1.0)


class TestIsResident(FrappeTestCase):
    """Unit tests for is_resident() — ITA 1967 s.7(1)(b) 182-day rule."""

    def test_182_days_is_resident(self):
        """Exactly 182 days of presence -> resident."""
        self.assertTrue(is_resident(182))

    def test_183_days_is_resident(self):
        """183 days of presence -> resident."""
        self.assertTrue(is_resident(183))

    def test_365_days_is_resident(self):
        """Full year of presence -> resident."""
        self.assertTrue(is_resident(365))

    def test_181_days_is_non_resident(self):
        """181 days of presence -> non-resident (below threshold)."""
        self.assertFalse(is_resident(181))

    def test_0_days_is_non_resident(self):
        """0 days of presence -> non-resident."""
        self.assertFalse(is_resident(0))

    def test_90_days_is_non_resident(self):
        """90 days of presence -> non-resident."""
        self.assertFalse(is_resident(90))


class TestDTACountries(FrappeTestCase):
    """Tests for DTA_COUNTRIES lookup table and get_dta_country() helper."""

    def test_dta_countries_has_minimum_entries(self):
        """DTA_COUNTRIES should contain at least 5 countries."""
        self.assertGreaterEqual(len(DTA_COUNTRIES), 5)

    def test_singapore_treaty_details(self):
        """Singapore entry should have correct treaty rate and threshold."""
        sg = get_dta_country("SG")
        self.assertIsNotNone(sg)
        self.assertEqual(sg["country"], "Singapore")
        self.assertIn("days_threshold", sg)
        self.assertIn("treaty_rate", sg)
        self.assertIn("notes", sg)

    def test_uk_entry_exists(self):
        """UK (GB) should be in DTA_COUNTRIES."""
        gb = get_dta_country("GB")
        self.assertIsNotNone(gb)
        self.assertEqual(gb["country"], "United Kingdom")

    def test_australia_entry_exists(self):
        """Australia (AU) should be in DTA_COUNTRIES."""
        au = get_dta_country("AU")
        self.assertIsNotNone(au)
        self.assertEqual(au["country"], "Australia")

    def test_unknown_country_returns_none(self):
        """Unknown country code should return None."""
        result = get_dta_country("ZZ")
        self.assertIsNone(result)

    def test_empty_code_returns_none(self):
        """Empty string should return None gracefully."""
        result = get_dta_country("")
        self.assertIsNone(result)

    def test_case_insensitive_lookup(self):
        """Lowercase country code should still find the entry."""
        sg_upper = get_dta_country("SG")
        sg_lower = get_dta_country("sg")
        self.assertEqual(sg_upper, sg_lower)

    def test_days_threshold_is_integer(self):
        """All DTA entries should have a numeric days_threshold."""
        for code, details in DTA_COUNTRIES.items():
            self.assertIsInstance(
                details["days_threshold"], (int, float),
                msg=f"days_threshold for {code} should be numeric",
            )
