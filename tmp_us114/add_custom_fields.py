"""Script to add US-114 custom fields to custom_field.json fixture."""
import json

fixture_path = "/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json"

with open(fixture_path, "r") as f:
    fields = json.load(f)

# New Employee fields for CP22 tracking
new_employee_fields = [
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_cp22_tracking_section",
        "dt": "Employee",
        "fieldname": "custom_cp22_tracking_section",
        "fieldtype": "Section Break",
        "label": "CP22 Submission Tracking",
        "description": "Track CP22 (new employee LHDN notification) submission. Mandatory via e-CP22 on MyTax within 30 days of joining (effective 1 Sep 2024).",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_labour_jurisdiction",
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_cp22_submission_status",
        "dt": "Employee",
        "fieldname": "custom_cp22_submission_status",
        "fieldtype": "Select",
        "label": "CP22 Submission Status",
        "options": "\nPending\nSubmitted\nNot Required",
        "default": "Pending",
        "description": "Pending: e-CP22 not yet filed on MyTax. Submitted: filed by employer representative. Not Required: employee has pre-existing TIN and notification waived.",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_cp22_tracking_section",
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_cp22_submission_date",
        "dt": "Employee",
        "fieldname": "custom_cp22_submission_date",
        "fieldtype": "Date",
        "label": "CP22 Submission Date",
        "description": "Date HR submitted e-CP22 on MyTax portal.",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_cp22_submission_status",
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_cp22_reference_number",
        "dt": "Employee",
        "fieldname": "custom_cp22_reference_number",
        "fieldtype": "Data",
        "label": "CP22 Reference Number",
        "description": "MyTax e-CP22 submission reference number for audit trail.",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_cp22_submission_date",
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_cp22_not_required_reason",
        "dt": "Employee",
        "fieldname": "custom_cp22_not_required_reason",
        "fieldtype": "Small Text",
        "label": "CP22 Not Required Reason",
        "description": "Reason why CP22 is not required (e.g., employee has existing TIN from previous employment).",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_cp22_reference_number",
    },
]

# New Company field: MyTax Employer Representative Name
new_company_fields = [
    {
        "doctype": "Custom Field",
        "name": "Company-custom_mytax_employer_rep_name",
        "dt": "Company",
        "fieldname": "custom_mytax_employer_rep_name",
        "fieldtype": "Data",
        "label": "MyTax Employer Representative Name",
        "description": "Name of the appointed Employer Representative registered on MyTax portal who can submit e-CP22, e-CP39, and other LHDN employer filings on behalf of the company.",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_foreign_employee_count",
    },
]

# Check for existing fieldnames to avoid duplicates
existing_fieldnames = {f.get("fieldname") for f in fields}

added = 0
for field in new_employee_fields + new_company_fields:
    if field["fieldname"] not in existing_fieldnames:
        fields.append(field)
        added += 1
        print(f"Added: {field['fieldname']}")
    else:
        print(f"Skipped (already exists): {field['fieldname']}")

with open(fixture_path, "w") as f:
    json.dump(fields, f, indent=1)

print(f"\nDone. Added {added} new fields. Total: {len(fields)} fields.")
