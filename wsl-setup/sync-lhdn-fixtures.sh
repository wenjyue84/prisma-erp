#!/bin/bash
cd ~/frappe-bench
bench --site frontend console << 'PYEOF'
import frappe
from frappe.utils.fixtures import sync_fixtures

print("Syncing lhdn_payroll_integration fixtures...")
sync_fixtures(app='lhdn_payroll_integration')
frappe.db.commit()

# Verify the 2 critical fields are still Small Text
r = frappe.db.get_all('Custom Field',
    filters={'name': ['in', ['Company-custom_statutory_hrdf_status', 'Company-custom_mytax_employer_rep_login_id']]},
    fields=['name', 'fieldtype'])
for f in r:
    print(f"  {f['name']}: {f['fieldtype']}")
print("Done")
PYEOF
