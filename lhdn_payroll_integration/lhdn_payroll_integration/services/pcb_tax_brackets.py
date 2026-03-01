"""PCB progressive tax bracket tables keyed by assessment year (Jadual Pertama, ITA 1967).

Each year's table maps to a list of band tuples in the format:
    (upper_limit_inclusive, rate_as_decimal, cumulative_tax_at_lower_bound)

The ``get_tax_bands(year)`` function returns the correct (bands, lower_bounds)
pair for any given assessment year, falling back gracefully to the latest
defined year when future years are requested (forward-compatibility).

Assessment Year Reference:
    - YA2024: Pre-Budget 2023 top-tier revision (26% above RM2M)
    - YA2025: Budget 2023 rates fully effective; 30% top tier on >RM2M;
              Schedule 1 mid-bracket restructure (6%/11%/19%/25%/26%/28%/30%)
"""

# ---------------------------------------------------------------------------
# Band format: (upper_limit, rate_decimal, cumulative_tax_at_lower_bound)
# For each band:
#   tax = cumulative_at_lower_bound + (income - lower_bound) * rate
# ---------------------------------------------------------------------------

_BRACKETS: dict[int, list[tuple]] = {
    # -----------------------------------------------------------------------
    # YA2024 — Jadual Pertama (as per LHDN PCB Specification 2024)
    # -----------------------------------------------------------------------
    2024: [
        (5_000,          0.00,  0.0),         # 0 – 5,000 : 0%
        (20_000,         0.01,  0.0),         # 5,001 – 20,000 : 1%
        (35_000,         0.03,  150.0),       # 20,001 – 35,000 : 3%
        (50_000,         0.08,  600.0),       # 35,001 – 50,000 : 8%
        (70_000,         0.13,  1_800.0),     # 50,001 – 70,000 : 13%
        (100_000,        0.21,  4_400.0),     # 70,001 – 100,000 : 21%
        (400_000,        0.24,  10_700.0),    # 100,001 – 400,000 : 24%
        (600_000,        0.245, 82_700.0),    # 400,001 – 600,000 : 24.5%
        (2_000_000,      0.25,  131_700.0),   # 600,001 – 2,000,000 : 25%
        (float("inf"),   0.26,  481_700.0),   # above 2,000,000 : 26%
    ],
    # -----------------------------------------------------------------------
    # YA2025 — Jadual Pertama (LHDN PCB Specification 2025)
    # Budget 2023 introduced 30% top tier (>RM2M) effective YA2024/YA2025;
    # YA2025 restructures mid-bracket rates and introduces RM250K inflection.
    # Source: https://www.hasil.gov.my/en/individual/.../tax-rate/
    # -----------------------------------------------------------------------
    2025: [
        (5_000,          0.00,  0.0),         # 0 – 5,000 : 0%
        (20_000,         0.01,  0.0),         # 5,001 – 20,000 : 1%
        (35_000,         0.03,  150.0),       # 20,001 – 35,000 : 3%
        (50_000,         0.06,  600.0),       # 35,001 – 50,000 : 6%
        (70_000,         0.11,  1_500.0),     # 50,001 – 70,000 : 11%
        (100_000,        0.19,  3_700.0),     # 70,001 – 100,000 : 19%
        (250_000,        0.25,  9_400.0),     # 100,001 – 250,000 : 25%
        (400_000,        0.26,  46_900.0),    # 250,001 – 400,000 : 26%
        (2_000_000,      0.28,  85_900.0),    # 400,001 – 2,000,000 : 28%
        (float("inf"),   0.30,  533_900.0),   # above 2,000,000 : 30%
    ],
}

_LATEST_YEAR: int = max(_BRACKETS.keys())


def _derive_lower_bounds(bands: list[tuple]) -> list[float]:
    """Return the lower income bound for each band derived from the previous upper limit."""
    lower_bounds = [0.0]
    for band in bands[:-1]:
        lower_bounds.append(float(band[0]))
    return lower_bounds


def get_tax_bands(year: int) -> tuple[list[tuple], list[float]]:
    """Return ``(bands, lower_bounds)`` for the requested assessment year.

    Selection logic:
    - Exact match: returns defined year table.
    - Year > latest defined: falls back to ``_LATEST_YEAR`` (forward-compat).
    - Year < earliest defined: falls back to the earliest year available.

    Args:
        year: Assessment year (e.g. 2024, 2025).

    Returns:
        Tuple of (bands_list, lower_bounds_list) where:
          bands_list = [(upper, rate, cumulative), ...]
          lower_bounds_list = [0, prev_upper, ...]
    """
    if year in _BRACKETS:
        bands = _BRACKETS[year]
    elif year > _LATEST_YEAR:
        bands = _BRACKETS[_LATEST_YEAR]
    else:
        # Nearest earlier year
        earlier = sorted(y for y in _BRACKETS if y <= year)
        bands = _BRACKETS[earlier[-1]] if earlier else _BRACKETS[_LATEST_YEAR]

    return bands, _derive_lower_bounds(bands)
