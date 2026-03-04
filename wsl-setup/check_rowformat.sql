SELECT row_format, COUNT(*) as cnt
FROM information_schema.tables
WHERE table_schema = '_b8086c2fb628b866'
GROUP BY row_format;
