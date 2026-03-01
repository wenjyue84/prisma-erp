"""Gratuity calculator for LHDN payroll integration.

Implements ITA 1967 Schedule 6 paragraph 25 exemption for gratuity payments:
- Approved Fund Gratuity: exempt = min(total_gratuity, RM1,000 x years_of_service)
- Non-Approved Gratuity: no exemption (fully taxable)
- Ex-Gratia: no exemption under paragraph 25 (may be fully exempt under para 30
  if employee qualifies — handled separately by US-085 logic in pcb_calculator.py)

Gratuity types are encoded in the Salary Component names:
  'Gratuity - Approved Fund'   -> GRATUITY_TYPE_APPROVED
  'Gratuity - Non-Approved'    -> GRATUITY_TYPE_NON_APPROVED
  'Gratuity - Ex-Gratia'       -> GRATUITY_TYPE_EX_GRATIA

US-125: Approved Gratuity Fund Contribution and Tax-Exempt Gratuity Declaration for EA Form
"""

# ITA 1967 Schedule 6 paragraph 25: RM1,000 per completed year of service
GRATUITY_EXEMPT_PER_YEAR = 1_000.0

# Valid gratuity types
GRATUITY_TYPE_APPROVED = "Approved Fund Gratuity"
GRATUITY_TYPE_NON_APPROVED = "Non-Approved Gratuity"
GRATUITY_TYPE_EX_GRATIA = "Ex-Gratia"

# Map from Salary Component name suffix to gratuity type
_COMPONENT_TYPE_MAP = {
    "Gratuity - Approved Fund": GRATUITY_TYPE_APPROVED,
    "Gratuity - Non-Approved": GRATUITY_TYPE_NON_APPROVED,
    "Gratuity - Ex-Gratia": GRATUITY_TYPE_EX_GRATIA,
}

# EA Form section for gratuity (Borang EA Part B line B5)
EA_FORM_SECTION = "B5 Gratuity"


def get_gratuity_type_from_component(component_name: str) -> str:
    """Infer gratuity type string from salary component name.

    Args:
        component_name: Name of the Salary Component document.

    Returns:
        One of GRATUITY_TYPE_APPROVED, GRATUITY_TYPE_NON_APPROVED,
        GRATUITY_TYPE_EX_GRATIA, or 'Unknown' for unrecognised names.
    """
    return _COMPONENT_TYPE_MAP.get(component_name, GRATUITY_TYPE_NON_APPROVED)


def calculate_gratuity_exemption(
    gratuity_amount: float,
    gratuity_type: str,
    years_of_service: float,
) -> dict:
    """Calculate the exempt and taxable portions of a gratuity payment.

    Under ITA 1967, Schedule 6, paragraph 25, gratuity from an approved fund
    is exempt up to RM1,000 per completed year of service. The taxable balance
    is subject to PCB using the annualisation rule (irregular payment treatment).

    Args:
        gratuity_amount: Total gross gratuity received (RM).
        gratuity_type: One of 'Approved Fund Gratuity', 'Non-Approved Gratuity',
            or 'Ex-Gratia'. Only 'Approved Fund Gratuity' qualifies for the
            Schedule 6 para 25 partial exemption.
        years_of_service: Completed years of service (float or int).
            Used for the RM1,000/year exemption cap. Fractional years are
            floored to whole completed years.

    Returns:
        dict with keys:
            gratuity_type     : str — the input gratuity type
            gross_gratuity    : float — total gratuity amount
            exempt_gratuity   : float — tax-exempt portion (ITA Sch. 6 para 25)
            taxable_gratuity  : float — amount subject to PCB (irregular payment)
            years_of_service  : int — completed years used for exemption calc
            exemption_limit   : float — RM1,000 x completed years cap
            ea_form_section   : str — always 'B5 Gratuity' for EA Form mapping
            warning           : str — non-empty if years_of_service is 0 or missing
    """
    completed_years = int(years_of_service or 0)
    warning = ""

    if completed_years <= 0 and gratuity_type == GRATUITY_TYPE_APPROVED:
        warning = (
            "Years of service is 0 or not set. Cannot calculate Schedule 6 para 25 "
            "exemption. Please set 'Date Joined Company' on the Employee record."
        )

    exemption_limit = GRATUITY_EXEMPT_PER_YEAR * completed_years

    if gratuity_type == GRATUITY_TYPE_APPROVED:
        exempt_gratuity = min(float(gratuity_amount), exemption_limit)
    else:
        # Non-Approved Gratuity and Ex-Gratia have no para 25 exemption
        exempt_gratuity = 0.0

    taxable_gratuity = max(0.0, float(gratuity_amount) - exempt_gratuity)

    return {
        "gratuity_type": gratuity_type,
        "gross_gratuity": round(float(gratuity_amount), 2),
        "exempt_gratuity": round(exempt_gratuity, 2),
        "taxable_gratuity": round(taxable_gratuity, 2),
        "years_of_service": completed_years,
        "exemption_limit": round(exemption_limit, 2),
        "ea_form_section": EA_FORM_SECTION,
        "warning": warning,
    }


def get_ea_form_gratuity_amounts(gratuity_results: list) -> dict:
    """Aggregate multiple gratuity payments for EA Form B5 reporting.

    EA Form Part B (Borang EA) requires the total gratuity in B5 (Imbuhan).
    The exempt portion is not included in chargeable employment income.

    Args:
        gratuity_results: List of dicts returned by calculate_gratuity_exemption().

    Returns:
        dict with:
            total_gross    : float — sum of all gratuity payments
            total_exempt   : float — total exempt under Sch. 6 para 25
            total_taxable  : float — total subject to PCB
            ea_section     : str — 'B5 Gratuity'
    """
    total_gross = sum(r.get("gross_gratuity", 0.0) for r in gratuity_results)
    total_exempt = sum(r.get("exempt_gratuity", 0.0) for r in gratuity_results)
    total_taxable = sum(r.get("taxable_gratuity", 0.0) for r in gratuity_results)

    return {
        "total_gross": round(total_gross, 2),
        "total_exempt": round(total_exempt, 2),
        "total_taxable": round(total_taxable, 2),
        "ea_section": EA_FORM_SECTION,
    }
