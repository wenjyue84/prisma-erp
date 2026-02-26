"""LHDN environment configuration utilities.

Reads LHDN API settings from Frappe site config to support
sandbox/production environment toggle without hardcoded URLs.
"""

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
