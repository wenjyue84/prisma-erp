"""Perquisite exemption calculator for LHDN PCB (US-061).

ITA Section 13(1)(a) and Public Ruling No. 5/2019 exempt certain perquisites
from income tax up to annual ceilings:

- Transport/petrol/car allowance: RM6,000/year (business use)
- Childcare: RM2,400/year
- Mobile phone handset: 1 unit, fully exempt (ceiling=0 means unlimited)
- Group insurance premiums: wholly exempt (ceiling=0)
- Medical/dental/optical benefits: wholly exempt (ceiling=0)

Usage:
    from lhdn_payroll_integration.utils.exemption_calculator import calculate_taxable_component

    taxable = calculate_taxable_component(
        "Transport Allowance",
        annual_amount=8000,
        exemption_type="Transport",
        ceiling=6000,
    )  # returns 2000.0
"""

# Exemption type constants (must match custom_exemption_type Select options)
EXEMPTION_TYPE_NONE = "None"
EXEMPTION_TYPE_TRANSPORT = "Transport"
EXEMPTION_TYPE_CHILDCARE = "Childcare"
EXEMPTION_TYPE_GROUP_INSURANCE = "Group Insurance"
EXEMPTION_TYPE_MEDICAL = "Medical"
EXEMPTION_TYPE_MOBILE_PHONE = "Mobile Phone"
EXEMPTION_TYPE_OTHER = "Other"


def calculate_taxable_component(
    component_name: str,
    annual_amount: float,
    exemption_type: str = "None",
    ceiling: float = 0.0,
) -> float:
    """Calculate the taxable portion of a salary component after applying ITA exemption.

    Args:
        component_name: Name of the salary component (used for logging only).
        annual_amount: Gross annual amount of this component (RM).
        exemption_type: Type of exemption from the Salary Component custom field
            (None/Transport/Childcare/Group Insurance/Medical/Mobile Phone/Other).
            Pass "None" or empty string for fully taxable components.
        ceiling: Annual exemption ceiling (RM). A ceiling of 0 means the component
            is fully exempt with no upper limit (e.g. medical, group insurance).

    Returns:
        float: Taxable portion after applying the exemption ceiling (RM).
               Never negative. Returns full amount if exemption_type is "None".
               Returns 0.0 if ceiling == 0 (fully exempt).
               Returns max(0, annual_amount - ceiling) otherwise.
    """
    annual_amount = float(annual_amount or 0.0)
    ceiling = float(ceiling or 0.0)

    # No exemption type set — fully taxable
    if not exemption_type or exemption_type.strip() in ("", EXEMPTION_TYPE_NONE):
        return annual_amount

    # ceiling == 0 means fully exempt (no upper limit — e.g. medical, group insurance)
    if ceiling == 0.0:
        return 0.0

    # Partially exempt: taxable = annual_amount - ceiling (floored at 0)
    return max(0.0, annual_amount - ceiling)
