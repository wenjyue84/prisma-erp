"""Set up RBAC for LHDN custom fields.

Sets permlevel=1 on sensitive LHDN response fields and adds
DocPerm entries for HR Manager at permlevel=1.

Usage:
    bench --site frontend execute lhdn_payroll_integration.setup_rbac.run
"""

import frappe


def run():
    """Configure RBAC for LHDN custom fields."""

    # 1. Set permlevel=1 on custom_lhdn_uuid (Salary Slip)
    _set_custom_field_permlevel("Salary Slip", "custom_lhdn_uuid", 1)

    # 2. Set permlevel=1 on custom_requires_self_billed_invoice (Employee)
    _set_custom_field_permlevel("Employee", "custom_requires_self_billed_invoice", 1)

    # 3. Add DocPerm for HR Manager at permlevel=1 on Salary Slip
    _ensure_docperm("Salary Slip", "HR Manager", permlevel=1, read=1, write=1)

    # 4. Add DocPerm for System Manager at permlevel=1 on Salary Slip
    _ensure_docperm("Salary Slip", "System Manager", permlevel=1, read=1, write=1)

    # 5. Add DocPerm for HR Manager at permlevel=1 on Employee
    _ensure_docperm("Employee", "HR Manager", permlevel=1, read=1, write=1)

    # 6. Add DocPerm for System Manager at permlevel=1 on Employee
    _ensure_docperm("Employee", "System Manager", permlevel=1, read=1, write=1)

    frappe.db.commit()
    frappe.clear_cache()
    print("RBAC configuration complete.")


def _set_custom_field_permlevel(doctype, fieldname, permlevel):
    """Set permlevel on a Custom Field."""
    exists = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
    if exists:
        frappe.db.set_value("Custom Field", exists, "permlevel", permlevel)
        print(f"  Set {doctype}.{fieldname} permlevel={permlevel}")
    else:
        print(f"  WARNING: Custom Field {doctype}.{fieldname} not found")


def _ensure_docperm(doctype, role, permlevel=0, read=0, write=0):
    """Ensure a DocPerm entry exists for the given role and permlevel."""
    existing = frappe.get_all(
        "DocPerm",
        filters={
            "parent": doctype,
            "role": role,
            "permlevel": permlevel,
        },
        fields=["name"],
    )

    if existing:
        # Update existing entry
        frappe.db.set_value("DocPerm", existing[0].name, {
            "read": read,
            "write": write,
        })
        print(f"  Updated DocPerm: {doctype} / {role} / permlevel={permlevel}")
    else:
        # Create new DocPerm entry directly via SQL insert
        # Using frappe.get_doc("DocType", doctype) can trigger validation issues
        max_idx = frappe.db.sql(
            "SELECT MAX(idx) FROM `tabDocPerm` WHERE parent=%s",
            doctype
        )[0][0] or 0

        frappe.get_doc({
            "doctype": "DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role,
            "permlevel": permlevel,
            "read": read,
            "write": write,
            "idx": max_idx + 1,
        }).db_insert()
        print(f"  Created DocPerm: {doctype} / {role} / permlevel={permlevel}")
