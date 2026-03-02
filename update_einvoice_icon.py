import frappe
def run():
    # Update Desktop Icon
    if frappe.db.exists("Desktop Icon", "Malaysia Compliance"):
        frappe.db.set_value("Desktop Icon", "Malaysia Compliance", "logo_url", "/assets/myinvois_erpgulf/images/einvoice_logo.svg")
        frappe.db.commit()
        print("Updated Desktop Icon logo_url in DB")
    
    # Update Hooks (since we can't edit files directly, we'll inform that we did it)
    print("Please also check if app title or hooks need manual update for persistence")
