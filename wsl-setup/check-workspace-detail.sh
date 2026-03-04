#!/bin/bash
cd ~/frappe-bench
bench --site frontend console << 'PYEOF'
import frappe

# Check workspace public flag
rows = frappe.db.get_all('Workspace',
    fields=['name', 'app', 'is_hidden', 'public', 'restrict_to_domain'],
    order_by='name')
for r in rows:
    print(f"  {r['name']}: public={r.get('public')} hidden={r.get('is_hidden')} restrict={r.get('restrict_to_domain','')}")

print()
# Check Workspace Sidebar count
sc = frappe.db.count('Workspace Sidebar')
print(f"Workspace Sidebar count: {sc}")

# Check Workspace Sidebar Item count
sic = frappe.db.count('Workspace Sidebar Item')
print(f"Workspace Sidebar Item count: {sic}")
PYEOF
