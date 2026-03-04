#!/bin/bash
cd ~/frappe-bench
bench --site frontend console << 'PYEOF'
import frappe
count = frappe.db.count('Workspace')
print(f"Total workspaces: {count}")
names = frappe.db.get_all('Workspace', fields=['name', 'module'], order_by='name')
for w in names:
    print(f"  {w['name']} ({w.get('module','')})")
PYEOF
