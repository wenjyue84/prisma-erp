"""
Fix: tabCustom Field record for custom_statutory_hrdf_status says 'Select'
but the actual tabCompany column is 'text'. Frappe tries to MODIFY text→varchar(140)
which fails due to Company table row size limit.

Fix: update the tabCustom Field record to 'Small Text' so Frappe sees
column already matches and skips the ALTER TABLE.
"""
import frappe
frappe.init(site="frontend")
frappe.connect()

# Update the Custom Field record to match the actual DB column type
frappe.db.sql(
    "UPDATE `tabCustom Field` SET fieldtype='Small Text' "
    "WHERE name='Company-custom_statutory_hrdf_status'"
)
frappe.db.commit()

# Verify
result = frappe.db.sql(
    "SELECT name, fieldtype FROM `tabCustom Field` "
    "WHERE name='Company-custom_statutory_hrdf_status'",
    as_dict=1
)
print("Fixed:", result)

frappe.destroy()
