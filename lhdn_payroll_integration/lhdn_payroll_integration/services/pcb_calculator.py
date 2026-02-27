"""LHDN PCB (Potongan Cukai Berjadual) / MTD monthly tax deduction calculator.

Implements LHDN progressive tax scale for resident and non-resident employees.
Provides calculate_pcb() for raw calculation and validate_pcb_amount() as a
whitelisted Frappe method for Salary Slip validation.

Tax bands (Assessment Year 2024 — Jadual PCB):
    0%      : 0 – 5,000
    1%      : 5,001 – 20,000
    3%      : 20,001 – 35,000
    8%      : 35,001 – 50,000
    13%     : 50,001 – 70,000
    21%     : 70,001 – 100,000
    24%     : 100,001 – 400,000
    24.5%   : 400,001 – 600,000
    25%     : 600,001 – 2,000,000
    26%     : above 2,000,000

Non-resident: flat 30% on gross income (no reliefs applied).
"""
import frappe

# LHDN progressive tax bands: (upper_limit, rate_percent, cumulative_tax_at_lower_bound)
# For each band: tax = cumulative_at_lower + (income - lower_bound) * rate
_TAX_BANDS = [
    (5_000,       0.00,  0.0),
    (20_000,      0.01,  0.0),
    (35_000,      0.03,  150.0),
    (50_000,      0.08,  600.0),
    (70_000,      0.13,  1_800.0),
    (100_000,     0.21,  4_400.0),
    (400_000,     0.24,  10_700.0),
    (600_000,     0.245, 82_700.0),
    (2_000_000,   0.25,  131_700.0),
    (float("inf"), 0.26, 481_700.0),
]

# Lower bounds derived from the bands above
_LOWER_BOUNDS = [0, 5_000, 20_000, 35_000, 50_000, 70_000, 100_000, 400_000, 600_000, 2_000_000]

# Standard personal relief amounts (RM)
_SELF_RELIEF = 9_000
_SPOUSE_RELIEF = 4_000
_CHILD_RELIEF_PER_CHILD = 2_000

# Warning threshold: warn if PCB deviates more than 10% from calculated
_WARNING_THRESHOLD = 0.10


def _compute_tax_on_chargeable_income(chargeable_income: float) -> float:
    """Compute annual income tax using LHDN progressive bands.

    Args:
        chargeable_income: Annual chargeable income after reliefs (RM).

    Returns:
        float: Annual tax amount (RM). Zero if chargeable_income <= 0.
    """
    if chargeable_income <= 0:
        return 0.0

    for i, (upper, rate, cumulative) in enumerate(_TAX_BANDS):
        if chargeable_income <= upper:
            excess = chargeable_income - _LOWER_BOUNDS[i]
            return cumulative + excess * rate

    # Should not reach here; last band has upper = inf
    return 0.0


def calculate_pcb(
    annual_income: float,
    resident: bool = True,
    married: bool = False,
    children: int = 0,
) -> float:
    """Calculate monthly PCB/MTD deduction amount.

    Applies standard reliefs for residents then uses LHDN progressive bands.
    Non-residents are taxed at flat 30% on gross income.

    Args:
        annual_income: Gross annual employment income (RM).
        resident: True if employee is a tax resident of Malaysia.
        married: True if employee is married (spouse relief applies).
        children: Number of qualifying children (RM2,000 each).

    Returns:
        float: Monthly PCB amount (RM), rounded to 2 decimal places.
               Returns 0.0 for zero or negative income.
    """
    if annual_income <= 0:
        return 0.0

    if not resident:
        # Non-resident: flat 30%, no reliefs
        annual_tax = annual_income * 0.30
        return round(annual_tax / 12, 2)

    # Resident: apply personal reliefs before tax computation
    total_relief = _SELF_RELIEF
    if married:
        total_relief += _SPOUSE_RELIEF
    total_relief += children * _CHILD_RELIEF_PER_CHILD

    chargeable_income = max(0.0, annual_income - total_relief)
    annual_tax = _compute_tax_on_chargeable_income(chargeable_income)
    return round(annual_tax / 12, 2)


@frappe.whitelist()
def validate_pcb_amount(doc_name: str) -> dict:
    """Validate PCB amount on a Salary Slip against LHDN calculated estimate.

    Fetches the Salary Slip, computes expected PCB using calculate_pcb(),
    and warns (does NOT block) if the actual PCB deviates more than 10%
    from the calculated estimate.

    Args:
        doc_name: Name of the Salary Slip document.

    Returns:
        dict with keys:
            - expected_monthly_pcb (float): Calculated monthly PCB.
            - actual_pcb (float): PCB found in the salary slip deductions.
            - deviation_pct (float): Absolute deviation as a fraction (e.g. 0.15 = 15%).
            - warning (bool): True if deviation exceeds threshold.
            - message (str): Human-readable result.
    """
    doc = frappe.get_doc("Salary Slip", doc_name)

    # Extract annual income from the slip
    monthly_gross = float(doc.gross_pay or 0)
    annual_income = monthly_gross * 12

    # Determine resident status (custom field, defaults to resident)
    resident = True
    married = False
    children = 0

    employee = frappe.get_doc("Employee", doc.employee)
    if hasattr(employee, "custom_tax_resident_status"):
        resident = (employee.custom_tax_resident_status or "Resident") == "Resident"
    if hasattr(employee, "custom_marital_status"):
        married = (employee.custom_marital_status or "") == "Married"
    if hasattr(employee, "custom_number_of_children"):
        children = int(employee.custom_number_of_children or 0)

    expected_monthly = calculate_pcb(annual_income, resident=resident, married=married, children=children)

    # Find PCB deduction component (look for "Monthly Tax Deduction" or "PCB")
    actual_pcb = 0.0
    for deduction in (doc.deductions or []):
        comp = (deduction.salary_component or "").lower()
        if "pcb" in comp or "monthly tax deduction" in comp or "mtd" in comp:
            actual_pcb += float(deduction.amount or 0)

    # Compute deviation
    if expected_monthly > 0:
        deviation = abs(actual_pcb - expected_monthly) / expected_monthly
    else:
        deviation = 0.0 if actual_pcb == 0 else 1.0

    over_threshold = deviation > _WARNING_THRESHOLD

    if over_threshold:
        message = (
            f"PCB Warning: Actual PCB RM {actual_pcb:,.2f} deviates "
            f"{deviation * 100:.1f}% from estimated RM {expected_monthly:,.2f}. "
            "Please verify against LHDN Jadual PCB."
        )
        frappe.msgprint(message, title="PCB Validation Warning", indicator="orange")
    else:
        message = (
            f"PCB OK: Actual RM {actual_pcb:,.2f} is within 10% of "
            f"estimated RM {expected_monthly:,.2f}."
        )

    return {
        "expected_monthly_pcb": expected_monthly,
        "actual_pcb": actual_pcb,
        "deviation_pct": round(deviation * 100, 2),
        "warning": over_threshold,
        "message": message,
    }
