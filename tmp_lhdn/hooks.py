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
	},
	"Expense Claim": {
		"on_submit": "lhdn_payroll_integration.services.submission_service.enqueue_expense_claim_submission",
		"on_cancel": "lhdn_payroll_integration.services.cancellation_service.handle_expense_claim_cancel",
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
}

# Fixtures
# --------

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "LHDN Payroll Integration"]]},
	{"dt": "LHDN MSIC Code"},
]
