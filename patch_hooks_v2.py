import os

file_path = "apps/myinvois_erpgulf/myinvois_erpgulf/hooks.py"

with open(file_path, 'r') as f:
    content = f.read()

# Fix the broken hook by hardcoding the app name string
content = content.replace('"name": app_name', '"name": "myinvois_erpgulf"')

with open(file_path, 'w') as f:
    f.write(content)

print(f"Hardcoded app name in {file_path}")
