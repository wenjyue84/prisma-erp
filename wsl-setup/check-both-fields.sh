#!/bin/bash
python3 << 'PYEOF'
import json
path = '/home/wenjyue/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json'
with open(path) as f:
    data = json.load(f)
for item in data:
    name = item.get('name', '')
    if 'statutory_hrdf_status' in name or 'mytax_employer_rep_login_id' in name:
        print(f"name={name}")
        print(f"  fieldtype={item.get('fieldtype')}")
        print(f"  options={item.get('options', 'N/A')}")
        print()
PYEOF
