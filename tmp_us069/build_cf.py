import json

with open('C:/Users/Jyue/Documents/1-projects/Projects/prisma-erp/tmp_us069/custom_field_current.json') as f:
    d = json.load(f)

new_fields = [
    {
        'doctype': 'Custom Field',
        'name': 'Salary Component-custom_day_type',
        'dt': 'Salary Component',
        'fieldname': 'custom_day_type',
        'fieldtype': 'Select',
        'label': 'OT Day Type',
        'description': 'For overtime components: specify the type of day worked.',
        'options': '\nNormal\nRest Day\nPublic Holiday',
        'module': 'LHDN Payroll Integration',
        'insert_after': 'custom_ea_section'
    },
    {
        'doctype': 'Custom Field',
        'name': 'Salary Component-custom_ot_hours_claimed',
        'dt': 'Salary Component',
        'fieldname': 'custom_ot_hours_claimed',
        'fieldtype': 'Float',
        'label': 'OT Hours Claimed',
        'description': 'Number of overtime hours claimed for this component.',
        'module': 'LHDN Payroll Integration',
        'insert_after': 'custom_day_type'
    }
]

d.extend(new_fields)
with open('C:/Users/Jyue/Documents/1-projects/Projects/prisma-erp/tmp_us069/custom_field_updated.json', 'w') as f:
    json.dump(d, f, indent=2)

print('Total entries:', len(d))
