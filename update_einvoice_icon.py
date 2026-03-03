import frappe

def run():
    icon_path = "/assets/myinvois_erpgulf/images/prisma_einvoice.svg"

    # Find the Desktop Icon by name OR label — handles both local and EC2 state
    icon_name = None
    for search_val, field in [
        ("Malaysia Compliance", "name"),
        ("E-Invoice", "label"),
        ("Malaysia Compliance", "label"),
    ]:
        result = frappe.db.get_value("Desktop Icon", {field: search_val}, "name")
        if result:
            icon_name = result
            break

    if icon_name:
        frappe.db.set_value("Desktop Icon", icon_name, {
            "label": "E-Invoice",
            "logo_url": icon_path,
            "icon": "",
            "app": "myinvois_erpgulf",
        })
        print(f"Updated Desktop Icon '{icon_name}' → label='E-Invoice', logo_url={icon_path}")
    else:
        print("Desktop Icon for E-Invoice not found — skipping")

    frappe.db.commit()
    frappe.clear_cache()
    print("Done.")
