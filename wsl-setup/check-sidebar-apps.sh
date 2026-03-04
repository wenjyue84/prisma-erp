#!/bin/bash
cd ~/frappe-bench
bench --site frontend mariadb << 'SQLEOF'
SET SQL_SAFE_UPDATES=0;

-- Check unique apps in Workspace Sidebar
SELECT DISTINCT app, COUNT(*) as cnt FROM `tabWorkspace Sidebar` GROUP BY app ORDER BY app;

-- Check if there's an ERPNext-related sidebar
SELECT name, app, title FROM `tabWorkspace Sidebar` LIMIT 20;
SQLEOF
