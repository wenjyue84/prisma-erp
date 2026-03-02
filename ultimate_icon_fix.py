import frappe

def run():
    print("--- Starting Deep Icon Fix ---")
    
    new_url = "/assets/myinvois_erpgulf/images/einvoice_logo.svg"
    
    # 1. Update Desktop Icons (Desk icons/App tiles)
    di_list = frappe.get_all("Desktop Icon", filters={"module": "Myinvois Erpgulf"})
    for di in di_list:
        frappe.db.set_value("Desktop Icon", di.name, "logo_url", new_url)
        frappe.db.set_value("Desktop Icon", di.name, "icon", "")
        print(f"Updated Desktop Icon: {di.name}")

    # 2. Update Workspaces (Sidebar/Dashboard)
    ws_list = frappe.get_all("Workspace", filters={"module": "Myinvois Erpgulf"})
    for ws in ws_list:
        frappe.db.set_value("Workspace", ws.name, "icon", "")
        # In some versions, Workspace uses 'image' or specific content JSON
        print(f"Updated Workspace: {ws.name}")

    # 3. Update Module Def
    if frappe.db.exists("Module Def", "Myinvois Erpgulf"):
        # Some versions use an icon field here
        try:
            frappe.db.set_value("Module Def", "Myinvois Erpgulf", "icon", "")
        except:
            pass
        print("Updated Module Def: Myinvois Erpgulf")

    # 4. Clear all caches
    frappe.clear_cache()
    frappe.db.commit()
    print("--- Database Update Complete & Cache Cleared ---")
