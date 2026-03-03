import frappe


def run():
    # Fix: update 9 child icons to reference "HR" (local parent name) not "Frappe HR"
    frappe.db.sql(
        "UPDATE `tabDesktop Icon` SET parent_icon='HR', modified=NOW() WHERE parent_icon='Frappe HR'"
    )
    frappe.db.commit()
    count = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabDesktop Icon` WHERE parent_icon='HR'"
    )[0][0]
    print(f"Updated child icons → parent_icon='HR'. Now {count} children under HR.")

    # Ensure HR App icon has icon field set
    frappe.db.sql(
        "UPDATE `tabDesktop Icon` SET icon='hr', modified=NOW() WHERE label='HR' AND icon_type='App'"
    )
    frappe.db.commit()
    print("HR App icon confirmed.")
