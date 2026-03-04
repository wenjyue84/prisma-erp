UPDATE `tabCustom Field` SET fieldtype='Small Text' WHERE name IN ('Company-custom_statutory_hrdf_status','Company-custom_mytax_employer_rep_login_id');
SELECT ROW_COUNT() AS rows_updated;
