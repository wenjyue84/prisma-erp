-- Restore ERP Settings workspace deleted by bench migrate
-- This workspace was renamed from "ERPNext Settings" on EC2 on 2026-03-02
-- bench migrate on local deleted it as "orphaned" (not in app fixtures)

USE `_b1e3b97d8c14bf67`;

-- 1. Insert ERP Settings into tabWorkspace
INSERT IGNORE INTO `tabWorkspace` VALUES
('ERP Settings','2022-01-27 13:14:47.349433','2026-03-02 15:34:17.668403','Administrator','Administrator',0,0,'ERP Settings','ERP Settings',19.000000000,'','','Setup','erpnext','Workspace',NULL,NULL,NULL,'setting',NULL,'',0,1,0,'[{"id":"NO5yYHJopc","type":"header","data":{"text":"<span class=\"h4\"><b>Your Shortcuts\n\t\t\t\n\t\t\n\t\t\t\n\t\t\n\t\t\t\n\t\t</b></span>","col":12}},{"id":"CDxIM-WuZ9","type":"shortcut","data":{"shortcut_name":"System Settings","col":3}},{"id":"-Uh7DKJNJX","type":"shortcut","data":{"shortcut_name":"Accounts Settings","col":3}},{"id":"K9ST9xcDXh","type":"shortcut","data":{"shortcut_name":"Stock Settings","col":3}},{"id":"27IdVHVQMb","type":"shortcut","data":{"shortcut_name":"Selling Settings","col":3}},{"id":"Rwp5zff88b","type":"shortcut","data":{"shortcut_name":"Buying Settings","col":3}},{"id":"hkfnQ2sevf","type":"shortcut","data":{"shortcut_name":"Global Defaults","col":3}},{"id":"jjxI_PDawD","type":"shortcut","data":{"shortcut_name":"Print Settings","col":3}}]',NULL,NULL,NULL,NULL);

-- 2. Insert ERP Settings into tabWorkspace Sidebar
INSERT IGNORE INTO `tabWorkspace Sidebar` VALUES
('ERP Settings','2025-11-17 13:19:05.050624','2026-01-10 00:06:12.956275','Administrator','Administrator',0,0,'ERP Settings','setting',NULL,'Setup',1,'erpnext',NULL,NULL,NULL,NULL,NULL);

-- 3. Insert tabWorkspace Link records for ERP Settings
INSERT IGNORE INTO `tabWorkspace Link` VALUES
('6rlgsojri4','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,2,'Link','Export Data',NULL,NULL,0,'DocType','Data Export',NULL,'',NULL,0,0,0,'ERP Settings','links','Workspace'),
('6rlkt83ua0','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,3,'Link','Bulk Update',NULL,NULL,0,'DocType','Bulk Update',NULL,'',NULL,0,0,0,'ERP Settings','links','Workspace'),
('6rll4m58s7','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,1,'Link','Import Data',NULL,NULL,0,'DocType','Data Import',NULL,'',NULL,0,0,0,'ERP Settings','links','Workspace'),
('6rlm78qvvq','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,4,'Link','Download Backups',NULL,NULL,0,'Page','backups',NULL,'',NULL,0,0,0,'ERP Settings','links','Workspace'),
('6rlonhaobo','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,5,'Link','Deleted Documents',NULL,NULL,0,'DocType','Deleted Document',NULL,'',NULL,0,0,0,'ERP Settings','links','Workspace');

-- 4. Insert tabWorkspace Shortcut records for ERP Settings
INSERT IGNORE INTO `tabWorkspace Shortcut` VALUES
('6rl568ihdt','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,5,'DocType','Stock Settings',NULL,NULL,NULL,'Stock Settings','stock',NULL,NULL,NULL,NULL,NULL,'ERP Settings','shortcuts','Workspace'),
('6rla7f8qj6','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,2,'DocType','System Settings',NULL,'List',NULL,'System Settings',NULL,NULL,NULL,NULL,'Grey',NULL,'ERP Settings','shortcuts','Workspace'),
('6rlac9fukf','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,7,'DocType','Buying Settings',NULL,NULL,NULL,'Buying Settings','buying',NULL,NULL,NULL,NULL,NULL,'ERP Settings','shortcuts','Workspace'),
('6rlaqoso2g','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,3,'DocType','Accounts Settings',NULL,NULL,NULL,'Accounts Settings','accounting',NULL,NULL,NULL,NULL,NULL,'ERP Settings','shortcuts','Workspace'),
('6rli09to9e','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,1,'DocType','Print Settings',NULL,'List',NULL,'Print Settings',NULL,NULL,NULL,NULL,'Grey',NULL,'ERP Settings','shortcuts','Workspace'),
('6rljioepus','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,6,'DocType','Selling Settings',NULL,NULL,NULL,'Selling Settings','sell',NULL,NULL,NULL,NULL,NULL,'ERP Settings','shortcuts','Workspace'),
('6rlka9fsrr','2022-01-27 13:14:47.349433','2026-02-26 04:46:14.908325','Administrator','Administrator',0,4,'DocType','Global Defaults',NULL,'List',NULL,'Global Defaults',NULL,NULL,NULL,NULL,'Grey',NULL,'ERP Settings','shortcuts','Workspace');

-- 5. Update tabDesktop Icon: ERPNext Settings → link_to = ERP Settings (already correct, confirm)
-- SELECT name, label, link_to FROM `tabDesktop Icon` WHERE name = 'ERPNext Settings';
UPDATE `tabDesktop Icon`
SET link_to = 'ERP Settings', label = 'ERP Settings'
WHERE name = 'ERPNext Settings' AND label != 'ERP Settings';

SELECT 'ERP Settings restore complete' as status;
SELECT COUNT(*) as workspace_count FROM `tabWorkspace` WHERE name = 'ERP Settings';
SELECT COUNT(*) as sidebar_count FROM `tabWorkspace Sidebar` WHERE name = 'ERP Settings';
