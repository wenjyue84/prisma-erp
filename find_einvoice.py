import frappe
def run():
    res = frappe.get_all("Desktop Icon", fields=["name", "label", "logo_url", "icon", "app"])
    print(f"ALL_DESKTOP_ICONS: {res}")
