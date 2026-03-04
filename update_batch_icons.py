import frappe
def run():
    updates = {
        "ESS Mobile": "/assets/hrms/images/ess_mobile.svg",
        "Framework": "/assets/frappe/images/framework.svg",
        "Home": "/assets/erpnext/images/home.svg",
        "LHDN Payroll": "/assets/lhdn_payroll_integration/images/lhdn_payroll.svg",
        "ERP Settings": "/assets/erpnext/images/erp_settings.svg",
        "HR": "/assets/hrms/images/hr.svg"
    }
    
    for label, url in updates.items():
        if frappe.db.exists("Desktop Icon", {"label": label}):
            frappe.db.set_value("Desktop Icon", {"label": label}, "logo_url", url)
            print(f"Updated {label} logo_url to {url}")
        else:
            print(f"Desktop Icon {label} not found")
    
    frappe.db.commit()
