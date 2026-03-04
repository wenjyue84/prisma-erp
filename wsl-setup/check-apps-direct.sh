#!/bin/bash
DB=$(python3 -c "import json; d=json.load(open('/home/wenjyue/frappe-bench/sites/frontend/site_config.json')); print(d['db_name'])")
echo "DB: $DB"
mysql -u root -padmin -e "SELECT app FROM \`${DB}\`.\`tabInstalled Application\` ORDER BY app;"
