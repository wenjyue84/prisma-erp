import frappe
frappe.init(site="frontend")
frappe.connect()
result = frappe.db.sql("SHOW TABLE STATUS LIKE 'tabCompany'", as_dict=1)
if result:
    print("Current row format:", result[0].get("Row_format"))
frappe.db.sql("ALTER TABLE tabCompany ROW_FORMAT=DYNAMIC")
print("ROW_FORMAT changed to DYNAMIC")
result2 = frappe.db.sql("SHOW TABLE STATUS LIKE 'tabCompany'", as_dict=1)
if result2:
    print("New row format:", result2[0].get("Row_format"))
frappe.db.commit()
frappe.destroy()
