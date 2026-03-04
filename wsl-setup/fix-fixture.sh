#!/bin/bash
FIXTURE="$HOME/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json"

# Change fieldtype for custom_mytax_employer_rep_login_id from Data to Small Text
# The entry spans lines - use Python for reliable JSON editing
python3 << 'PYEOF'
import json

path = "/home/wenjyue/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json"

with open(path) as f:
    data = json.load(f)

changed = 0
for item in data:
    if (item.get("name") == "Company-custom_mytax_employer_rep_login_id" and
            item.get("fieldtype") == "Data"):
        item["fieldtype"] = "Small Text"
        changed += 1

with open(path, "w") as f:
    json.dump(data, f, indent=1, ensure_ascii=False)

print(f"Changed {changed} entries")
PYEOF
