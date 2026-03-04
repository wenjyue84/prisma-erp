#!/bin/bash
python3 -c "
import json
with open('/home/wenjyue/frappe-bench/sites/assets/assets.json') as f:
    d = json.load(f)
keys = [k for k in d.keys() if 'login' in k or 'website' in k]
for k in keys:
    print(k, '->', d[k])
"
