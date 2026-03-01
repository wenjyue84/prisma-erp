"""e-Invoice Mandatory Phase Readiness Check for Employer Company Records.

LHDN's e-invoice mandate rolls out in phases based on annual turnover:
  - **Phase 1** (Aug 2024): Annual revenue > RM100M
  - **Phase 2** (Jan 2025): Annual revenue > RM25M
  - **Phase 3** (Jul 2025): Annual revenue > RM150K
  - **Phase 4+** (TBD): All remaining businesses

Many employers using the payroll app are SMEs who crossed Phase 3 threshold
in July 2025 and must now have MyInvois credentials configured. This service
detects whether the employer's revenue tier requires active e-invoice compliance
and warns HR if MyInvois API credentials are missing or incomplete.

This is a pre-flight guard only — it does not prevent payroll runs but flags
the MyInvois gap for action.

US-242: e-Invoice Mandatory Phase Readiness Check for Employer Company Records.
"""

from datetime import date

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Phase thresholds in RM (annual revenue)
PHASE_1_THRESHOLD = 100_000_000  # RM100M
PHASE_2_THRESHOLD = 25_000_000   # RM25M
PHASE_3_THRESHOLD = 150_000      # RM150K

# Phase labels
PHASE_1_LABEL = ">RM100M (Phase 1)"
PHASE_2_LABEL = ">RM25M (Phase 2)"
PHASE_3_LABEL = ">RM150K (Phase 3)"
PHASE_4_LABEL = "All Businesses (Phase 4+)"
VOLUNTARY_LABEL = "Below RM150K (Voluntary)"

# Phase effective dates
PHASE_1_DATE = date(2024, 8, 1)
PHASE_2_DATE = date(2025, 1, 1)
PHASE_3_DATE = date(2025, 7, 1)
PHASE_4_DATE = None  # TBD — LHDN has not finalized

# Ordered phase thresholds (highest first for matching)
PHASE_THRESHOLDS = [
    (PHASE_1_THRESHOLD, PHASE_1_LABEL, PHASE_1_DATE),
    (PHASE_2_THRESHOLD, PHASE_2_LABEL, PHASE_2_DATE),
    (PHASE_3_THRESHOLD, PHASE_3_LABEL, PHASE_3_DATE),
]

# Compliance statuses
STATUS_COMPLIANT = "Compliant"
STATUS_CREDENTIALS_MISSING = "Credentials Missing"
STATUS_VOLUNTARY = "Voluntary"
STATUS_NOT_APPLICABLE = "Not Applicable"

# Custom field names on Company DocType
FIELD_ANNUAL_REVENUE = "custom_annual_revenue"
FIELD_EINVOICE_MANDATE_PHASE = "custom_einvoice_mandate_phase"
FIELD_CLIENT_ID = "custom_client_id"
FIELD_CLIENT_SECRET = "custom_client_secret"

# Warning message template
CREDENTIALS_WARNING = (
    "e-Invoice mandatory for this company — "
    "MyInvois API credentials are missing"
)

# Phase transition alert subject
PHASE_TRANSITION_SUBJECT = (
    "e-Invoice Phase Change Alert: {company_name} moved to {new_phase}"
)


# ---------------------------------------------------------------------------
# Phase Determination
# ---------------------------------------------------------------------------


def determine_mandate_phase(annual_revenue):
    """Determine the e-invoice mandate phase based on annual revenue.

    Args:
        annual_revenue: Annual revenue in RM (numeric). None or negative
            values are treated as zero.

    Returns:
        str: The mandate phase label (e.g. '>RM100M (Phase 1)').
    """
    if annual_revenue is None or annual_revenue < 0:
        annual_revenue = 0

    for threshold, label, _effective_date in PHASE_THRESHOLDS:
        if annual_revenue > threshold:
            return label

    return VOLUNTARY_LABEL


def get_phase_effective_date(phase_label):
    """Get the effective date for a given phase label.

    Args:
        phase_label: The phase label string.

    Returns:
        date or None: The effective date, or None if TBD / voluntary.
    """
    for _threshold, label, effective_date in PHASE_THRESHOLDS:
        if label == phase_label:
            return effective_date

    if phase_label == PHASE_4_LABEL:
        return PHASE_4_DATE  # None — TBD

    return None


def is_mandatory_phase(phase_label):
    """Check if a phase label represents a mandatory e-invoice phase.

    Args:
        phase_label: The phase label string.

    Returns:
        bool: True if the phase is mandatory (not Voluntary).
    """
    return phase_label not in (VOLUNTARY_LABEL, None, "")


def is_phase_active(phase_label, as_of=None):
    """Check if a mandatory phase is currently active (effective date passed).

    Args:
        phase_label: The phase label string.
        as_of: Date to check against. Defaults to today.

    Returns:
        bool: True if the phase is mandatory AND its effective date has passed.
    """
    if not is_mandatory_phase(phase_label):
        return False

    effective = get_phase_effective_date(phase_label)
    if effective is None:
        # Phase 4+ — date TBD, treat as not yet active
        return False

    if as_of is None:
        as_of = date.today()

    return as_of >= effective


# ---------------------------------------------------------------------------
# Credential Checks
# ---------------------------------------------------------------------------


def has_myinvois_credentials(client_id, client_secret):
    """Check if MyInvois API credentials are present.

    Args:
        client_id: The custom_client_id value.
        client_secret: The custom_client_secret value.

    Returns:
        bool: True if both client_id and client_secret are non-empty strings.
    """
    return bool(client_id and str(client_id).strip()) and bool(
        client_secret and str(client_secret).strip()
    )


def check_credentials_complete(company_data):
    """Check if a company's MyInvois credentials are fully configured.

    Args:
        company_data: Dict with keys matching FIELD_CLIENT_ID, FIELD_CLIENT_SECRET.

    Returns:
        dict: {
            'has_client_id': bool,
            'has_client_secret': bool,
            'is_complete': bool
        }
    """
    client_id = company_data.get(FIELD_CLIENT_ID, "")
    client_secret = company_data.get(FIELD_CLIENT_SECRET, "")

    has_id = bool(client_id and str(client_id).strip())
    has_secret = bool(client_secret and str(client_secret).strip())

    return {
        "has_client_id": has_id,
        "has_client_secret": has_secret,
        "is_complete": has_id and has_secret,
    }


# ---------------------------------------------------------------------------
# Company Readiness Assessment
# ---------------------------------------------------------------------------


def assess_company_readiness(company_data):
    """Assess a single company's e-invoice readiness.

    Args:
        company_data: Dict with keys:
            - 'name': Company name/ID
            - 'custom_annual_revenue': Annual revenue in RM
            - 'custom_client_id': MyInvois client ID
            - 'custom_client_secret': MyInvois client secret

    Returns:
        dict: {
            'company': str,
            'annual_revenue': float,
            'mandate_phase': str,
            'is_mandatory': bool,
            'is_phase_active': bool,
            'credentials_complete': bool,
            'compliance_status': str,
            'warning': str or None
        }
    """
    company_name = company_data.get("name", "Unknown")
    revenue = company_data.get(FIELD_ANNUAL_REVENUE, 0) or 0
    phase = determine_mandate_phase(revenue)
    mandatory = is_mandatory_phase(phase)
    active = is_phase_active(phase)
    creds = check_credentials_complete(company_data)

    # Determine compliance status
    if not mandatory:
        status = STATUS_VOLUNTARY
    elif creds["is_complete"]:
        status = STATUS_COMPLIANT
    else:
        status = STATUS_CREDENTIALS_MISSING

    # Generate warning if mandatory but credentials missing
    warning = None
    if mandatory and not creds["is_complete"]:
        warning = CREDENTIALS_WARNING

    return {
        "company": company_name,
        "annual_revenue": float(revenue),
        "mandate_phase": phase,
        "is_mandatory": mandatory,
        "is_phase_active": active,
        "credentials_complete": creds["is_complete"],
        "compliance_status": status,
        "warning": warning,
    }


def assess_multiple_companies(companies_data):
    """Assess e-invoice readiness for multiple companies.

    Args:
        companies_data: List of company data dicts (same format as
            assess_company_readiness).

    Returns:
        list: List of readiness assessment dicts.
    """
    return [assess_company_readiness(c) for c in (companies_data or [])]


# ---------------------------------------------------------------------------
# Readiness Report
# ---------------------------------------------------------------------------


def generate_readiness_report(companies_data):
    """Generate an e-Invoice Readiness Report for all companies.

    Args:
        companies_data: List of company data dicts.

    Returns:
        dict: {
            'total_companies': int,
            'compliant': int,
            'credentials_missing': int,
            'voluntary': int,
            'compliance_rate': float (percentage among mandatory companies),
            'companies': list of assessment dicts,
            'action_required': list of companies needing credentials
        }
    """
    assessments = assess_multiple_companies(companies_data)

    compliant = sum(1 for a in assessments if a["compliance_status"] == STATUS_COMPLIANT)
    missing = sum(1 for a in assessments if a["compliance_status"] == STATUS_CREDENTIALS_MISSING)
    voluntary = sum(1 for a in assessments if a["compliance_status"] == STATUS_VOLUNTARY)

    mandatory_count = compliant + missing
    compliance_rate = (
        round((compliant / mandatory_count) * 100, 2) if mandatory_count > 0 else 100.0
    )

    action_required = [a for a in assessments if a["compliance_status"] == STATUS_CREDENTIALS_MISSING]

    return {
        "total_companies": len(assessments),
        "compliant": compliant,
        "credentials_missing": missing,
        "voluntary": voluntary,
        "compliance_rate": compliance_rate,
        "companies": assessments,
        "action_required": action_required,
    }


# ---------------------------------------------------------------------------
# Phase Transition Detection
# ---------------------------------------------------------------------------


def detect_phase_transition(old_revenue, new_revenue):
    """Detect if a revenue change causes a phase transition.

    Args:
        old_revenue: Previous annual revenue in RM.
        new_revenue: New annual revenue in RM.

    Returns:
        dict or None: If transition detected:
            {
                'old_phase': str,
                'new_phase': str,
                'old_revenue': float,
                'new_revenue': float,
                'is_upgrade': bool (moved to higher mandatory phase),
                'is_downgrade': bool (moved to lower phase),
                'now_mandatory': bool (was voluntary, now mandatory)
            }
            None if no phase change.
    """
    old_phase = determine_mandate_phase(old_revenue)
    new_phase = determine_mandate_phase(new_revenue)

    if old_phase == new_phase:
        return None

    old_mandatory = is_mandatory_phase(old_phase)
    new_mandatory = is_mandatory_phase(new_phase)

    # Determine phase ordering for upgrade/downgrade
    phase_order = {
        VOLUNTARY_LABEL: 0,
        PHASE_3_LABEL: 1,
        PHASE_2_LABEL: 2,
        PHASE_1_LABEL: 3,
        PHASE_4_LABEL: 0,  # Same level as voluntary until date set
    }

    old_rank = phase_order.get(old_phase, 0)
    new_rank = phase_order.get(new_phase, 0)

    return {
        "old_phase": old_phase,
        "new_phase": new_phase,
        "old_revenue": float(old_revenue or 0),
        "new_revenue": float(new_revenue or 0),
        "is_upgrade": new_rank > old_rank,
        "is_downgrade": new_rank < old_rank,
        "now_mandatory": not old_mandatory and new_mandatory,
    }


# ---------------------------------------------------------------------------
# Notification Builders
# ---------------------------------------------------------------------------


def build_phase_transition_alert(company_name, transition):
    """Build an alert notification for a phase transition.

    Args:
        company_name: The company name.
        transition: Dict from detect_phase_transition().

    Returns:
        dict: {
            'subject': str,
            'message': str,
            'severity': str ('warning' or 'info'),
            'company': str,
            'old_phase': str,
            'new_phase': str
        }
    """
    if transition is None:
        return None

    new_phase = transition["new_phase"]
    old_phase = transition["old_phase"]

    subject = PHASE_TRANSITION_SUBJECT.format(
        company_name=company_name, new_phase=new_phase
    )

    if transition["now_mandatory"]:
        severity = "warning"
        message = (
            f"{company_name} has moved from '{old_phase}' to '{new_phase}'. "
            f"e-Invoice submission is now MANDATORY. "
            f"Please ensure MyInvois API credentials (Client ID and Client Secret) "
            f"are configured in the Company settings."
        )
    elif transition["is_upgrade"]:
        severity = "info"
        message = (
            f"{company_name} has moved from '{old_phase}' to '{new_phase}'. "
            f"The company remains in a mandatory e-invoice phase."
        )
    elif transition["is_downgrade"]:
        severity = "info"
        message = (
            f"{company_name} has moved from '{old_phase}' to '{new_phase}'. "
            f"Please verify the annual revenue figure is correct."
        )
    else:
        severity = "info"
        message = (
            f"{company_name} phase changed from '{old_phase}' to '{new_phase}'."
        )

    return {
        "subject": subject,
        "message": message,
        "severity": severity,
        "company": company_name,
        "old_phase": old_phase,
        "new_phase": new_phase,
    }


def build_credentials_warning(company_name, mandate_phase):
    """Build a warning message for missing credentials on a mandatory company.

    Args:
        company_name: The company name.
        mandate_phase: The mandate phase label.

    Returns:
        dict or None: Warning dict if mandatory and action needed, else None.
    """
    if not is_mandatory_phase(mandate_phase):
        return None

    return {
        "company": company_name,
        "mandate_phase": mandate_phase,
        "message": CREDENTIALS_WARNING,
        "severity": "warning",
        "action": (
            f"Configure MyInvois API credentials (Client ID and Client Secret) "
            f"in {company_name} > LHDN Malaysia Setup tab."
        ),
    }


# ---------------------------------------------------------------------------
# Summary Dashboard
# ---------------------------------------------------------------------------


def generate_dashboard_summary(companies_data):
    """Generate a summary for the e-Invoice readiness dashboard.

    Args:
        companies_data: List of company data dicts.

    Returns:
        dict: {
            'total_companies': int,
            'by_phase': dict mapping phase_label -> count,
            'by_status': dict mapping status -> count,
            'compliance_rate': float,
            'mandatory_count': int,
            'voluntary_count': int,
            'action_items': list of warning dicts for non-compliant mandatory companies,
            'phase_4_note': str
        }
    """
    report = generate_readiness_report(companies_data)
    assessments = report["companies"]

    by_phase = {}
    for a in assessments:
        phase = a["mandate_phase"]
        by_phase[phase] = by_phase.get(phase, 0) + 1

    by_status = {}
    for a in assessments:
        status = a["compliance_status"]
        by_status[status] = by_status.get(status, 0) + 1

    action_items = []
    for a in assessments:
        if a["compliance_status"] == STATUS_CREDENTIALS_MISSING:
            warning = build_credentials_warning(a["company"], a["mandate_phase"])
            if warning:
                action_items.append(warning)

    return {
        "total_companies": report["total_companies"],
        "by_phase": by_phase,
        "by_status": by_status,
        "compliance_rate": report["compliance_rate"],
        "mandatory_count": report["compliant"] + report["credentials_missing"],
        "voluntary_count": report["voluntary"],
        "action_items": action_items,
        "phase_4_note": (
            "Phase 4 (all remaining businesses) effective date is TBD — "
            "LHDN has not finalized the date. Monitor announcements at "
            "https://www.hasil.gov.my/en/e-invoice/"
        ),
    }
