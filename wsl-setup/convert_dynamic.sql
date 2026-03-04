SET group_concat_max_len = 1000000;
SELECT GROUP_CONCAT(
  CONCAT('ALTER TABLE `', table_name, '` ROW_FORMAT=DYNAMIC;')
  SEPARATOR '\n'
)
FROM information_schema.tables
WHERE table_schema = '_b8086c2fb628b866'
  AND row_format = 'Compact'
INTO @stmts;
PREPARE stmt FROM @stmts;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
