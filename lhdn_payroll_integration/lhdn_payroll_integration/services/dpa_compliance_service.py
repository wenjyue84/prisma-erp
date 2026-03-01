"""PDPA 2024 Data Processor Agreement Compliance Service (US-208).

Manages the Data Processor Registry, DPA expiry alerts, export audit
logging with downstream-processor tracking, and compliance checklist
reporting for external payroll service vendors.

Key rules (PDPA Amendment 2024, effective 1 June 2025):
- Data processors have direct liability for security principle breaches
  (fine up to RM1,000,000 or 3 years imprisonment)
- Every external processor handling payroll data must have a signed DPA
- DPA must specify: purpose, data categories, retention, security measures
- Typical processors: HRD Corp agents, LHDN e-PCB bureaus, bank payroll,
  EPF/SOCSO e-filing vendors
"""

import frappe
from frappe.utils import getdate, today, date_diff, now_datetime


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Days before DPA expiry to trigger an alert
DPA_EXPIRY_WARNING_DAYS = 30

#: Sensitive employee data categories tracked for export audit
SENSITIVE_DATA_CATEGORIES = [
    "Salary",
    "IC Number",
    "TIN",
    "Bank Account",
    "EPF Number",
    "SOCSO Number",
    "EIS Number",
]

#: Required DPA contract fields per PDPA 2024
REQUIRED_DPA_FIELDS = [
    "processor_name",
    "services_provided",
    "dpa_signed_date",
    "dpa_expiry_date",
]

#: Maximum penalty for processor security breach (MYR)
MAX_PENALTY_MYR = 1_000_000

#: Effective date of data processor direct obligations
EFFECTIVE_DATE = "2025-06-01"


# ---------------------------------------------------------------------------
# Data Processor Registry helpers
# ---------------------------------------------------------------------------

def validate_processor_record(record):
    """Validate a data processor registry entry.

    Args:
        record: dict with processor_name, services_provided,
                dpa_signed_date, dpa_expiry_date, etc.

    Returns:
        dict with ``valid`` (bool) and ``errors`` (list of str).
    """
    errors = []
    if not record:
        return {"valid": False, "errors": ["Record is empty"]}

    for field in REQUIRED_DPA_FIELDS:
        val = record.get(field)
        if not val or (isinstance(val, str) and not val.strip()):
            errors.append(f"Missing required field: {field}")

    signed = record.get("dpa_signed_date")
    expiry = record.get("dpa_expiry_date")
    if signed and expiry:
        try:
            if getdate(expiry) <= getdate(signed):
                errors.append("dpa_expiry_date must be after dpa_signed_date")
        except Exception:
            errors.append("Invalid date format in signed/expiry dates")

    return {"valid": len(errors) == 0, "errors": errors}


def get_dpa_status(expiry_date, reference_date=None):
    """Classify a DPA's status based on its expiry date.

    Returns one of: ``"active"``, ``"expiring_soon"``, ``"expired"``.
    """
    ref = getdate(reference_date) if reference_date else getdate(today())
    exp = getdate(expiry_date)
    days_remaining = date_diff(exp, ref)

    if days_remaining < 0:
        return "expired"
    elif days_remaining <= DPA_EXPIRY_WARNING_DAYS:
        return "expiring_soon"
    else:
        return "active"


def get_days_until_dpa_expiry(expiry_date, reference_date=None):
    """Return the number of days until a DPA expires (negative if expired)."""
    ref = getdate(reference_date) if reference_date else getdate(today())
    exp = getdate(expiry_date)
    return date_diff(exp, ref)


def is_dpa_expired(expiry_date, reference_date=None):
    """Return True if the DPA has expired."""
    return get_days_until_dpa_expiry(expiry_date, reference_date) < 0


def is_dpa_expiring_soon(expiry_date, reference_date=None):
    """Return True if the DPA expires within DPA_EXPIRY_WARNING_DAYS."""
    days = get_days_until_dpa_expiry(expiry_date, reference_date)
    return 0 <= days <= DPA_EXPIRY_WARNING_DAYS


# ---------------------------------------------------------------------------
# DPA Expiry Alert generation
# ---------------------------------------------------------------------------

def get_processors_needing_alerts(company, reference_date=None):
    """Return processors with DPAs that are expired or expiring within 30 days.

    Args:
        company: Company name to filter processors.
        reference_date: Override for today (testing).

    Returns:
        dict with ``expiring_soon`` and ``expired`` lists.
    """
    ref = getdate(reference_date) if reference_date else getdate(today())

    processors = frappe.get_all(
        "Data Processor Registry",
        filters={"company": company},
        fields=[
            "name", "processor_name", "services_provided",
            "dpa_signed_date", "dpa_expiry_date",
            "last_security_audit_date",
        ],
    )

    expiring_soon = []
    expired = []

    for p in processors:
        if not p.get("dpa_expiry_date"):
            expired.append({**dict(p), "days_remaining": None, "status": "no_expiry_date"})
            continue

        days = date_diff(getdate(p["dpa_expiry_date"]), ref)

        if days < 0:
            expired.append({**dict(p), "days_remaining": days, "status": "expired"})
        elif days <= DPA_EXPIRY_WARNING_DAYS:
            expiring_soon.append({**dict(p), "days_remaining": days, "status": "expiring_soon"})

    return {
        "company": company,
        "reference_date": str(ref),
        "expiring_soon": expiring_soon,
        "expired": expired,
        "total_alerts": len(expiring_soon) + len(expired),
    }


# ---------------------------------------------------------------------------
# Export Audit Logging
# ---------------------------------------------------------------------------

def log_data_export(user, data_categories, downstream_processor,
                    employee=None, document_type=None, document_name=None):
    """Create an audit log entry when employee personal data is exported.

    Args:
        user: The user performing the export.
        data_categories: List of data categories exported (e.g. ["Salary", "TIN"]).
        downstream_processor: Name of the receiving data processor.
        employee: Optional employee ID whose data was exported.
        document_type: Optional source document type.
        document_name: Optional source document name.

    Returns:
        dict with the log entry details.
    """
    if not data_categories:
        data_categories = []

    categories_str = ", ".join(data_categories) if isinstance(data_categories, list) else str(data_categories)

    log_entry = {
        "user": user,
        "data_categories": categories_str,
        "downstream_processor": downstream_processor,
        "employee": employee,
        "document_type": document_type,
        "document_name": document_name,
        "timestamp": str(now_datetime()),
    }

    try:
        doc = frappe.get_doc({
            "doctype": "PDPA Export Audit Log",
            **log_entry,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log_entry["name"] = doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PDPA Export Audit Log Failed")

    return log_entry


# ---------------------------------------------------------------------------
# Compliance Checklist Report
# ---------------------------------------------------------------------------

def generate_compliance_checklist(company):
    """Generate a compliance checklist for all registered data processors.

    Returns per-processor:
    - dpa_on_file (Yes/No)
    - dpa_current (Yes/No) — signed and not expired
    - dpo_notified (Yes/No) — DPO has been notified of this processor

    Args:
        company: Company name.

    Returns:
        dict with ``processors`` list and ``summary`` counts.
    """
    processors = frappe.get_all(
        "Data Processor Registry",
        filters={"company": company},
        fields=[
            "name", "processor_name", "services_provided",
            "dpa_signed_date", "dpa_expiry_date",
            "dpa_document_attachment", "dpo_notified",
            "last_security_audit_date",
        ],
    )

    checklist = []
    compliant_count = 0

    for p in processors:
        has_dpa = bool(p.get("dpa_document_attachment"))
        dpa_current = False
        if p.get("dpa_signed_date") and p.get("dpa_expiry_date"):
            dpa_current = not is_dpa_expired(p["dpa_expiry_date"])
        dpo_notified = bool(p.get("dpo_notified"))

        is_compliant = has_dpa and dpa_current and dpo_notified
        if is_compliant:
            compliant_count += 1

        checklist.append({
            "processor_name": p.get("processor_name"),
            "services_provided": p.get("services_provided"),
            "dpa_on_file": "Yes" if has_dpa else "No",
            "dpa_current": "Yes" if dpa_current else "No",
            "dpo_notified": "Yes" if dpo_notified else "No",
            "compliant": is_compliant,
            "last_security_audit_date": str(p.get("last_security_audit_date") or ""),
        })

    total = len(checklist)
    return {
        "company": company,
        "processors": checklist,
        "summary": {
            "total_processors": total,
            "compliant": compliant_count,
            "non_compliant": total - compliant_count,
            "compliance_rate": round(compliant_count / total * 100, 1) if total else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Bulk Export DPA Gate
# ---------------------------------------------------------------------------

def check_active_dpa_for_processor(company, processor_name):
    """Check if there is an active (non-expired) DPA for a given processor.

    Args:
        company: Company name.
        processor_name: Name of the downstream processor.

    Returns:
        dict with ``has_active_dpa`` (bool), ``processor_name``,
        and optional ``dpa_expiry_date``.
    """
    processors = frappe.get_all(
        "Data Processor Registry",
        filters={"company": company, "processor_name": processor_name},
        fields=["name", "dpa_expiry_date", "dpa_signed_date"],
    )

    if not processors:
        return {
            "has_active_dpa": False,
            "processor_name": processor_name,
            "reason": "No processor record found",
        }

    for p in processors:
        if p.get("dpa_expiry_date") and not is_dpa_expired(p["dpa_expiry_date"]):
            return {
                "has_active_dpa": True,
                "processor_name": processor_name,
                "dpa_expiry_date": str(p["dpa_expiry_date"]),
            }

    return {
        "has_active_dpa": False,
        "processor_name": processor_name,
        "reason": "All DPAs have expired",
    }


def warn_if_no_active_dpa(company, processor_name):
    """Return a warning message if no active DPA exists for the processor.

    Returns None if DPA is active, otherwise returns a warning string.
    """
    result = check_active_dpa_for_processor(company, processor_name)
    if result["has_active_dpa"]:
        return None
    return (
        f"WARNING: No active Data Processing Agreement on file for "
        f"processor '{processor_name}' under company '{company}'. "
        f"Reason: {result.get('reason', 'Unknown')}. "
        f"PDPA 2024 requires a valid DPA before sharing payroll data."
    )


def get_all_processors_summary(company):
    """Return a summary of all data processors for a company.

    Returns:
        dict with counts by status (active, expiring_soon, expired, no_dpa).
    """
    processors = frappe.get_all(
        "Data Processor Registry",
        filters={"company": company},
        fields=["name", "processor_name", "dpa_expiry_date"],
    )

    summary = {"active": 0, "expiring_soon": 0, "expired": 0, "no_dpa": 0}

    for p in processors:
        if not p.get("dpa_expiry_date"):
            summary["no_dpa"] += 1
        else:
            status = get_dpa_status(p["dpa_expiry_date"])
            if status in summary:
                summary[status] += 1

    summary["total"] = len(processors)
    return summary
