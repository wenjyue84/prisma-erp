import frappe
frappe.init(site="frontend")
frappe.connect()

# Check if both PDPA tables exist
pdpa_breach_exists = frappe.db.table_exists("PDPA Breach Incident")
print("PDPA Breach Incident table exists:", pdpa_breach_exists)

pdpa_dpo_exists = frappe.db.table_exists("PDPA DPO Registry")
print("PDPA DPO Registry table exists:", pdpa_dpo_exists)

# Check the custom_statutory_hrdf_status column
col_info = frappe.db.sql(
    "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tabCompany' "
    "AND COLUMN_NAME='custom_statutory_hrdf_status'",
    as_dict=1
)
print("custom_statutory_hrdf_status type:", col_info)

# Count Company columns
count = frappe.db.sql(
    "SELECT COUNT(*) as n FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tabCompany'",
    as_dict=1
)
print("tabCompany column count:", count[0]["n"])

frappe.destroy()
