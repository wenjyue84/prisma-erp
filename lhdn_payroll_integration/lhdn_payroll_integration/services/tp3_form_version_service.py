"""TP3 Form Version Service — Process TP3(1/2026) Updated Form Format (US-218).

Manages TP3 form versioning to accommodate Budget 2026 relief changes.
When new employees join mid-year and declare income from a prior employer,
the system selects the correct TP3 form version based on the employee's
join year and processes the updated relief line items.

Form versions:
- TP3(1/2024): Legacy format with basic prior income fields
- TP3(1/2025): Intermediate format
- TP3(1/2026): Budget 2026 format with expanded relief line items
  (childcare RM3,000, learning disability RM10,000, expanded vaccination,
   eco-friendly lifestyle items)

Regulatory basis: LHDN PCB 2026 Specification Amendment; Borang TP3.
Official spec: https://www.hasil.gov.my/en/employers/employer-payroll-data-specification/
"""


# ---------------------------------------------------------------------------
# Constants — TP3 Form Versions
# ---------------------------------------------------------------------------

TP3_FORM_VERSION_2024 = "1/2024"
TP3_FORM_VERSION_2025 = "1/2025"
TP3_FORM_VERSION_2026 = "1/2026"

SUPPORTED_TP3_VERSIONS = [TP3_FORM_VERSION_2024, TP3_FORM_VERSION_2025, TP3_FORM_VERSION_2026]
CURRENT_TP3_VERSION = TP3_FORM_VERSION_2026

# Year-to-version mapping: joiners in a given year use that year's TP3 form
TP3_VERSION_BY_YEAR = {
    2024: TP3_FORM_VERSION_2024,
    2025: TP3_FORM_VERSION_2025,
    2026: TP3_FORM_VERSION_2026,
}

# Default version for years not explicitly mapped (future-proof)
DEFAULT_TP3_VERSION_FOR_UNKNOWN_YEAR = TP3_FORM_VERSION_2026


# ---------------------------------------------------------------------------
# TP3(1/2026) Budget 2026 Relief Line Items
# ---------------------------------------------------------------------------

# These are the relief fields that appear on the TP3(1/2026) form.
# Prior employer declares these values; new employer uses them in MTD.
TP3_2026_RELIEF_FIELDS = [
    "prior_childcare_centre_relief",      # RM3,000 max (Budget 2026)
    "prior_learning_disability_relief",    # RM10,000 max (Budget 2026)
    "prior_vaccination_relief",            # Expanded vaccination sub-relief
    "prior_eco_lifestyle_relief",          # Eco-friendly lifestyle items (Budget 2026)
    "prior_medical_parents_relief",        # Medical expenses for parents
    "prior_education_fees_relief",         # Self-education fees
    "prior_lifestyle_relief",             # Lifestyle (books, sports, internet, etc.)
    "prior_prs_annuity_relief",           # Private Retirement Scheme / annuity
    "prior_sspn_relief",                  # SSPN net deposit
    "prior_life_insurance_relief",        # Life insurance / takaful
    "prior_medical_insurance_relief",     # Medical / education insurance
    "prior_disabled_equipment_relief",    # Supporting equipment for disabled
    "prior_ev_charging_relief",           # EV charging facility (Budget 2026)
]

# Maximum relief amounts for TP3(1/2026) per LHDN Budget 2026 specification
TP3_2026_RELIEF_LIMITS = {
    "prior_childcare_centre_relief": 3000.0,
    "prior_learning_disability_relief": 10000.0,
    "prior_vaccination_relief": 1000.0,
    "prior_eco_lifestyle_relief": 2500.0,
    "prior_medical_parents_relief": 8000.0,
    "prior_education_fees_relief": 7000.0,
    "prior_lifestyle_relief": 2500.0,
    "prior_prs_annuity_relief": 3000.0,
    "prior_sspn_relief": 8000.0,
    "prior_life_insurance_relief": 7000.0,
    "prior_medical_insurance_relief": 3000.0,
    "prior_disabled_equipment_relief": 6000.0,
    "prior_ev_charging_relief": 2500.0,
}

# Base fields present in ALL TP3 versions
TP3_BASE_FIELDS = [
    "prior_gross_income",
    "prior_epf_deducted",
    "prior_pcb_deducted",
    "prior_socso_deducted",
    "prior_eis_deducted",
    "prior_zakat_paid",
]


# ---------------------------------------------------------------------------
# Form Version Selection
# ---------------------------------------------------------------------------

def get_tp3_form_version(join_year: int) -> str:
    """Determine the TP3 form version based on the employee's join year.

    Args:
        join_year: The calendar year the employee joined the current employer.

    Returns:
        str: Form version string (e.g. '1/2026').
    """
    join_year = int(join_year)
    return TP3_VERSION_BY_YEAR.get(join_year, DEFAULT_TP3_VERSION_FOR_UNKNOWN_YEAR)


def get_tp3_form_version_for_employee(date_of_joining: str) -> str:
    """Determine the TP3 form version from an employee's date of joining.

    Args:
        date_of_joining: ISO date string (e.g. '2026-03-15').

    Returns:
        str: Form version string.
    """
    if not date_of_joining:
        return CURRENT_TP3_VERSION

    year = int(str(date_of_joining)[:4])
    return get_tp3_form_version(year)


def is_version_supported(version: str) -> bool:
    """Check whether a TP3 form version is supported by the system.

    Args:
        version: Form version string (e.g. '1/2026').

    Returns:
        bool: True if version is supported.
    """
    return version in SUPPORTED_TP3_VERSIONS


# ---------------------------------------------------------------------------
# Field Definitions per Version
# ---------------------------------------------------------------------------

def get_tp3_fields_for_version(version: str) -> list:
    """Return the list of field names for a given TP3 form version.

    Args:
        version: TP3 form version string.

    Returns:
        list of str: Field names applicable to this version.
    """
    fields = list(TP3_BASE_FIELDS)

    if version == TP3_FORM_VERSION_2026:
        fields.extend(TP3_2026_RELIEF_FIELDS)
    elif version == TP3_FORM_VERSION_2025:
        # 2025 has a subset of relief fields (no Budget 2026 items)
        fields.extend([
            "prior_lifestyle_relief",
            "prior_prs_annuity_relief",
            "prior_sspn_relief",
            "prior_life_insurance_relief",
            "prior_medical_insurance_relief",
            "prior_medical_parents_relief",
            "prior_education_fees_relief",
        ])
    # 2024: base fields only

    return fields


def get_relief_fields_for_version(version: str) -> list:
    """Return only the relief-specific fields for a TP3 form version.

    Args:
        version: TP3 form version string.

    Returns:
        list of str: Relief field names (excludes base income/deduction fields).
    """
    all_fields = get_tp3_fields_for_version(version)
    return [f for f in all_fields if f not in TP3_BASE_FIELDS]


# ---------------------------------------------------------------------------
# TP3 Data Validation
# ---------------------------------------------------------------------------

def validate_tp3_data(data: dict, version: str) -> dict:
    """Validate TP3 declaration data against the form version rules.

    Checks:
    - All required base fields are present and non-negative
    - Relief values do not exceed TP3(1/2026) limits
    - Version is supported

    Args:
        data: dict of field_name -> value (RM amounts).
        version: TP3 form version string.

    Returns:
        dict with keys:
            valid (bool): True if all checks pass.
            errors (list of str): Validation error messages.
            warnings (list of str): Non-blocking warnings.
    """
    errors = []
    warnings = []

    if not is_version_supported(version):
        errors.append(f"Unsupported TP3 form version: {version}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Check base fields are present and non-negative
    for field in TP3_BASE_FIELDS:
        value = data.get(field)
        if value is None:
            # prior_gross_income and prior_pcb_deducted are required
            if field in ("prior_gross_income", "prior_pcb_deducted"):
                errors.append(f"Required field '{field}' is missing")
        elif float(value) < 0:
            errors.append(f"Field '{field}' cannot be negative: {value}")

    # Validate relief limits for TP3(1/2026)
    if version == TP3_FORM_VERSION_2026:
        for field in TP3_2026_RELIEF_FIELDS:
            value = data.get(field)
            if value is not None and float(value) < 0:
                errors.append(f"Relief field '{field}' cannot be negative: {value}")
            if value is not None and field in TP3_2026_RELIEF_LIMITS:
                limit = TP3_2026_RELIEF_LIMITS[field]
                if float(value) > limit:
                    warnings.append(
                        f"Relief '{field}' value RM{float(value):,.2f} exceeds "
                        f"limit RM{limit:,.2f} — will be capped"
                    )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def cap_relief_values(data: dict, version: str) -> dict:
    """Cap relief values to their statutory limits for a given version.

    Args:
        data: dict of field_name -> value (RM amounts).
        version: TP3 form version string.

    Returns:
        dict: Copy of data with relief values capped at statutory limits.
    """
    result = dict(data)

    if version == TP3_FORM_VERSION_2026:
        for field, limit in TP3_2026_RELIEF_LIMITS.items():
            if field in result and result[field] is not None:
                result[field] = min(float(result[field]), limit)

    return result


# ---------------------------------------------------------------------------
# TP3 → MTD Integration
# ---------------------------------------------------------------------------

def compute_total_prior_reliefs(data: dict, version: str) -> float:
    """Sum all prior employer relief values from a TP3 declaration.

    Used to feed into the MTD Method 2 calculation as tp1_reliefs equivalent.
    Values are capped at statutory limits before summing.

    Args:
        data: dict of TP3 field_name -> value (RM amounts).
        version: TP3 form version string.

    Returns:
        float: Total reliefs declared by prior employer (RM).
    """
    capped = cap_relief_values(data, version)
    relief_fields = get_relief_fields_for_version(version)

    total = 0.0
    for field in relief_fields:
        value = capped.get(field)
        if value is not None:
            total += max(0.0, float(value))

    return round(total, 2)


def build_mtd_carry_forward(data: dict, version: str) -> dict:
    """Build the carry-forward dict for MTD computation from TP3 data.

    Extracts base income/deduction figures and computes total prior reliefs,
    returning a structure ready for the PCB calculator.

    Args:
        data: dict of TP3 field_name -> value.
        version: TP3 form version string.

    Returns:
        dict with keys:
            tp3_prior_gross (float): Prior employer gross income.
            tp3_prior_pcb (float): Prior employer PCB deducted.
            tp3_prior_epf (float): Prior employer EPF deducted.
            tp3_prior_socso (float): Prior employer SOCSO deducted.
            tp3_prior_eis (float): Prior employer EIS deducted.
            tp3_prior_zakat (float): Prior employer Zakat paid.
            tp3_prior_reliefs (float): Sum of all capped relief values.
            tp3_form_version (str): Form version used.
    """
    return {
        "tp3_prior_gross": float(data.get("prior_gross_income") or 0),
        "tp3_prior_pcb": float(data.get("prior_pcb_deducted") or 0),
        "tp3_prior_epf": float(data.get("prior_epf_deducted") or 0),
        "tp3_prior_socso": float(data.get("prior_socso_deducted") or 0),
        "tp3_prior_eis": float(data.get("prior_eis_deducted") or 0),
        "tp3_prior_zakat": float(data.get("prior_zakat_paid") or 0),
        "tp3_prior_reliefs": compute_total_prior_reliefs(data, version),
        "tp3_form_version": version,
    }


def process_tp3_declaration(employee_join_date: str, tp3_data: dict, tp3_form_version: str = None) -> dict:
    """Process a complete TP3 declaration for a new hire.

    Determines the correct form version, validates data, caps reliefs,
    and returns the carry-forward structure for MTD computation.

    Args:
        employee_join_date: ISO date string of employee's join date.
        tp3_data: dict of TP3 field_name -> value.
        tp3_form_version: Optional explicit form version override.
            If None, version is determined from employee_join_date.

    Returns:
        dict with keys:
            success (bool): True if processing succeeded.
            carry_forward (dict): MTD carry-forward data (if success).
            validation (dict): Validation result with errors/warnings.
            form_version (str): TP3 form version used.
    """
    version = tp3_form_version or get_tp3_form_version_for_employee(employee_join_date)

    validation = validate_tp3_data(tp3_data, version)
    if not validation["valid"]:
        return {
            "success": False,
            "carry_forward": None,
            "validation": validation,
            "form_version": version,
        }

    carry_forward = build_mtd_carry_forward(tp3_data, version)

    return {
        "success": True,
        "carry_forward": carry_forward,
        "validation": validation,
        "form_version": version,
    }


def get_tp3_form_metadata(version: str) -> dict:
    """Return metadata about a TP3 form version for UI rendering.

    Args:
        version: TP3 form version string.

    Returns:
        dict with keys:
            version (str): Form version.
            title (str): Human-readable form title.
            fields (list): Field definitions for UI.
            relief_count (int): Number of relief line items.
            is_current (bool): Whether this is the latest version.
    """
    if not is_version_supported(version):
        return {"version": version, "title": "Unknown", "fields": [], "relief_count": 0, "is_current": False}

    titles = {
        TP3_FORM_VERSION_2024: "TP3 (1/2024) — Prior Employer Employment Information",
        TP3_FORM_VERSION_2025: "TP3 (1/2025) — Prior Employer Employment Information",
        TP3_FORM_VERSION_2026: "TP3 (1/2026) — Prior Employer Employment Information (Budget 2026)",
    }

    all_fields = get_tp3_fields_for_version(version)
    relief_fields = get_relief_fields_for_version(version)

    return {
        "version": version,
        "title": titles.get(version, f"TP3 ({version})"),
        "fields": all_fields,
        "relief_count": len(relief_fields),
        "is_current": version == CURRENT_TP3_VERSION,
    }
