"""US-203: e-CP22 Online-Only Mandatory Submission and Wakil Majikan Authorization Check.

Effective 1 September 2024, LHDN mandates that all CP22 new employee notifications must
be submitted exclusively through the e-CP22 system on MyTax Portal. Manual paper
submissions to LHDN offices are no longer accepted.

Submission can only be made by:
  - Company director (with MyTax Employer role), OR
  - Registered Employer Representative (Wakil Majikan)

Reference: ITA 1967 Section 83(2) — Fine RM200 to RM20,000 or 6 months imprisonment.
"""
import frappe
from frappe.utils import date_diff, getdate, today

# Effective date of online-only mandate
ONLINE_MANDATE_EFFECTIVE_DATE = "2024-09-01"

# Official online-only mandate alert text (AC-3)
ONLINE_MANDATE_ALERT = (
    "e-CP22 must be submitted by company director or registered Wakil Majikan "
    "via mytax.hasil.gov.my \u2014 system cannot auto-submit"
)

# ITA 1967 S.83(2) penalty notice (AC-6)
PENALTY_NOTICE = (
    "Offence under ITA 1967 S.83(2) \u2014 Fine RM200 to RM20,000 "
    "or 6 months imprisonment or both"
)


def check_employer_rep_setup(company_name):
    """Validate that the Wakil Majikan (Employer Representative) is configured on Company.

    Raises frappe.ValidationError if any required Wakil Majikan fields are missing.
    All three fields (name, MyTax login ID, authorization date) must be set before
    the e-CP22 workflow is accessible.

    Args:
        company_name (str): The Company document name to check.
    """
    company = frappe.get_doc("Company", company_name)
    missing = []

    if not company.get("custom_mytax_employer_rep_name"):
        missing.append("MyTax Employer Representative Name")
    if not company.get("custom_mytax_employer_rep_login_id"):
        missing.append("MyTax Employer Representative Login ID")
    if not company.get("custom_mytax_employer_rep_auth_date"):
        missing.append("MyTax Employer Representative Authorization Date")

    if missing:
        frappe.throw(
            "e-CP22 requires Wakil Majikan (Employer Representative) setup on Company "
            f"'{company_name}'. Please complete: {', '.join(missing)}",
            title="Wakil Majikan Not Configured",
        )


def get_cp22_online_mandate_alert():
    """Return the official e-CP22 online-only mandate alert text (AC-3)."""
    return ONLINE_MANDATE_ALERT


def get_cp22_penalty_notice():
    """Return the ITA 1967 S.83(2) penalty notice text (AC-6)."""
    return PENALTY_NOTICE


def check_onboarding_block(doc, method=None):
    """Block Employee save if CP22 is Pending and 30+ days have elapsed since hire date.

    Enforces AC-5: System blocks new employee onboarding finalization if CP22 status
    is 'Pending' and 30 days have elapsed since hire date.

    Args:
        doc: Employee document being validated.
        method (str, optional): Frappe doc event method name.

    Raises:
        frappe.ValidationError: When CP22 is Pending and deadline has passed.
    """
    if doc.get("custom_cp22_submission_status") != "Pending":
        return

    if not doc.date_of_joining:
        return

    days_elapsed = date_diff(today(), getdate(doc.date_of_joining))
    if days_elapsed >= 30:
        frappe.throw(
            f"Onboarding blocked: e-CP22 for {doc.employee_name} has been Pending for "
            f"{days_elapsed} days (hire date: {doc.date_of_joining}). "
            f"Submit e-CP22 via mytax.hasil.gov.my before updating this record. "
            f"{PENALTY_NOTICE}",
            title="CP22 Submission Overdue — ITA 1967 S.83(2)",
        )


def show_online_mandate_alert(doc, method=None):
    """Display online-only mandate alert and penalty notice on LHDN CP22 validate.

    Enforces AC-1 (digital-only) and AC-3 (mandate alert) by showing a persistent
    blue info message. When the filing deadline is at risk (7 days or fewer remaining),
    also shows the ITA 1967 S.83(2) penalty notice (AC-6).

    Args:
        doc: LHDN CP22 document being validated.
        method (str, optional): Frappe doc event method name.
    """
    frappe.msgprint(
        ONLINE_MANDATE_ALERT,
        title="e-CP22 Online-Only Submission Required",
        indicator="blue",
    )

    # Show penalty notice when deadline is at risk (AC-6)
    if doc.get("filing_deadline") and doc.get("status") == "Pending":
        days_left = date_diff(getdate(doc.filing_deadline), getdate(today()))
        if days_left <= 7:
            frappe.msgprint(
                PENALTY_NOTICE,
                title="Warning: ITA 1967 S.83(2) Penalty Risk",
                indicator="orange",
            )
