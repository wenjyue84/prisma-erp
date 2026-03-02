import frappe
def run():
    if frappe.db.exists("Desktop Icon", "ESS Mobile"):
        frappe.db.set_value("Desktop Icon", "ESS Mobile", "icon", "")
        frappe.db.set_value("Desktop Icon", "ESS Mobile", "logo_url", "/assets/hrms/images/ess_mobile.svg")
        frappe.db.commit()
        print("Updated ESS Mobile: Cleared 'icon' and set 'logo_url'")
