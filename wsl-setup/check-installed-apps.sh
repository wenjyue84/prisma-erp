#!/bin/bash
cd ~/frappe-bench
bench --site frontend mariadb << 'SQLEOF'
SELECT app FROM `tabInstalled Application` ORDER BY app;
SQLEOF
