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
	},
	"Expense Claim": {
		"on_submit": "lhdn_payroll_integration.services.submission_service.enqueue_expense_claim_submission",
		"on_cancel": "lhdn_payroll_integration.services.cancellation_service.handle_expense_claim_cancel",
		"before_amend": "lhdn_payroll_integration.services.retention_service.check_retention_lock",
	},
	"Employee": {
		"validate": "lhdn_payroll_integration.utils.validation.validate_document_for_lhdn",
		"on_update": "lhdn_payroll_integration.services.cp21_service.handle_employee_left",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"lhdn_payroll_integration.services.status_poller.poll_pending_documents",
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
