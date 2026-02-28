import json

with open('/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json') as f:
    data = json.load(f)

new_fields = [
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_expatriate_section",
        "dt": "Employee",
        "fieldname": "custom_expatriate_section",
        "fieldtype": "Section Break",
        "label": "Expatriate / DTA Settings",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_contracted_weekly_hours",
        "collapsible": 1
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_is_tax_equalised",
        "dt": "Employee",
        "fieldname": "custom_is_tax_equalised",
        "fieldtype": "Check",
        "label": "Tax Equalised (Gross-Up)",
        "description": "If checked, employer bears the Malaysian income tax so employee receives agreed net salary.",
        "default": "0",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_expatriate_section"
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_dta_country",
        "dt": "Employee",
        "fieldname": "custom_dta_country",
        "fieldtype": "Select",
        "label": "DTA Country",
        "options": "\nSG\nGB\nUS\nAU\nCN\nJP\nDE\nNL\nIN\nID",
        "description": "Country of tax residence for DTA treaty relief. ISO 3166-1 alpha-2 code.",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_is_tax_equalised"
    },
    {
        "doctype": "Custom Field",
        "name": "Employee-custom_malaysia_presence_days",
        "dt": "Employee",
        "fieldname": "custom_malaysia_presence_days",
        "fieldtype": "Int",
        "label": "Malaysia Presence Days (YTD)",
        "description": "Year-to-date days physically present in Malaysia. Used for 182-day residency rule under ITA 1967 s.7.",
        "default": "0",
        "module": "LHDN Payroll Integration",
        "insert_after": "custom_dta_country"
    }
]

existing_names = {f.get("name") for f in data}
for field in new_fields:
    fname = field["name"]
    if fname not in existing_names:
        data.append(field)
        print("Added:", fname)
    else:
        print("Already exists:", fname)

with open('/home/frappe/frappe-bench/apps/lhdn_payroll_integration/lhdn_payroll_integration/fixtures/custom_field.json', 'w') as f:
    json.dump(data, f, indent=2)

print("Done. Total fields:", len(data))
