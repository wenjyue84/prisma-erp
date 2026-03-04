-- Fix fieldtype so Frappe won't try to change TEXT columns back to varchar
UPDATE `tabCustom Field`
SET fieldtype = 'Small Text'
WHERE fieldname IN ('custom_statutory_hrdf_status', 'custom_mytax_employer_rep_login_id')
  AND dt = 'Company';

SELECT name, fieldtype, fieldname FROM `tabCustom Field`
WHERE fieldname IN ('custom_statutory_hrdf_status', 'custom_mytax_employer_rep_login_id');
