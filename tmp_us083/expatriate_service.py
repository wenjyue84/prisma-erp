"""Expatriate Gross-Up Calculator and DTA Country Table (US-083).

Implements:
1. calculate_gross_up() — iterative solver that finds the gross salary
   that produces a desired net after Malaysian income tax.
2. is_resident() — residency test based on 182-day presence threshold.
3. DTA_COUNTRIES — dict of Double Tax Agreement countries with key treaty
   provisions relevant to short-term business visitors and employees.

References:
- ITA 1967 s.7: Resident status (182+ days in Malaysia in basis year)
- ITA 1967 s.6: Flat 30% rate for non-residents
- Malaysia DTA treaties: https://www.hasil.gov.my/en/double-taxation-agreement/
"""

# ---------------------------------------------------------------------------
# DTA country table
# keys: ISO 3166-1 alpha-2 country codes
# values: dict with treaty rate (withholding on employment income, %),
#         days_threshold (days in-country before employment income is taxable),
#         notes (key treaty provision summary)
# ---------------------------------------------------------------------------
DTA_COUNTRIES = {
    "SG": {
        "country": "Singapore",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Employment income exempt if present <183 days in calendar year, "
            "employer is not resident in Malaysia, and remuneration not borne by Malaysian PE."
        ),
    },
    "GB": {
        "country": "United Kingdom",
        "treaty_rate": 0.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Employment income taxable only in UK if employee present <183 days "
            "in Malaysian fiscal year and employer is not Malaysian resident."
        ),
    },
    "US": {
        "country": "United States",
        "treaty_rate": 0.0,
        "days_threshold": 183,
        "notes": (
            "No comprehensive DTA; Malaysia-US treaty covers limited categories. "
            "Employment income generally taxed under domestic law."
        ),
    },
    "AU": {
        "country": "Australia",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Exemption for short-term employment if present <183 days "
            "in aggregate in a 12-month period straddling the fiscal year."
        ),
    },
    "CN": {
        "country": "China",
        "treaty_rate": 10.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Employment income exempt if aggregate presence <183 days in 12-month "
            "period beginning/ending in fiscal year concerned."
        ),
    },
    "JP": {
        "country": "Japan",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Employment income taxable only in Japan if employee present <183 days "
            "in aggregate in the fiscal year."
        ),
    },
    "DE": {
        "country": "Germany",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Standard 183-day rule for short-term business visitors. "
            "Tax equalisation arrangements respected."
        ),
    },
    "NL": {
        "country": "Netherlands",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Employment income exempt for short-term assignments <183 days. "
        ),
    },
    "IN": {
        "country": "India",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Standard 183-day rule. Beneficial for Indian IT workers on "
            "short-term assignments."
        ),
    },
    "ID": {
        "country": "Indonesia",
        "treaty_rate": 15.0,
        "days_threshold": 183,
        "notes": (
            "Art. 15: Standard 183-day rule for employment income exemption."
        ),
    },
}

# ---------------------------------------------------------------------------
# Progressive tax bands (mirrored from pcb_calculator for self-contained use)
# (upper_limit, rate_percent, cumulative_tax_at_lower_bound)
# ---------------------------------------------------------------------------
_TAX_BANDS = [
    (5_000,        0.00,   0.0),
    (20_000,       0.01,   0.0),
    (35_000,       0.03,   150.0),
    (50_000,       0.08,   600.0),
    (70_000,       0.13,   1_800.0),
    (100_000,      0.21,   4_400.0),
    (400_000,      0.24,   10_700.0),
    (600_000,      0.245,  82_700.0),
    (2_000_000,    0.25,   131_700.0),
    (float("inf"), 0.26,   481_700.0),
]

_LOWER_BOUNDS = [0, 5_000, 20_000, 35_000, 50_000, 70_000, 100_000, 400_000, 600_000, 2_000_000]

# Non-resident flat rate (ITA 1967 s.6)
_NON_RESIDENT_RATE = 0.30

# Convergence tolerance (RM)
_CONVERGENCE_TOLERANCE = 0.01


def _compute_annual_tax(chargeable_income: float, resident: bool = True) -> float:
    """Compute annual Malaysian income tax on chargeable income.

    Args:
        chargeable_income: Annual chargeable income after reliefs (RM). Must be >= 0.
        resident: True for progressive resident bands; False for flat 30% non-resident.

    Returns:
        float: Annual tax payable (RM).
    """
    if chargeable_income <= 0:
        return 0.0

    if not resident:
        return chargeable_income * _NON_RESIDENT_RATE

    for i, (upper, rate, cumulative) in enumerate(_TAX_BANDS):
        if chargeable_income <= upper:
            excess = chargeable_income - _LOWER_BOUNDS[i]
            return cumulative + excess * rate

    return 0.0  # unreachable (last band is inf)


def _marginal_rate(chargeable_income: float) -> float:
    """Return the marginal tax rate at a given chargeable income level."""
    if chargeable_income <= 0:
        return 0.0
    for upper, rate, _ in _TAX_BANDS:
        if chargeable_income <= upper:
            return rate
    return _TAX_BANDS[-1][1]


def calculate_gross_up(
    desired_net_monthly: float,
    annual_reliefs: float = 0.0,
    category: int = 1,
    resident: bool = True,
    max_iterations: int = 50,
) -> dict:
    """Iterative gross-up solver: find gross that yields the desired net after tax.

    Tax-equalised expatriates receive a guaranteed net salary. The employer
    pays the tax differential. This function finds the gross salary G such that:

        G - annual_tax(G - annual_reliefs) / 12 = desired_net_monthly

    Algorithm (Newton-like fixed-point iteration):
        1. Annualise desired net: desired_net_annual = desired_net_monthly * 12
        2. Initial guess: gross_annual = desired_net_annual + tax_at_desired_net
        3. Each iteration: compute tax on (gross_annual - annual_reliefs),
           then update: gross_annual = desired_net_annual + annual_tax
        4. Stop when |net_from_guess - desired_net_monthly| < tolerance

    Args:
        desired_net_monthly: The take-home pay the employee should receive per month (RM).
        annual_reliefs: Total annual tax reliefs applicable (RM). Defaults to 0.
        category: PCB category (1=single/dual income, 2=married single income). Unused in
            current simplified model but retained for API compatibility.
        resident: True if employee is a Malaysian tax resident (>= 182 days presence).
            Non-residents are taxed at flat 30% — gross-up typically much higher.
        max_iterations: Maximum solver iterations before stopping (default 50).

    Returns:
        dict with keys:
            gross_monthly (float): Monthly gross required to achieve desired net.
            gross_annual (float): Annual gross.
            annual_tax (float): Total annual tax payable by employer.
            monthly_tax (float): Monthly tax top-up.
            net_monthly (float): Achieved net (should equal desired_net_monthly ± tolerance).
            converged (bool): True if solver converged within max_iterations.
            iterations (int): Number of iterations taken.
            resident (bool): Residency flag used.
    """
    desired_net_annual = desired_net_monthly * 12.0

    # Initial guess: assume we pay desired_net + tax on desired_net
    initial_chargeable = max(desired_net_annual - annual_reliefs, 0.0)
    initial_tax = _compute_annual_tax(initial_chargeable, resident=resident)
    gross_annual = desired_net_annual + initial_tax

    converged = False
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        chargeable = max(gross_annual - annual_reliefs, 0.0)
        annual_tax = _compute_annual_tax(chargeable, resident=resident)
        achieved_net_annual = gross_annual - annual_tax

        delta = achieved_net_annual - desired_net_annual

        if abs(delta) < _CONVERGENCE_TOLERANCE:
            converged = True
            break

        # Fixed-point update: gross = desired_net + tax_on_gross
        gross_annual = desired_net_annual + annual_tax

    # Final computation with converged gross
    chargeable = max(gross_annual - annual_reliefs, 0.0)
    annual_tax = _compute_annual_tax(chargeable, resident=resident)

    return {
        "gross_monthly": round(gross_annual / 12.0, 2),
        "gross_annual": round(gross_annual, 2),
        "annual_tax": round(annual_tax, 2),
        "monthly_tax": round(annual_tax / 12.0, 2),
        "net_monthly": round((gross_annual - annual_tax) / 12.0, 2),
        "converged": converged,
        "iterations": iteration,
        "resident": resident,
    }


def is_resident(presence_days: int) -> bool:
    """Determine Malaysian tax residency based on days of presence in calendar year.

    Under ITA 1967 s.7(1)(b), an individual is a resident if present in Malaysia
    for >= 182 days in the basis year for a year of assessment.

    Args:
        presence_days: Number of days present in Malaysia in the tax year.

    Returns:
        bool: True if resident (>= 182 days), False if non-resident (< 182 days).
    """
    return presence_days >= 182


def get_dta_country(country_code: str) -> dict | None:
    """Look up DTA treaty details for a country code.

    Args:
        country_code: ISO 3166-1 alpha-2 code (e.g. "SG", "GB").

    Returns:
        dict with treaty details, or None if no DTA found.
    """
    return DTA_COUNTRIES.get(country_code.upper() if country_code else "")
