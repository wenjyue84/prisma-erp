"""LHDN monthly consolidation service.

Runs as a monthly scheduled job. Finds all pending, unconsolidated Salary Slips
and Expense Claims from the previous calendar month. High-value documents
(> RM 10,000) are submitted individually. The rest are submitted as a batch
via a single consolidated XML using build_consolidated_xml().
All processed documents are marked with custom_is_consolidated=1.

Enforces LHDN's 7-calendar-day deadline after month-end for consolidated
submission. If the deadline is missed, logs an error and raises ValidationError.
"""
import calendar
from datetime import date, timedelta

import frappe
import requests

from lhdn_payroll_integration.services import submission_service
from lhdn_payroll_integration.services.payload_builder import (
	build_consolidated_xml,
	prepare_submission_wrapper,
)

HIGH_VALUE_THRESHOLD = 10000
DEADLINE_DAYS = 7
SUBMISSION_ENDPOINT = "/api/v1.0/documentsubmissions"


def get_consolidation_deadline(target_month):
	"""Calculate the LHDN consolidation submission deadline for a given month.

	LHDN requires consolidated self-billed invoices to be submitted within
	7 calendar days after the last day of the target month.

	Args:
		target_month: Month string in 'YYYY-MM' format (e.g. '2026-01').

	Returns:
		date: The deadline date (7 days after the last day of target_month).
	"""
	year, month = target_month.split("-")
	year = int(year)
	month = int(month)
	last_day_num = calendar.monthrange(year, month)[1]
	last_day = date(year, month, last_day_num)
	return last_day + timedelta(days=DEADLINE_DAYS)


def _submit_consolidated_batch(batch_docnames, target_month, company_name):
	"""Submit a batch of Salary Slip docnames as ONE consolidated XML to LHDN.

	Builds a single UBL 2.1 XML aggregating all batch documents, wraps it for
	the LHDN API, POSTs it once, and logs the accepted UUID.

	Args:
		batch_docnames: List of Salary Slip document names to consolidate.
		target_month: Target month string in 'YYYY-MM' format.
		company_name: The company name used for auth and URL resolution.

	Returns:
		str or None: The LHDN submission UUID if accepted, None otherwise.
	"""
	xml_string = build_consolidated_xml(batch_docnames, target_month)
	submission_data = prepare_submission_wrapper(xml_string, f"CONSOL-{target_month}")

	token = submission_service.get_access_token(company_name)
	company = frappe.get_doc("Company", company_name)

	if company.custom_integration_type == "Sandbox":
		base_url = company.custom_sandbox_url
	else:
		base_url = company.custom_production_url
	url = f"{base_url.rstrip('/')}{SUBMISSION_ENDPOINT}"

	headers = {
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json",
	}

	response = requests.post(url, json=submission_data, headers=headers)
	data = response.json()

	accepted = data.get("acceptedDocuments", [])
	rejected = data.get("rejectedDocuments", [])

	if accepted:
		uuid = accepted[0].get("uuid", "")
		frappe.log_error(
			title="LHDN Consolidation Log",
			message=(
				f"Consolidated batch submitted successfully. "
				f"UUID: {uuid}. "
				f"Month: {target_month}. "
				f"Documents ({len(batch_docnames)}): {', '.join(batch_docnames)}"
			),
		)
		return uuid
	elif rejected:
		error_info = rejected[0].get("error", {})
		frappe.log_error(
			title="LHDN Consolidation Failed",
			message=(
				f"Consolidated batch rejected. "
				f"Month: {target_month}. "
				f"Error: {error_info}. "
				f"Documents: {', '.join(batch_docnames)}"
			),
		)
	return None


def run_monthly_consolidation():
	"""Monthly scheduled job to consolidate and submit pending LHDN documents.

	Queries the previous calendar month for pending Salary Slips and Expense Claims
	that have not yet been consolidated. High-value documents (> RM 10,000) are
	submitted individually. Remaining Salary Slips are submitted as ONE consolidated
	batch via build_consolidated_xml(). Expense Claims in-scope are submitted
	individually. After successful submission, all processed documents are marked
	as consolidated.

	Raises frappe.ValidationError if the 7-day deadline has been missed.
	"""
	# Calculate previous month date range
	today = frappe.utils.today()
	prev_month_date = frappe.utils.add_months(today, -1)
	first_day = frappe.utils.get_first_day(prev_month_date)
	last_day = frappe.utils.get_last_day(prev_month_date)

	# Check 7-day deadline
	target_month = f"{first_day.year:04d}-{first_day.month:02d}"
	deadline = get_consolidation_deadline(target_month)
	today_date = date.fromisoformat(str(today))

	if today_date > deadline:
		frappe.log_error(
			message=f"LHDN consolidation deadline missed for {target_month}. "
					f"Deadline was {deadline}. Current date: {today_date}.",
			title="LHDN Consolidation Deadline Missed",
		)
		frappe.throw(
			f"LHDN consolidation deadline missed for {target_month}. "
			f"The deadline was {deadline} (7 days after month-end). "
			f"Please contact LHDN for late submission guidance.",
			frappe.ValidationError,
		)

	# Query pending, unconsolidated Salary Slips from previous month
	salary_slips = frappe.get_all(
		"Salary Slip",
		filters={
			"custom_lhdn_status": "Pending",
			"custom_is_consolidated": 0,
			"posting_date": ["between", [first_day, last_day]],
		},
		fields=["name", "doctype", "net_pay", "company", "custom_lhdn_status",
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

	# Submit batch Salary Slips as ONE consolidated XML (single HTTP call)
	if batch_slips:
		batch_docnames = [s.name for s in batch_slips]
		company_name = batch_slips[0].company
		_submit_consolidated_batch(batch_docnames, target_month, company_name)
		for slip in batch_slips:
			frappe.db.set_value("Salary Slip", slip.name, "custom_is_consolidated", 1)

	# Submit batch Expense Claims individually (consolidation applies to slips only)
	for claim in batch_claims:
		submission_service.process_expense_claim(claim.name)
		frappe.db.set_value("Expense Claim", claim.name, "custom_is_consolidated", 1)
