import frappe
from frappe.utils import today

def run():
    frappe.set_user("Administrator")
    company_name = "Arising Packaging"
    
    # ── 1. ITEM GROUPS ──────────────────────────────────────────────────
    groups = ["Carton Boxes", "Packaging Tape", "Pallets"]
    for g in groups:
        if not frappe.db.exists("Item Group", g):
            frappe.get_doc({
                "doctype": "Item Group",
                "item_group_name": g,
                "parent_item_group": "All Item Groups",
                "is_group": 0
            }).insert(ignore_permissions=True)
            print(f"Created Item Group {g}")

    # ── 2. WAREHOUSES ───────────────────────────────────────────────────
    # Find a valid warehouse type (fallback)
    wh_type = frappe.db.get_value("Warehouse Type", {"name": "Warehouse"}, "name")
    if not wh_type:
        wh_type = frappe.db.get_value("Warehouse Type", {}, "name")

    warehouses = ["Main Warehouse", "Finished Goods", "Raw Materials"]
    for wh in warehouses:
        wh_name = f"{wh} - AP"
        if not frappe.db.exists("Warehouse", wh_name):
            doc = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": wh,
                "company": company_name,
                "parent_warehouse": f"All Warehouses - AP" if frappe.db.exists("Warehouse", "All Warehouses - AP") else None
            })
            if wh_type:
                doc.warehouse_type = wh_type
            doc.insert(ignore_permissions=True)
            print(f"Created Warehouse {wh_name}")

    # ── 3. ITEMS ────────────────────────────────────────────────────────
    items = [
        {"item_code": "BOX-L-001", "item_name": "Large Box Heavy Duty", "item_group": "Carton Boxes", "stock_uom": "Nos"},
        {"item_code": "BOX-S-001", "item_name": "Small Box Regular", "item_group": "Carton Boxes", "stock_uom": "Nos"},
        {"item_code": "TAPE-001", "item_name": "Packaging Tape (Clear)", "item_group": "Packaging Tape", "stock_uom": "Roll"}
    ]
    for it in items:
        if not frappe.db.exists("Item", it["item_code"]):
            doc = frappe.get_doc({
                "doctype": "Item",
                **it,
                "is_stock_item": 1,
                "is_sales_item": 1,
                "is_purchase_item": 1
            })
            doc.insert(ignore_permissions=True)
            print(f"Created Item {it['item_code']}")

    # ── 4. STOCK ENTRY (Initial Stock) ──────────────────────────────────
    if not frappe.db.exists("Stock Entry Detail", {"item_code": "BOX-L-001", "docstatus": 1}):
        target_wh = f"Main Warehouse - AP" if frappe.db.exists("Warehouse", "Main Warehouse - AP") else None
        if not target_wh:
             target_wh = frappe.db.get_value("Warehouse", {"company": company_name, "is_group": 0}, "name")

        if target_wh:
            se = frappe.get_doc({
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": company_name,
                "posting_date": today(),
                "items": [
                    {"item_code": "BOX-L-001", "qty": 500, "t_warehouse": target_wh, "basic_rate": 4.5},
                    {"item_code": "BOX-S-001", "qty": 800, "t_warehouse": target_wh, "basic_rate": 2.5},
                    {"item_code": "TAPE-001", "qty": 100, "t_warehouse": target_wh, "basic_rate": 6.0}
                ]
            })
            se.insert(ignore_permissions=True)
            se.submit()
            print(f"Stock Entry {se.name} submitted")

    frappe.db.commit()

if __name__ == "__main__":
    run()
