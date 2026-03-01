import frappe
frappe.init(site="frontend")
frappe.connect()

result = frappe.db.sql(
    "SELECT COUNT(*) as col_count FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tabCompany'",
    as_dict=1
)
print("tabCompany column count:", result[0]["col_count"])

# Check row format
fmt = frappe.db.sql(
    "SELECT Row_format, Engine FROM information_schema.TABLES "
    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tabCompany'",
    as_dict=1
)
print("tabCompany format:", fmt)

# Check if PDPA Breach Incident table exists
pdpa_exists = frappe.db.table_exists("PDPA Breach Incident")
print("PDPA Breach Incident table exists:", pdpa_exists)

# Check DPO custom fields
dpo_fields = frappe.db.sql(
    "SELECT name, fieldname FROM tabCustom_Field WHERE dt='Company' AND fieldname LIKE '%dpo%'",
    as_dict=1
)
print("DPO custom fields:", dpo_fields)

frappe.destroy()
