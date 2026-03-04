#!/bin/bash
cd ~/frappe-bench
bench --site frontend console << 'PYEOF'
import frappe

sc = frappe.db.count('Workspace Sidebar')
sic = frappe.db.count('Workspace Sidebar Item')
print(f"Workspace Sidebar count: {sc}")
print(f"Workspace Sidebar Item count: {sic}")

# Check if there's a Workspace with route field
rows = frappe.db.get_all('Workspace', fields=['name', 'route'], order_by='name', limit=5)
for r in rows:
    print(f"  name={r['name']} route={r.get('route', 'N/A')}")
PYEOF
