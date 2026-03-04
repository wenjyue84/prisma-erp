-- Check tabCompany column count and row size estimate
SELECT
  COUNT(*) as varchar_count,
  SUM(CASE WHEN data_type = 'varchar' THEN character_maximum_length * 4 ELSE 0 END) as estimated_row_bytes
FROM information_schema.columns
WHERE table_schema = '_b8086c2fb628b866'
  AND table_name = 'tabCompany'
  AND data_type IN ('varchar', 'char');

-- Show actual row format
SELECT table_name, row_format, data_length
FROM information_schema.tables
WHERE table_schema = '_b8086c2fb628b866'
  AND table_name = 'tabCompany';
