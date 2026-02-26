"""LHDN monthly consolidation service.

Runs as a monthly scheduled job. Finds all pending, unconsolidated Salary Slips
and Expense Claims from the previous calendar month. High-value documents
(> RM 10,000) are submitted individually. The rest are submitted as a batch.
All processed documents are marked with custom_is_consolidated=1.
"""

import frappe
from lhdn_payroll_integration.services import submission_service

HIGH_VALUE_THRESHOLD = 10000


def run_monthly_consolidation():
	"""Monthly scheduled job to consolidate and submit pending LHDN documents.

	Queries the previous calendar month for pending Salary Slips and Expense Claims
	that have not yet been consolidated. High-value documents (> RM 10,000) are
	submitted individually. Remaining documents are submitted as a consolidated batch.
	After successful submission, all processed documents are marked as consolidated.
	"""
	# Calculate previous month date range
	today = frappe.utils.today()
	prev_month_date = frappe.utils.add_months(today, -1)
	first_day = frappe.utils.get_first_day(prev_month_date)
	last_day = frappe.utils.get_last_day(prev_month_date)

	# Query pending, unconsolidated Salary Slips from previous month
	salary_slips = frappe.get_all(
		"Salary Slip",
		filters={
			"custom_lhdn_status": "Pending",
			"custom_is_consolidated": 0,
			"posting_date": ["between", [first_day, last_day]],
		},
		fields=["name", "doctype", "net_pay", "custom_lhdn_status",
				"custom_is_consolidated", "posting_date"],
	)

	# Query pending, unconsolidated Expense Claims from previous month
	expense_claims = frappe.get_all(
		"Expense Claim",
		filters={
			"custom_lhdn_status": "Pending",
			"custom_is_consolidated": 0,
			"posting_date": ["between", [first_day, last_day]],
		},
		fields=["name", "doctype", "total_sanctioned_amount", "custom_lhdn_status",
				"custom_is_consolidated", "posting_date"],
	)

	# Separate high-value documents for individual submission
	high_value_slips = [s for s in salary_slips if s.net_pay > HIGH_VALUE_THRESHOLD]
	batch_slips = [s for s in salary_slips if s.net_pay <= HIGH_VALUE_THRESHOLD]

	high_value_claims = [c for c in expense_claims if c.total_sanctioned_amount > HIGH_VALUE_THRESHOLD]
	batch_claims = [c for c in expense_claims if c.total_sanctioned_amount <= HIGH_VALUE_THRESHOLD]

	# Submit high-value documents individually
	for slip in high_value_slips:
		submission_service.process_salary_slip(slip.name)
		frappe.db.set_value("Salary Slip", slip.name, "custom_is_consolidated", 1)

	for claim in high_value_claims:
		submission_service.process_expense_claim(claim.name)
		frappe.db.set_value("Expense Claim", claim.name, "custom_is_consolidated", 1)

	# Submit remaining documents as consolidated batch
	for slip in batch_slips:
		submission_service.process_salary_slip(slip.name)
		frappe.db.set_value("Salary Slip", slip.name, "custom_is_consolidated", 1)

	for claim in batch_claims:
		submission_service.process_expense_claim(claim.name)
		frappe.db.set_value("Expense Claim", claim.name, "custom_is_consolidated", 1)
