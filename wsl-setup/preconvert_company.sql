-- Manually convert the 2 over-budget custom fields from varchar to text
-- This gives migrate ~1120 bytes of headroom to add new columns
ALTER TABLE `tabCompany`
  MODIFY COLUMN `custom_statutory_hrdf_status` TEXT,
  MODIFY COLUMN `custom_mytax_employer_rep_login_id` TEXT;
