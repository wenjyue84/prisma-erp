#!/bin/bash
python3 -c "
import json
path = '/home/wenjyue/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field_backup.json'
try:
    with open(path) as f:
        data = json.load(f)
    for item in data:
        if 'mytax_employer_rep_login_id' in item.get('name', ''):
            print('BACKUP name:', item['name'])
            print('BACKUP fieldtype:', item['fieldtype'])
except Exception as e:
    print('Error:', e)
"
