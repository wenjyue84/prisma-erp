#!/bin/bash
cd ~/frappe-bench
bench --site frontend mariadb << 'SQLEOF'
SELECT name, app, module, is_hidden
FROM `tabWorkspace`
WHERE name LIKE '%Learn%'
   OR name LIKE '%lms%'
   OR module LIKE '%Learn%'
   OR module LIKE '%lms%';
SQLEOF
