#!/bin/bash
# Find the line with ALTER TABLE tabCompany MODIFY and get context
grep -n "ALTER TABLE" /tmp/mysql_general2.log | grep -i "tabCompany" | head -3
echo "---"
# Get queries around line 800 (where ALTER TABLE might be)
LINE=$(grep -n "ALTER TABLE" /tmp/mysql_general2.log | grep -i "tabCompany" | head -1 | cut -d: -f1)
echo "ALTER TABLE at line: $LINE"
if [ -n "$LINE" ]; then
  START=$((LINE - 30))
  sed -n "${START},${LINE}p" /tmp/mysql_general2.log | grep -E "Query|fieldtype|Custom Field" | head -20
fi
