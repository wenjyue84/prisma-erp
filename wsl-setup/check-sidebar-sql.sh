#!/bin/bash
cd ~/frappe-bench
DB=$(python3 -c "import json; d=json.load(open('sites/frontend/site_config.json')); print(d['db_name'])")
echo "DB: $DB"

bench --site frontend mariadb << SQLEOF
SELECT COUNT(*) as sidebar_count FROM \`tabWorkspace Sidebar\`;
SELECT COUNT(*) as sidebar_item_count FROM \`tabWorkspace Sidebar Item\`;
SELECT name FROM \`tabWorkspace Sidebar\` LIMIT 10;
SQLEOF
