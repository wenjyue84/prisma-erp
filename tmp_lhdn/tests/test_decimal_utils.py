"""Tests for LHDN decimal utilities.

TDD Red Phase — these tests import from lhdn_payroll_integration.utils.decimal_utils
which does NOT exist yet. All tests should fail with ImportError.
"""

from decimal import Decimal

from frappe.tests.utils import FrappeTestCase

from lhdn_payroll_integration.utils.decimal_utils import (
    quantize,
    assert_totals_balance,
)


class TestDecimalUtils(FrappeTestCase):
    """Test decimal quantization and balance assertion utilities."""

    def test_quantize_0_1_plus_0_2_equals_0_30(self):
        """quantize should avoid floating point errors: 0.1 + 0.2 == 0.30."""
        result = quantize(Decimal("0.1") + Decimal("0.2"))
        self.assertEqual(result, Decimal("0.30"))

    def test_totals_balance_exact_passes(self):
        """assert_totals_balance should pass when subtotal + tax == total exactly."""
        # Should not raise
        assert_totals_balance(
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            total=Decimal("110.00"),
        )

    def test_totals_imbalance_raises_value_error(self):
        """assert_totals_balance should raise ValueError when totals don't balance."""
        with self.assertRaises(ValueError):
            assert_totals_balance(
                subtotal=Decimal("100"),
                tax=Decimal("0"),
                total=Decimal("100.01"),
            )
