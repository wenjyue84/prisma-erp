app_name = "lhdn_payroll_integration"
app_title = "LHDN Payroll Integration"
app_publisher = "Prisma Technology"
app_description = "LHDN MyInvois payroll e-Invoice compliance"
app_email = "admin@prismatechnology.com"
app_license = "mit"

# Installation
# ------------

after_install = "lhdn_payroll_integration.install.after_install"
after_migrate = "lhdn_payroll_integration.install.after_migrate"

# Jinja Template Helpers
# ----------------------

jinja = {
	"methods": [
		"lhdn_payroll_integration.utils.qr_utils.generate_qr_code_base64",
	],
}

# Document Events
# ---------------

doc_events = {
	"Salary Slip": {
		"on_submit": "lhdn_payroll_integration.services.submission_service.enqueue_salary_slip_submission",
		"on_cancel": "lhdn_payroll_integration.services.cancellation_service.handle_salary_slip_cancel",
		"before_amend": "lhdn_payroll_integration.services.retention_service.check_retention_lock",
		"validate": [
			"lhdn_payroll_integration.services.cp107_service.check_salary_slip_cp107_warning",
			"lhdn_payroll_integration.services.currency_converter.apply_myr_conversion",
		],
		"before_submit": [
			"lhdn_payroll_integration.services.age_checker_service.validate_statutory_rates_before_submit",
			"lhdn_payroll_integration.services.salary_advance_service.compute_advance_repayment_for_salary_slip",
			"lhdn_payroll_integration.services.spc_cessation_service.block_salary_slip_if_spc_pending",
		],
	},
	"Expense Claim": {
		"on_submit": "lhdn_payroll_integration.services.submission_service.enqueue_expense_claim_submission",
		"on_cancel": "lhdn_payroll_integration.services.cancellation_service.handle_expense_claim_cancel",
	},
	"Employee": {
		"validate": "lhdn_payroll_integration.services.jurisdiction_service.auto_set_labour_jurisdiction",
		"on_update": [
			"lhdn_payroll_integration.services.cp107_service.handle_foreign_employee_left",
			"lhdn_payroll_integration.services.socso_service.handle_employee_termination_socso",
			"lhdn_payroll_integration.services.spc_cessation_service.handle_employee_cessation_update",
		],
		"after_insert": "lhdn_payroll_integration.services.socso_service.handle_new_employee_socso",
	},
	"Payroll Entry": {
		"on_submit": "lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.create_monthly_compliance_records",
	},
	"Workplace Accident": {
		"after_insert": "lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.handle_accident_after_insert",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"lhdn_payroll_integration.services.status_poller.poll_pending_documents",
		"lhdn_payroll_integration.lhdn_payroll_integration.services.borang34_service.check_overdue_borang34",
	],
	"daily": [
		"lhdn_payroll_integration.services.socso_service.check_overdue_socso_borang3",
		"lhdn_payroll_integration.services.socso_service.check_overdue_socso_borang4",
		"lhdn_payroll_integration.services.fw_levy_service.check_overdue_fw_levy",
		"lhdn_payroll_integration.services.age_checker_service.check_approaching_age_60",
		"lhdn_payroll_integration.lhdn_payroll_integration.utils.wage_payment_compliance.send_wage_payment_alerts",
		"lhdn_payroll_integration.services.spc_cessation_service.check_pending_spc_alerts",
		"lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.update_overdue_compliance_records",
		"lhdn_payroll_integration.lhdn_payroll_integration.services.compliance_tracker.send_overdue_compliance_notifications",
	],
	"monthly": [
		"lhdn_payroll_integration.services.consolidation_service.run_monthly_consolidation",
	],
	"yearly": [
		"lhdn_payroll_integration.services.retention_service.run_retention_archival",
	],
}

# Fixtures
# --------

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "LHDN Payroll Integration"]]},
	{"dt": "LHDN MSIC Code"},
	{"dt": "Salary Component", "filters": [["name", "in", ["Basic Salary", "Monthly Tax Deduction", "EPF Employee", "SOCSO Employee", "EPF - Employer", "SOCSO - Employer"]]]},
	{"dt": "Workspace", "filters": [["name", "=", "LHDN Payroll"]]},
]
