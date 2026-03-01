"""Add DPO custom fields to Company in custom_field.json fixture."""
import json

NEW_FIELDS = [
    {
        "doctype": "Custom Field",
        "name": "Company-custom_pdpa_tab",
        "dt": "Company",
        "fieldname": "custom_pdpa_tab",
        "fieldtype": "Tab Break",
        "label": "PDPA Compliance",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_statutory_hrdf_status"
    },
    {
        "doctype": "Custom Field",
        "name": "Company-custom_pdpa_section",
        "dt": "Company",
        "fieldname": "custom_pdpa_section",
        "fieldtype": "Section Break",
        "label": "Data Protection Officer (DPO)",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_pdpa_tab",
        "description": "Mandatory for employers processing large-scale employee payroll data under PDPA Amendment Act 2024."
    },
    {
        "doctype": "Custom Field",
        "name": "Company-custom_dpo_name",
        "dt": "Company",
        "fieldname": "custom_dpo_name",
        "fieldtype": "Data",
        "label": "DPO Name",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_pdpa_section"
    },
    {
        "doctype": "Custom Field",
        "name": "Company-custom_dpo_email",
        "dt": "Company",
        "fieldname": "custom_dpo_email",
        "fieldtype": "Data",
        "label": "DPO Email",
        "options": "Email",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_dpo_name"
    },
    {
        "doctype": "Custom Field",
        "name": "Company-custom_dpo_phone",
        "dt": "Company",
        "fieldname": "custom_dpo_phone",
        "fieldtype": "Data",
        "label": "DPO Phone",
        "options": "Phone",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_dpo_email"
    },
    {
        "doctype": "Custom Field",
        "name": "Company-custom_dpo_appointment_date",
        "dt": "Company",
        "fieldname": "custom_dpo_appointment_date",
        "fieldtype": "Date",
        "label": "DPO Appointment Date",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_dpo_phone",
        "description": "Date the DPO was formally appointed. Commissioner must be notified within 21 days."
    },
    {
        "doctype": "Custom Field",
        "name": "Company-custom_dpo_commissioner_registration_date",
        "dt": "Company",
        "fieldname": "custom_dpo_commissioner_registration_date",
        "fieldtype": "Date",
        "label": "DPO Commissioner Registration Date",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_dpo_appointment_date",
        "description": "Date when the DPO appointment was registered/notified to the PDPA Commissioner (must be within 21 days of appointment)."
    }
]

with open("/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json") as f:
    existing = json.load(f)

# Remove any existing DPO fields (idempotent)
existing_names = {x["name"] for x in NEW_FIELDS}
existing = [f for f in existing if f.get("name") not in existing_names]

# Append new fields
existing.extend(NEW_FIELDS)

with open("/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json", "w") as f:
    json.dump(existing, f, indent=2)

print(f"custom_field.json updated: now {len(existing)} entries")
print(f"Added {len(NEW_FIELDS)} DPO fields for Company doctype")
