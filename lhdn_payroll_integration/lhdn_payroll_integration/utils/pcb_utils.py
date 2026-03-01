"""PCB utility functions for LHDN payroll integration.

Implements the LHDN PCB 2026 Computerised Calculation Specification rounding rule.

Per LHDN PCB 2026 Spec (Spesifikasi Kaedah Pengiraan Berkomputer PCB 2026):
    'Pengiraan berkomputer PCB hendaklah dalam dua titik perpuluhan dan mesti
    mengabaikan sebarang angka berikutnya (cth: 123.023 ≈ 123.02). Dari situ,
    amaun perlu dibundarkan kepada 5 sen yang paling hampir ke atas;
    cth: 123.02 ≈ 123.05 manakala 123.06 ≈ 123.10'
"""
from decimal import Decimal, ROUND_DOWN


def round_pcb(amount: float) -> float:
    """Apply LHDN PCB 2026 two-step rounding rule to a raw PCB/MTD amount.

    Step 1: Truncate to exactly 2 decimal places (drop all subsequent digits,
            no rounding up). Uses Decimal to avoid floating-point precision errors.

    Step 2: Apply ceiling rounding to the nearest 5 cents. Uses integer arithmetic
            on cents to avoid float imprecision.

    Examples::

        round_pcb(123.023)  → 123.05   (123.023 → 123.02 → 123.05)
        round_pcb(123.061)  → 123.10   (123.061 → 123.06 → 123.10)
        round_pcb(123.000)  → 123.00   (123.000 → 123.00 → already on 5-cent boundary)
        round_pcb(123.049)  → 123.05   (123.049 → 123.04 → 123.05)
        round_pcb(0.00)     → 0.00
        round_pcb(100.01)   → 100.05   (100.01 → 100.01 → 100.05)
        round_pcb(100.00)   → 100.00   (100.00 → 100.00 → already on 5-cent boundary)

    Args:
        amount: Raw PCB/MTD amount in RM (float or Decimal).

    Returns:
        float: PCB amount rounded per LHDN PCB 2026 spec, to 2 decimal places.
               Returns 0.0 for zero or negative input.
    """
    if amount <= 0:
        return 0.0

    # Step 1: Truncate to 2 decimal places (ROUND_DOWN = truncate toward zero for positives)
    truncated = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    # Step 2: Ceiling to nearest 5 cents using integer arithmetic to avoid float imprecision.
    # Convert to integer cents (e.g., 123.02 → 12302), then round up to next multiple of 5.
    cents = int(truncated * 100)
    remainder = cents % 5
    if remainder != 0:
        cents += 5 - remainder

    return round(cents / 100, 2)
