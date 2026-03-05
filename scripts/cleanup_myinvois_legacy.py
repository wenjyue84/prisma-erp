"""One-shot bench execute script: remove stale 'Myinvois Erpgulf' desk entries.

Usage:
    bench --site frontend execute frappe.cleanup_myinvois_legacy.run
"""

import frappe


def run():
    # Delete stale Workspace Sidebar named "Myinvois Erpgulf"
    for name in frappe.db.get_all("Workspace Sidebar", filters={"name": "Myinvois Erpgulf"}, pluck="name"):
        frappe.delete_doc("Workspace Sidebar", name, ignore_permissions=True, force=True)
        print(f"Deleted Workspace Sidebar: {name}")

    # Delete any Workspace labelled "Myinvois Erpgulf"
    stale = frappe.db.get_all(
        "Workspace",
        filters=[["label", "=", "Myinvois Erpgulf"]],
        pluck="name",
    )
    for name in stale:
        frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)
        print(f"Deleted Workspace: {name}")

    # Delete stale Desktop Icon
    for name in frappe.db.get_all("Desktop Icon", filters={"name": "Myinvois Erpgulf"}, pluck="name"):
        frappe.delete_doc("Desktop Icon", name, ignore_permissions=True, force=True)
        print(f"Deleted Desktop Icon: {name}")

    frappe.db.commit()
    print("Done. Cache clear recommended: bench --site frontend clear-cache")
