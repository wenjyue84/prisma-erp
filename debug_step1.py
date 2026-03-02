import frappe
from frappe.desk.desktop import get_workspace_sidebar_items

def run():
    print("--- Debugging Sidebar Items ---")
    items = get_workspace_sidebar_items()
    for item in items.get('pages', []):
        if 'Invoice' in str(item.get('title')) or 'Malaysia' in str(item.get('title')):
            print(f"SIDEBAR_ITEM: {item}")

    print("\n--- Debugging add_to_apps_screen from hooks ---")
    from frappe.utils.commands import get_apps
    for app in get_apps():
        hooks = frappe.get_hooks(app_name=app)
        if 'add_to_apps_screen' in hooks:
            print(f"APP: {app}, HOOKS: {hooks['add_to_apps_screen']}")
