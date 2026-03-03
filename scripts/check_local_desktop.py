import frappe

def run():
    rows = frappe.db.sql("""
        SELECT label, icon_type, link_to, parent_icon, app, icon, bg_color, idx, hidden
        FROM `tabDesktop Icon`
        WHERE parent_icon='HR' OR parent_icon='Frappe HR' OR label='HR' OR label='Frappe HR' OR app='hrms'
        ORDER BY idx, label
    """, as_dict=True)
    print("HR/HRMS Desktop Icons on localhost:")
    for r in rows:
        print(f"  label={r['label']} | type={r['icon_type']} | link_to={r['link_to']} | parent={r['parent_icon']} | icon={r['icon']} | bg={r['bg_color']}")

    if not rows:
        print("  (none found)")

    # Also show all desktop icons briefly
    all_rows = frappe.db.sql("SELECT label, icon_type, parent_icon FROM `tabDesktop Icon` ORDER BY label LIMIT 30", as_dict=True)
    print("\nAll Desktop Icons (sample):")
    for r in all_rows:
        print(f"  {r['label']} | {r['icon_type']} | parent={r['parent_icon']}")
