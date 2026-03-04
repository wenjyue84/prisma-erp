#!/bin/bash
cd ~/frappe-bench
# Sync fixtures for all apps except lhdn_payroll_integration
# (we manually fixed lhdn's Company fields — syncing would revert them)
bench --site frontend console << 'PYEOF'
import frappe
from frappe.utils.fixtures import sync_fixtures

# Sync fixtures for each app except lhdn_payroll_integration
for app in frappe.get_installed_apps():
    if app != 'lhdn_payroll_integration':
        print(f"Syncing fixtures for {app}...")
        sync_fixtures(app=app)
    else:
        print(f"Skipping {app} (manual Company field fix applied)")

frappe.db.commit()
print("Done")
PYEOF
