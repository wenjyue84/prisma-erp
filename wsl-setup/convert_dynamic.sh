#!/bin/bash
DB="_b8086c2fb628b866"
MYSQL="mysql -u root -padmin"

# Get all COMPACT tables
TABLES=$($MYSQL -N -e "
  SELECT table_name FROM information_schema.tables
  WHERE table_schema = '$DB' AND row_format = 'Compact';
" 2>/dev/null)

COUNT=0
for TABLE in $TABLES; do
  $MYSQL "$DB" -e "ALTER TABLE \`$TABLE\` ROW_FORMAT=DYNAMIC;" 2>/dev/null
  COUNT=$((COUNT + 1))
done

echo "Converted $COUNT tables to DYNAMIC row format"
