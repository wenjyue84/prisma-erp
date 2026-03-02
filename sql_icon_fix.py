import frappe

def run():
    print("Executing raw SQL fix for E-Invoice icon...")
    
    # 1. Force update the Desktop Icon table
    # We use LIKE '%E-Invoice%' to catch 'E-Invoice' label correctly
    query = """
        UPDATE `tabDesktop Icon` 
        SET logo_url = '/assets/myinvois_erpgulf/images/einvoice_logo.svg', 
            icon = '' 
        WHERE label LIKE '%E-Invoice%'
    """
    frappe.db.sql(query)
    
    # 2. Also update Workspace if it exists
    query_ws = """
        UPDATE `tabWorkspace` 
        SET icon = '' 
        WHERE label LIKE '%E-Invoice%' OR name = 'Malaysia Compliance'
    """
    frappe.db.sql(query_ws)
    
    frappe.db.commit()
    frappe.clear_cache()
    print("SQL Update and Cache Clear finished.")
