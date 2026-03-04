#!/bin/bash
cd ~/frappe-bench
bench --site frontend mariadb << 'SQLEOF'
SET SQL_SAFE_UPDATES=0;

-- Show LMS workspaces before delete
SELECT name, app FROM `tabWorkspace` WHERE app = 'lms';

-- Delete LMS workspaces
DELETE FROM `tabWorkspace` WHERE app = 'lms';

-- Delete LMS workspace sidebars
DELETE FROM `tabWorkspace Sidebar` WHERE app = 'lms';

-- Check counts after
SELECT COUNT(*) as remaining_workspaces FROM `tabWorkspace`;
SELECT COUNT(*) as remaining_ws_sidebars FROM `tabWorkspace Sidebar`;
SQLEOF

echo ""
echo "=== Clearing cache ==="
bench --site frontend clear-cache
bench --site frontend clear-website-cache
echo "Done"
