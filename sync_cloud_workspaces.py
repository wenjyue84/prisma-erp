"""
sync_cloud_workspaces.py — Fix module names and create missing workspaces
to match the cloud (prismaerp.click).

Usage (2 steps — separate invocations to refresh module cache):

    Step 1: Fix module name
    bench --site frontend execute frappe.sync_cloud_workspaces.fix_module

    Step 2: Create workspaces (run AFTER step 1)
    bench --site frontend execute frappe.sync_cloud_workspaces.create_workspaces

    Or run both in one go:
    bench --site frontend execute frappe.sync_cloud_workspaces.run

Safe to re-run.
"""

import frappe


def fix_module():
    """Rename Module Def 'E-Invoice' → 'Myinvois Erpgulf' if needed."""
    if frappe.db.exists("Module Def", "E-Invoice") and not frappe.db.exists(
        "Module Def", "Myinvois Erpgulf"
    ):
        print("Renaming Module Def: E-Invoice → Myinvois Erpgulf ...")

        # Tables with a 'module' column that might reference the old name
        tables = [
            "`tabCustom Field`",
            "`tabDocType`",
            "`tabReport`",
            "`tabPage`",
            "`tabProperty Setter`",
            "`tabPrint Format`",
            "`tabWorkspace`",
            "`tabWorkspace Link`",
            "`tabWorkspace Shortcut`",
            "`tabWorkspace Sidebar`",
            "`tabWorkspace Sidebar Item`",
            "`tabDesktop Icon`",
            "`tabNumber Card`",
            "`tabDashboard Chart`",
        ]
        for t in tables:
            try:
                cnt = frappe.db.sql(
                    f"SELECT COUNT(*) FROM {t} WHERE module = 'E-Invoice'"
                )[0][0]
                if cnt:
                    frappe.db.sql(
                        f"UPDATE {t} SET module = 'Myinvois Erpgulf' WHERE module = 'E-Invoice'"
                    )
                    print(f"  {t}: {cnt} rows updated")
            except Exception as e:
                pass  # table might not exist or have no module column

        # Rename the primary key
        frappe.db.sql(
            "UPDATE `tabModule Def` SET name = 'Myinvois Erpgulf' WHERE name = 'E-Invoice'"
        )
        frappe.db.sql(
            "UPDATE `tabModule Def` SET app_name = 'myinvois_erpgulf' WHERE name = 'Myinvois Erpgulf'"
        )
        frappe.db.commit()
        print("DONE: Module Def renamed. Run create_workspaces next.")
    elif frappe.db.exists("Module Def", "Myinvois Erpgulf"):
        print("Module Def 'Myinvois Erpgulf' already correct.")
    else:
        print("WARNING: No E-Invoice or Myinvois Erpgulf Module Def found!")


def create_workspaces():
    """Create missing workspaces to match prismaerp.click."""
    created = []

    # 1. Malaysia Compliance (E-Invoice)
    if not frappe.db.exists("Workspace", "Malaysia Compliance"):
        print("Creating: Malaysia Compliance ...")
        doc = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": "Malaysia Compliance",
                "title": "Malaysia Compliance",
                "module": "Myinvois Erpgulf",
                "type": "Workspace",
                "public": 1,
                "is_hidden": 0,
                "icon": "",
                "content": "[]",
                "shortcuts": [
                    {
                        "color": "Grey",
                        "doc_view": "List",
                        "label": "LHDN Detailed Dashboard",
                        "link_to": "lhdn-dashboard",
                        "type": "Page",
                    }
                ],
                "links": [
                    {"type": "Card Break", "label": "LHDN setup", "link_count": 2},
                    {"type": "Link", "label": "LHDN Setup for Company", "link_to": "Company", "link_type": "DocType"},
                    {"type": "Link", "label": "Item Tax Templates", "link_to": "Item Tax Template", "link_type": "DocType"},
                    {"type": "Card Break", "label": "VAT Report", "link_count": 1},
                    {"type": "Link", "label": "LHDN VAT Report on Sales & Purchase", "link_to": "LHDN VAT Report on Sales & Purchase", "link_type": "Report", "is_query_report": 1},
                    {"type": "Card Break", "label": "LHDN Status Reports", "link_count": 2},
                    {"type": "Link", "label": "LHDN Sales Status Report", "link_to": "LHDN Sales Status Report", "link_type": "Report", "is_query_report": 1},
                    {"type": "Link", "label": "LHDN Purchase Status Report", "link_to": "LHDN Purchase Status Report", "link_type": "Report", "is_query_report": 1},
                ],
                "quick_lists": [
                    {"document_type": "Sales Invoice", "label": "New Sales Invoices", "quick_list_filter": '[[\"Sales Invoice\",\"custom_lhdn_status\",\"like\",\"%Valid%\",false]]'},
                    {"document_type": "Purchase Invoice", "label": "New Purchase Invoices", "quick_list_filter": '[[\"Purchase Invoice\",\"custom_lhdn_status\",\"like\",\"%Valid%\",false]]'},
                ],
                "charts": [],
                "number_cards": [],
            }
        )
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_if_duplicate=True)
        # Set label to E-Invoice after insert (name stays "Malaysia Compliance")
        frappe.db.set_value("Workspace", "Malaysia Compliance", "label", "E-Invoice")
        created.append("Malaysia Compliance (label=E-Invoice)")
    else:
        cur = frappe.db.get_value("Workspace", "Malaysia Compliance", "label")
        if cur != "E-Invoice":
            frappe.db.set_value("Workspace", "Malaysia Compliance", "label", "E-Invoice")
            created.append(f"Malaysia Compliance label: {cur} → E-Invoice")
        else:
            print("Malaysia Compliance OK")

    # 2. HR
    if not frappe.db.exists("Workspace", "HR"):
        print("Creating: HR ...")
        doc = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": "HR",
                "title": "HR",
                "module": "HR",
                "type": "Workspace",
                "public": 1,
                "is_hidden": 0,
                "icon": "employee",
                "content": "[]",
                "shortcuts": [],
                "links": [],
                "charts": [],
                "number_cards": [],
            }
        )
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.insert(ignore_if_duplicate=True)
        created.append("HR")
    else:
        print("HR OK")

    frappe.db.commit()
    frappe.clear_cache()

    if created:
        for c in created:
            print(f"  CREATED: {c}")
    else:
        print("All workspaces already match cloud.")


def run():
    """Run both steps. Note: module cache may be stale within same process."""
    fix_module()
    # Force module_app cache rebuild
    if hasattr(frappe.local, "module_app"):
        delattr(frappe.local, "module_app")
    create_workspaces()
