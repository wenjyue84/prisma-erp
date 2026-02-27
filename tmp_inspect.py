import frappe
frappe.init(site='frontend', sites_path='sites')
frappe.connect()

# Check Employee fields
print("=== Employee TIN/IC fields ===")
cols = frappe.db.sql("DESCRIBE `tabEmployee`", as_dict=True)
for c in cols:
    name = c.get('Field', '')
    if any(k in name.lower() for k in ['tin', 'nric', 'ic', 'passport', 'custom_lhdn', 'custom_id', 'custom_tin', 'custom_ic', 'nationality', 'custom_pcb']):
        print(f"  {name}: {c.get('Type')}")

print("\n=== Salary Slip fields ===")
cols2 = frappe.db.sql("DESCRIBE `tabSalary Slip`", as_dict=True)
for c in cols2:
    name = c.get('Field', '')
    if any(k in name.lower() for k in ['gross', 'total_earn', 'net_pay', 'pcb', 'tax', 'total_deduct', 'start_date', 'end_date', 'employee_name', 'company']):
        print(f"  {name}: {c.get('Type')}")

print("\n=== Salary Detail fields ===")
cols3 = frappe.db.sql("DESCRIBE `tabSalary Detail`", as_dict=True)
for c in cols3:
    name = c.get('Field', '')
    if any(k in name.lower() for k in ['salary_component', 'amount', 'parent', 'parenttype', 'parentfield', 'abbr', 'pcb', 'custom']):
        print(f"  {name}: {c.get('Type')}")

print("\nDone")
