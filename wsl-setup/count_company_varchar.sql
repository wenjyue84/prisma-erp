-- Count varchar columns remaining in tabCompany
SELECT COUNT(*) as varchar_cols,
       SUM(CHARACTER_MAXIMUM_LENGTH * 4) as max_row_bytes
FROM information_schema.columns
WHERE TABLE_SCHEMA = '_b8086c2fb628b866'
  AND TABLE_NAME = 'tabCompany'
  AND DATA_TYPE = 'varchar';

-- Also check if custom_mytax_employer_rep_login_id is still TEXT
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM information_schema.columns
WHERE TABLE_SCHEMA = '_b8086c2fb628b866'
  AND TABLE_NAME = 'tabCompany'
  AND COLUMN_NAME IN ('custom_statutory_hrdf_status', 'custom_mytax_employer_rep_login_id');
