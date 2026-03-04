#!/bin/bash
cd ~/frappe-bench
bench --site frontend console << 'PYEOF'
import frappe

# All workspaces
rows = frappe.db.get_all('Workspace', fields=['name', 'module', 'app'], order_by='name')
for r in rows:
    print(f"  {r['name']}  app={r.get('app','')}  module={r.get('module','')}")

# Check if any erpnext workspace exists
erpnext_ws = [r for r in rows if r.get('app') == 'erpnext' or 'Account' in r['name'] or 'ERPNext' in r['name']]
print(f"\nERPNext workspaces: {len(erpnext_ws)}")

# Check LMS workspaces
lms_ws = [r for r in rows if r.get('app') == 'lms' or 'Learning' in r['name'] or 'LMS' in r['name']]
print(f"LMS workspaces: {len(lms_ws)}")
for r in lms_ws:
    print(f"  LMS: {r['name']}")
PYEOF
