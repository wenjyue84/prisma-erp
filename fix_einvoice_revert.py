import frappe
def run():
    # Update Desktop Icon for Malaysia Compliance (E-Invoice)
    if frappe.db.exists("Desktop Icon", "Malaysia Compliance"):
        # Clear 'icon' to force 'logo_url' usage
        frappe.db.set_value("Desktop Icon", "Malaysia Compliance", "icon", "")
        frappe.db.set_value("Desktop Icon", "Malaysia Compliance", "logo_url", "/assets/myinvois_erpgulf/images/einvoice_logo.svg")
        frappe.db.commit()
        print("Fixed E-Invoice: Cleared 'icon' and set 'logo_url' to blue SVG")
    else:
        print("Desktop Icon 'Malaysia Compliance' not found")
