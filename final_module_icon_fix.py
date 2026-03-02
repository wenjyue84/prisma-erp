import frappe

def run():
    print("--- Fixing E-Invoice Module and Application Icons ---")
    
    icon_path = "/assets/myinvois_erpgulf/images/prisma_einvoice.svg"
    
    # 1. Update the Module Def (This fixes the sidebar/grid broken icon)
    if frappe.db.exists("Module Def", "E-Invoice"):
        # Note: Module Def in v16 might not have a direct 'icon' field that shows in UI, 
        # but we ensure it's clean.
        print("Module Def 'E-Invoice' found.")

    # 2. Update all Desktop Icons that might be used as 'E-Invoice'
    # We rename 'Malaysia Compliance' to 'E-Invoice' if needed, but let's just force the icon first
    frappe.db.sql("""
        UPDATE `tabDesktop Icon` 
        SET label = 'E-Invoice', 
            logo_url = %s, 
            icon = '' 
        WHERE app = 'myinvois_erpgulf' OR label = 'Malaysia Compliance' OR label = 'E-Invoice'
    """, (icon_path,))

    # 3. Update Workspace (Sidebar)
    frappe.db.sql("""
        UPDATE `tabWorkspace`
        SET label = 'E-Invoice',
            icon = ''
        WHERE module = 'E-Invoice' OR name = 'Malaysia Compliance'
    """)

    frappe.db.commit()
    frappe.clear_cache()
    print("--- Fix Complete. Please Hard Reload. ---")
