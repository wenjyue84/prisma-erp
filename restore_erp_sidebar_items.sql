-- Restore tabWorkspace Sidebar Item records for ERP Settings workspace
-- These power the sidebar nav items AND the desktop icon route resolution

USE `_b1e3b97d8c14bf67`;

INSERT IGNORE INTO `tabWorkspace Sidebar Item` VALUES
('73i039d32v','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,12,'Other Settings','DocType','getting-started','Section Break',NULL,0,NULL,NULL,1,1,1,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73i13v9gee','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,7,'Stock Settings','DocType','stock','Link','Stock Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73i6dcb5q9','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,11,'Support Settings','DocType','support','Link','Support Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73i6pr3ij8','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,4,'POS Settings','DocType','computer','Link','POS Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73idspuel2','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,14,'Item Variant Settings','DocType',NULL,'Link','Item Variant Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73igas89rv','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,17,'Appointment Booking Settings','DocType',NULL,'Link','Appointment Booking Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73iiirlolr','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,3,'Accounts Settings','DocType','accounting','Link','Accounts Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73iilan30l','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,16,'Currency Exchange Settings','DocType',NULL,'Link','Currency Exchange Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73ilf65qcb','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,18,'Stock Reposting Settings','DocType',NULL,'Link','Stock Reposting Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73iluhuspn','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,8,'Manufacturing Settings','DocType','building-2','Link','Manufacturing Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73inv1524a','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,15,'Delivery Settings','DocType',NULL,'Link','Delivery Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73ion037ee','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,6,'Buying Settings','DocType','buying','Link','Buying Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73ip2h3623','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,1,'Global Defaults','DocType','earth','Link','Global Defaults',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73ipgae9hi','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,13,'Subscription Settings','DocType',NULL,'Link','Subscription Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73iqvsuv0n','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,2,'System Settings','DocType','washing-machine','Link','System Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73isjfq84c','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,5,'Selling Settings','DocType','sell','Link','Selling Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73itat64fl','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,9,'Projects Settings','DocType','projects','Link','Projects Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73iuesh2lh','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,10,'CRM Settings','DocType','crm','Link','CRM Settings',0,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar'),
('73iv9va28l','2025-11-17 13:19:05.050624','2026-02-26 04:46:40.221368','Administrator','Administrator',0,19,'Repost Accounting Ledger Settings','DocType',NULL,'Link','Repost Accounting Ledger Settings',1,NULL,NULL,1,0,0,0,NULL,NULL,NULL,'ERP Settings','items','Workspace Sidebar');

SELECT COUNT(*) as inserted_items FROM `tabWorkspace Sidebar Item` WHERE parent='ERP Settings';
