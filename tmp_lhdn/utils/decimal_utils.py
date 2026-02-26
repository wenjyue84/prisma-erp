"""Decimal utilities for LHDN payroll integration."""
from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def quantize(value):
    """Quantize a value to 2 decimal places using ROUND_HALF_UP.

    Args:
        value: A numeric value (Decimal, int, float, or str).

    Returns:
        Decimal: The value quantized to 2 decimal places.
    """
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def assert_totals_balance(subtotal, tax, total):
    """Assert that subtotal + tax == total exactly (2dp precision).

    Args:
        subtotal: Decimal tax-exclusive amount.
        tax: Decimal tax amount.
        total: Decimal tax-inclusive amount.

    Raises:
        ValueError: If subtotal + tax != total after quantization.
    """
    expected = quantize(subtotal) + quantize(tax)
    actual = quantize(total)
    if expected != actual:
        raise ValueError(
            f"Totals imbalance: {subtotal} + {tax} = {expected} != {actual}"
        )
