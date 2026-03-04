#!/bin/bash
cat > /home/wenjyue/frappe-bench/sites/apps.txt << 'EOF'
frappe
erpnext
hrms
myinvois_erpgulf
lhdn_payroll_integration
prisma_assistant
frappe_assistant_core
EOF
echo "apps.txt created:"
cat /home/wenjyue/frappe-bench/sites/apps.txt
