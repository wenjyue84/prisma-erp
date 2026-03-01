import frappe
frappe.init(site="frontend")
frappe.connect()

# Check the custom field record in the DB
result = frappe.db.sql(
    "SELECT name, fieldname, fieldtype, label FROM `tabCustom Field` "
    "WHERE name='Company-custom_statutory_hrdf_status'",
    as_dict=1
)
print("Custom Field DB record:", result)

# Check what other Company custom fields are near it that might be causing issues
company_selects = frappe.db.sql(
    "SELECT fieldname, fieldtype, LENGTH(options) as opt_len FROM `tabCustom Field` "
    "WHERE dt='Company' AND fieldtype IN ('Select', 'Data') "
    "ORDER BY opt_len DESC LIMIT 10",
    as_dict=1
)
print("Company Select/Data fields by option length:", company_selects)

frappe.destroy()
