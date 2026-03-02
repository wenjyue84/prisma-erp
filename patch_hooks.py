import os

file_path = "apps/myinvois_erpgulf/myinvois_erpgulf/hooks.py"

with open(file_path, 'r') as f:
    content = f.read()

content = content.replace('app_title = "Myinvois Erpgulf"', 'app_title = "E-Invoice"')
content = content.replace('einvoice_logo.svg', 'prisma_einvoice.svg')

with open(file_path, 'w') as f:
    f.write(content)

print(f"Updated {file_path}")
