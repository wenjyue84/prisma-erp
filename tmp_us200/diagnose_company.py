"""
Diagnose which Company custom fields will cause ALTER TABLE errors
and fix them by ensuring the tabCustom Field record matches the actual DB column type.
"""
import frappe
frappe.init(site="frontend")
frappe.connect()

# Get all Company custom fields from tabCustom Field
cf_records = frappe.db.sql(
    "SELECT name, fieldname, fieldtype FROM `tabCustom Field` WHERE dt='Company'",
    as_dict=1
)
cf_map = {r["fieldname"]: r["fieldtype"] for r in cf_records}

# Get actual DB column types for tabCompany
col_types = frappe.db.sql(
    "SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='tabCompany' "
    "AND COLUMN_NAME LIKE 'custom_%'",
    as_dict=1
)
col_map = {r["COLUMN_NAME"]: r["COLUMN_TYPE"] for r in col_types}

# Find mismatches that would cause ALTER TABLE errors
print("=== Company Custom Field Type Mismatches ===")
for fieldname, fieldtype in cf_map.items():
    db_col_type = col_map.get(fieldname, "NOT IN DB")

    # Determine expected DB type from fieldtype
    if fieldtype in ("Data", "Select", "Password", "Read Only"):
        expected_db = "varchar"  # will try ALTER to varchar(140)
    elif fieldtype in ("Small Text", "Text", "Long Text", "Code"):
        expected_db = "text"
    elif fieldtype in ("Int", "Check"):
        expected_db = "int"
    elif fieldtype == "Float":
        expected_db = "decimal"
    elif fieldtype in ("Date",):
        expected_db = "date"
    elif fieldtype in ("Datetime",):
        expected_db = "datetime"
    else:
        expected_db = "unknown"

    # Check for mismatch that would cause ALTER error
    actual_is_text = "text" in str(db_col_type).lower()
    will_try_varchar_alter = expected_db == "varchar" and actual_is_text

    if will_try_varchar_alter:
        print(f"  MISMATCH: {fieldname}")
        print(f"    tabCustom Field says: {fieldtype} (→ varchar alter)")
        print(f"    tabCompany column is: {db_col_type}")
        print(f"    FIX: change tabCustom Field to 'Small Text'")

print("\n=== Fix: Set all conflicting Company fields to Small Text ===")
fixed = []
for fieldname, fieldtype in cf_map.items():
    db_col_type = col_map.get(fieldname, "")
    actual_is_text = "text" in str(db_col_type).lower()
    if fieldtype in ("Data", "Select") and actual_is_text:
        frappe.db.sql(
            f"UPDATE `tabCustom Field` SET fieldtype='Small Text' "
            f"WHERE dt='Company' AND fieldname='{fieldname}'"
        )
        fixed.append(fieldname)
        print(f"  Fixed: {fieldname} ({fieldtype} → Small Text)")

frappe.db.commit()
print(f"\nTotal fixed: {len(fixed)}")
frappe.destroy()
