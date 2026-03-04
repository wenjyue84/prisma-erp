#!/bin/bash
python3 << 'PYEOF'
import json
path = '/home/wenjyue/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field_backup.json'
with open(path) as f:
    data = json.load(f)
print(f"Total entries in backup: {len(data)}")
for item in data:
    name = item.get('name', '')
    if 'mytax' in name or 'hrdf_status' in name:
        print(f"  name={name}, fieldtype={item.get('fieldtype')}")
PYEOF
