"""
compliance_tracker.py — Statutory Compliance Submission Tracker

Tracks monthly and annual statutory filing deadlines for Malaysian employers:
- PCB (15th of following month) — ITA 1967, Section 83(6); 10% late penalty
- EPF (15th of following month) — EPF Act 1991, Section 43; 6% p.a. late penalty
- SOCSO (15th of following month) — ESSA 1969; 6% p.a. late penalty
- EIS (15th of following month) — EIS Act 2017
- HRDF levy (15th of following month) — PSMB Act 2001
- EA Form (28 Feb each year) — ITA 1967, Section 83(1A)
- Borang E (31 Mar each year) — ITA 1967, Section 83(1)

Auto-creates Statutory Compliance Submission records when Payroll Entry is submitted.
Daily scheduler checks for overdue records and sends notifications.
"""

import calendar

import frappe
from frappe.utils import add_months, date_diff, get_datetime, getdate, today


# Penalty reference information per compliance type
_PENALTY_INFO = {
	"PCB": "Late PCB remittance: 10% late payment penalty — ITA 1967, Section 83(6).",
	"EPF": "Late EPF contribution: 6% per annum from due date — EPF Act 1991, Section 45.",
	"SOCSO": "Late SOCSO contribution: 6% per annum from due date — ESSA 1969.",
	"EIS": "Late EIS contribution: 6% per annum from due date — EIS Act 2017.",
	"HRDF": "Late HRDF levy: interest applies under PSMB Act 2001.",
	"EA Form": "Late EA Form: RM200–RM20,000 fine under ITA 1967, Section 120.",
	"Borang E": "Late Borang E: RM200–RM20,000 fine under ITA 1967, Section 120.",
}

# Monthly filings auto-created from Payroll Entry (due on 15th of following month)
_MONTHLY_TYPES = ["PCB", "EPF", "SOCSO", "EIS", "HRDF"]


def _get_monthly_due_date(payroll_end_date):
	"""Return the 15th of the month following payroll_end_date."""
	following_month = add_months(getdate(payroll_end_date), 1)
	# Replace day with 15
	return following_month.replace(day=15)


def _get_payroll_period_str(payroll_end_date):
	"""Return 'YYYY-MM' string from payroll end date."""
	d = getdate(payroll_end_date)
	return f"{d.year:04d}-{d.month:02d}"


def create_monthly_compliance_records(doc, method):
	"""Hook: Payroll Entry on_submit.

	Creates one Statutory Compliance Submission record per monthly filing type
	(PCB, EPF, SOCSO, EIS, HRDF) for the payroll period, unless a record already
	exists for that combination of (company, compliance_type, payroll_period).
	"""
	company = doc.company
	payroll_period = _get_payroll_period_str(doc.end_date)
	due_date = _get_monthly_due_date(doc.end_date)

	created = []
	for compliance_type in _MONTHLY_TYPES:
		if frappe.db.exists(
			"Statutory Compliance Submission",
			{
				"company": company,
				"compliance_type": compliance_type,
				"payroll_period": payroll_period,
			},
		):
			continue

		record = frappe.new_doc("Statutory Compliance Submission")
		record.compliance_type = compliance_type
		record.company = company
		record.payroll_period = payroll_period
		record.due_date = due_date
		record.submission_status = "Pending"
		record.penalty_info = _PENALTY_INFO.get(compliance_type, "")
		record.payroll_entry = doc.name
		record.insert(ignore_permissions=True)
		created.append(compliance_type)

	if created:
		frappe.msgprint(
			f"Created {len(created)} Statutory Compliance Submission record(s) "
			f"for {payroll_period}: {', '.join(created)}. Due: {due_date}.",
			title="Compliance Calendar Updated",
			indicator="blue",
		)


def create_annual_compliance_records(company, year):
	"""Create EA Form and Borang E records for the given year and company.

	Called at year-end payroll run. Idempotent — skips if records exist.

	Args:
		company (str): Company name.
		year (int): The tax year (e.g. 2026).
	"""
	annual = [
		{
			"compliance_type": "EA Form",
			"due_date": f"{year}-02-28",
			"payroll_period": f"{year - 1}-12",  # for previous year's income
		},
		{
			"compliance_type": "Borang E",
			"due_date": f"{year}-03-31",
			"payroll_period": f"{year - 1}-12",
		},
	]

	created = []
	for item in annual:
		if frappe.db.exists(
			"Statutory Compliance Submission",
			{
				"company": company,
				"compliance_type": item["compliance_type"],
				"payroll_period": item["payroll_period"],
			},
		):
			continue

		record = frappe.new_doc("Statutory Compliance Submission")
		record.compliance_type = item["compliance_type"]
		record.company = company
		record.payroll_period = item["payroll_period"]
		record.due_date = item["due_date"]
		record.submission_status = "Pending"
		record.penalty_info = _PENALTY_INFO.get(item["compliance_type"], "")
		record.insert(ignore_permissions=True)
		created.append(item["compliance_type"])

	return created


def update_overdue_compliance_records():
	"""Daily scheduled job: flip Pending → Overdue for past-due records."""
	today_date = today()
	pending_records = frappe.get_all(
		"Statutory Compliance Submission",
		filters={"submission_status": "Pending", "due_date": ["<", today_date]},
		fields=["name", "compliance_type", "company", "payroll_period", "due_date"],
	)

	for record in pending_records:
		frappe.db.set_value(
			"Statutory Compliance Submission",
			record["name"],
			"submission_status",
			"Overdue",
		)


def send_overdue_compliance_notifications():
	"""Daily scheduled job: notify HR Manager of approaching or overdue filings.

	Sends notifications for submissions where:
	- Status is Pending AND due in 0–5 days (approaching), OR
	- Status is Overdue
	"""
	today_date = getdate(today())

	# Records overdue
	overdue_records = frappe.get_all(
		"Statutory Compliance Submission",
		filters={"submission_status": "Overdue"},
		fields=["name", "compliance_type", "company", "payroll_period", "due_date"],
	)

	# Records approaching (due in ≤5 days)
	approaching_records = frappe.get_all(
		"Statutory Compliance Submission",
		filters={
			"submission_status": "Pending",
			"due_date": ["between", [today_date, today_date.replace(day=today_date.day + 5) if today_date.day <= 26 else today_date]],
		},
		fields=["name", "compliance_type", "company", "payroll_period", "due_date"],
	)

	all_records = overdue_records + approaching_records
	if not all_records:
		return

	# Get HR Manager users to notify
	hr_managers = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
		pluck="parent",
	)

	for record in all_records:
		days_remaining = date_diff(record["due_date"], today_date)
		status_label = "OVERDUE" if days_remaining < 0 else f"due in {days_remaining} day(s)"

		subject = (
			f"[Compliance Alert] {record['compliance_type']} for "
			f"{record['payroll_period']} is {status_label}"
		)
		message = (
			f"Statutory filing reminder:<br><br>"
			f"<b>Type:</b> {record['compliance_type']}<br>"
			f"<b>Company:</b> {record['company']}<br>"
			f"<b>Period:</b> {record['payroll_period']}<br>"
			f"<b>Due Date:</b> {record['due_date']}<br>"
			f"<b>Status:</b> {status_label}<br><br>"
			f"Please update the submission status in the "
			f"<a href='/app/statutory-compliance-submission/{record['name']}'>Compliance Calendar</a>."
		)

		for user in hr_managers:
			frappe.sendmail(
				recipients=[user],
				subject=subject,
				message=message,
				now=True,
			)

			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"subject": subject,
					"email_content": message,
					"for_user": user,
					"type": "Alert",
					"document_type": "Statutory Compliance Submission",
					"document_name": record["name"],
				}
			).insert(ignore_permissions=True)


def get_compliance_status_for_dashboard(company=None):
	"""Return compliance records grouped by status for dashboard widget.

	Returns:
		dict with keys 'green' (>5 days), 'amber' (2-5 days), 'red' (0-2 days or overdue)
	"""
	today_date = getdate(today())
	filters = {"submission_status": ["in", ["Pending", "Overdue"]]}
	if company:
		filters["company"] = company

	records = frappe.get_all(
		"Statutory Compliance Submission",
		filters=filters,
		fields=["name", "compliance_type", "company", "payroll_period", "due_date", "submission_status", "penalty_info"],
	)

	result = {"green": [], "amber": [], "red": []}
	for r in records:
		if r["submission_status"] == "Overdue":
			result["red"].append(r)
			continue
		days_remaining = date_diff(r["due_date"], today_date)
		if days_remaining > 5:
			result["green"].append(r)
		elif days_remaining >= 2:
			result["amber"].append(r)
		else:
			result["red"].append(r)

	return result
