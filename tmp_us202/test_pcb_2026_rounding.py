"""Tests for US-202: PCB 2026 Two-Step Rounding Rule.

Verifies that round_pcb() in pcb_utils implements the LHDN PCB 2026 Spec:
  Step 1 — truncate raw amount to exactly 2 decimal places (no rounding)
  Step 2 — ceiling to nearest 5 cents

Also verifies that all PCB calculation paths (Method 1, Method 2, director fees)
return values that satisfy the 5-cent ceiling constraint.
"""
from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.pcb_utils import round_pcb
from lhdn_payroll_integration.services.pcb_calculator import (
    calculate_pcb,
    calculate_pcb_method2,
    calculate_director_fee_pcb,
)


def _is_5cent_aligned(value: float) -> bool:
    """Return True if value is a multiple of 0.05 (within float precision)."""
    cents = round(value * 100)
    return cents % 5 == 0


class TestPCB2026Rounding(FrappeTestCase):
    """TestPCB2026Rounding — LHDN PCB 2026 truncate-then-5-cent-ceiling rule.

    Covers at least 15 scenarios including edge cases at 0.00, 0.01, 0.05, 0.06
    fractional values per the LHDN PCB 2026 Computerised Calculation Spec.
    """

    # --- Core two-step rounding scenarios ---

    def test_spec_example_123_023(self):
        """LHDN spec example: 123.023 → truncate 123.02 → ceiling 123.05."""
        self.assertAlmostEqual(round_pcb(123.023), 123.05, places=2)

    def test_spec_example_123_061(self):
        """LHDN spec example: 123.061 → truncate 123.06 → ceiling 123.10."""
        self.assertAlmostEqual(round_pcb(123.061), 123.10, places=2)

    def test_already_on_boundary_123_000(self):
        """Exact 5-cent boundary stays unchanged: 123.000 → 123.00."""
        self.assertAlmostEqual(round_pcb(123.000), 123.00, places=2)

    def test_ac_case_123_049(self):
        """123.049 → truncate 123.04 → ceiling 123.05."""
        self.assertAlmostEqual(round_pcb(123.049), 123.05, places=2)

    def test_zero_input(self):
        """0.00 → 0.00 (zero or negative short-circuits)."""
        self.assertEqual(round_pcb(0.00), 0.0)

    def test_negative_input(self):
        """Negative amount returns 0.0."""
        self.assertEqual(round_pcb(-50.00), 0.0)

    def test_exactly_on_5cent_boundary_100_00(self):
        """100.00 is already on 5-cent boundary → stays 100.00."""
        self.assertAlmostEqual(round_pcb(100.00), 100.00, places=2)

    def test_small_fractional_above_boundary_100_01(self):
        """100.01 → truncate 100.01 → ceiling 100.05."""
        self.assertAlmostEqual(round_pcb(100.01), 100.05, places=2)

    def test_small_sub_cent_above_boundary_100_001(self):
        """100.001 → truncate 100.00 → already on 5-cent boundary → 100.00."""
        self.assertAlmostEqual(round_pcb(100.001), 100.00, places=2)

    def test_fractional_0_01(self):
        """0.01 → truncate 0.01 → ceiling 0.05."""
        self.assertAlmostEqual(round_pcb(0.01), 0.05, places=2)

    def test_fractional_0_05(self):
        """0.05 → truncate 0.05 → already on boundary → 0.05."""
        self.assertAlmostEqual(round_pcb(0.05), 0.05, places=2)

    def test_fractional_0_06(self):
        """0.06 → truncate 0.06 → ceiling 0.10."""
        self.assertAlmostEqual(round_pcb(0.06), 0.10, places=2)

    def test_fractional_0_09(self):
        """0.09 → truncate 0.09 → ceiling 0.10."""
        self.assertAlmostEqual(round_pcb(0.09), 0.10, places=2)

    def test_fractional_0_10(self):
        """0.10 → already on 5-cent boundary → 0.10."""
        self.assertAlmostEqual(round_pcb(0.10), 0.10, places=2)

    def test_truncation_no_roundup_123_044(self):
        """123.044 → truncate 123.04 (NOT 123.05) → ceiling 123.05."""
        self.assertAlmostEqual(round_pcb(123.044), 123.05, places=2)

    def test_truncation_prevents_roundup_123_094(self):
        """123.094 → truncate 123.09 (NOT 123.10) → ceiling 123.10."""
        self.assertAlmostEqual(round_pcb(123.094), 123.10, places=2)

    def test_already_on_boundary_250_50(self):
        """250.50 already on 5-cent boundary → stays 250.50."""
        self.assertAlmostEqual(round_pcb(250.50), 250.50, places=2)

    def test_high_value_rounding(self):
        """5000.123 → truncate 5000.12 → ceiling 5000.15."""
        self.assertAlmostEqual(round_pcb(5000.123), 5000.15, places=2)

    def test_high_value_on_boundary(self):
        """5000.10 → already on boundary → 5000.10."""
        self.assertAlmostEqual(round_pcb(5000.10), 5000.10, places=2)

    def test_output_always_5cent_aligned(self):
        """All outputs from round_pcb must be multiples of 0.05."""
        test_amounts = [
            0.001, 0.011, 0.021, 0.031, 0.041,
            0.051, 0.061, 0.071, 0.081, 0.091,
            1.234, 99.999, 500.501, 1234.567,
        ]
        for amount in test_amounts:
            result = round_pcb(amount)
            self.assertTrue(
                _is_5cent_aligned(result),
                msg=f"round_pcb({amount}) = {result} is not 5-cent aligned",
            )

    # --- Integration: verify all PCB calculation paths produce 5-cent aligned output ---

    def test_calculate_pcb_method1_output_5cent_aligned(self):
        """calculate_pcb() (Method 1) must return a 5-cent-aligned value."""
        result = calculate_pcb(60_000, resident=True, married=False, children=0)
        self.assertTrue(
            _is_5cent_aligned(result),
            msg=f"calculate_pcb() returned {result} which is not 5-cent aligned",
        )

    def test_calculate_pcb_method2_output_5cent_aligned(self):
        """calculate_pcb_method2() must return a 5-cent-aligned value."""
        result = calculate_pcb_method2(
            ytd_gross=30_000,
            ytd_pcb_deducted=100.0,
            month_number=6,
        )
        self.assertTrue(
            _is_5cent_aligned(result),
            msg=f"calculate_pcb_method2() returned {result} which is not 5-cent aligned",
        )

    def test_calculate_director_fee_pcb_5cent_aligned(self):
        """calculate_director_fee_pcb() must return a 5-cent-aligned value."""
        result = calculate_director_fee_pcb(
            total_fee=12_000,
            months_covered=3,
            resident=True,
            category=1,
        )
        self.assertTrue(
            _is_5cent_aligned(result),
            msg=f"calculate_director_fee_pcb() returned {result} which is not 5-cent aligned",
        )

    def test_non_resident_flat_rate_5cent_aligned(self):
        """Non-resident flat 30% path must also produce 5-cent-aligned output."""
        result = calculate_pcb(60_000, resident=False)
        self.assertTrue(
            _is_5cent_aligned(result),
            msg=f"Non-resident calculate_pcb() returned {result} which is not 5-cent aligned",
        )
