-- Fix tabCompany custom fields causing row size > 65535
UPDATE `tabCustom Field`
SET fieldtype = 'Small Text'
WHERE name IN (
  'Company-custom_statutory_hrdf_status',
  'Company-custom_mytax_employer_rep_login_id'
);

-- Convert COMPACT tables to DYNAMIC row format
SET @db = '_b8086c2fb628b866';
