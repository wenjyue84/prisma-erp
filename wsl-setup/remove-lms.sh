#!/bin/bash
# Remove LMS from apps.txt and clean up LMS workspace records
cd ~/frappe-bench

echo "=== Before: apps.txt ==="
cat sites/apps.txt

echo ""
echo "=== Removing LMS from apps.txt ==="
grep -v '^lms$' sites/apps.txt > /tmp/apps_new.txt
mv /tmp/apps_new.txt sites/apps.txt
cat sites/apps.txt

echo ""
echo "=== Cleaning LMS workspace records from DB ==="
bench --site frontend mariadb << 'SQLEOF'
-- Delete LMS-related workspaces
DELETE FROM `tabWorkspace` WHERE app = 'lms';

-- Delete sidebar items for LMS workspaces
DELETE wsi FROM `tabWorkspace Sidebar Item` wsi
JOIN `tabWorkspace Sidebar` ws ON wsi.parent = ws.name
WHERE ws.app = 'lms';

-- Delete LMS workspace sidebars
DELETE FROM `tabWorkspace Sidebar` WHERE app = 'lms';

-- Check remaining
SELECT COUNT(*) as remaining_workspaces FROM `tabWorkspace`;
SELECT COUNT(*) as remaining_sidebars FROM `tabWorkspace Sidebar`;
SQLEOF

echo ""
echo "=== Clearing cache ==="
bench --site frontend clear-cache
bench --site frontend clear-website-cache

echo "Done. LMS removed from ERPNext site."
