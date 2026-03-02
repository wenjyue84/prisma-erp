import frappe
def run():
    print("--- Raw Desktop Icon Data ---")
    data = frappe.db.sql("SELECT * FROM `tabDesktop Icon` WHERE label LIKE '%E-Invoice%'", as_dict=True)
    print(f"RAW_DATA: {data}")
