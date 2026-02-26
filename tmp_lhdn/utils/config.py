"""LHDN environment configuration utilities.

Reads LHDN API settings from Frappe site config to support
sandbox/production environment toggle without hardcoded URLs.
Also provides mandatory e-invoice date gating per company revenue tier.
"""

from datetime import date

import frappe

SANDBOX_URL_DEFAULT = "https://preprod-api.myinvois.hasil.gov.my"
PRODUCTION_URL_DEFAULT = "https://api.myinvois.hasil.gov.my"


def get_lhdn_base_url():
    """Get the LHDN MyInvois API base URL based on site config.

    Reads lhdn_environment from site config ('sandbox' or 'production').
    Defaults to 'sandbox' if not set (safe default).

    Returns:
        str: The LHDN API base URL.
    """
    env = frappe.conf.get("lhdn_environment", "sandbox") or "sandbox"

    if env == "production":
        return frappe.conf.get("lhdn_production_url", PRODUCTION_URL_DEFAULT) or PRODUCTION_URL_DEFAULT
    else:
        return frappe.conf.get("lhdn_sandbox_url", SANDBOX_URL_DEFAULT) or SANDBOX_URL_DEFAULT


def get_einvoice_version():
    """Get the LHDN e-Invoice version from site config.

    Returns:
        str: The e-Invoice version (e.g. '1.0' or '1.1'). Defaults to '1.0'.
    """
    return frappe.conf.get("lhdn_einvoice_version", "1.0") or "1.0"


# Per December 2025 Cabinet decision — mandatory e-invoice dates by revenue tier
MANDATORY_DATES = {
    "Above RM100M": date(2024, 8, 1),
    "RM25M to RM100M": date(2025, 1, 1),
    "RM5M to RM25M": date(2025, 7, 1),
    "RM1M to RM5M": date(2026, 1, 1),
    "Below RM1M (Exempt)": None,
}


def get_mandatory_date(tier):
    """Get the mandatory e-invoice compliance date for the given revenue tier.

    Args:
        tier: One of the MANDATORY_DATES keys (e.g. 'Above RM100M').

    Returns:
        date or None: The mandatory compliance date, or None if exempt.
    """
    return MANDATORY_DATES.get(tier)


def check_mandatory_compliance(company_name):
    """Check if a company's LHDN e-invoice compliance is mandatory yet.

    In sandbox mode, bypasses the check entirely.
    In production mode before the mandatory date, logs a warning.

    Args:
        company_name: The Company name to check.
    """
    env = frappe.conf.get("lhdn_environment", "sandbox")
    if env == "sandbox":
        return

    tier = frappe.db.get_value("Company", company_name, "custom_annual_revenue_tier")
    mandatory = get_mandatory_date(tier)

    if mandatory and str(frappe.utils.today()) < str(mandatory):
        frappe.log_error(
            message=f"Company '{company_name}' (tier: {tier}) is submitting e-invoices "
                    f"before the mandatory date {mandatory}. Mandatory compliance "
                    f"starts {mandatory}.",
            title="LHDN Compliance Warning",
        )
