"""
borang34_service.py — US-141: PERKESO Borang 34 Accident Notification

Under the Employees' Social Security Act 1969, employers must report any workplace
accident to SOCSO (PERKESO) within 48 hours using Borang 34. This service:
  - Auto-computes the statutory 48-hour deadline on accident creation
  - Creates a high-priority Task assigned to HR Manager
  - Escalates overdue tasks at the 46-hour mark
  - Generates 6-month wage history data for Borang 34 PDF population
"""

from datetime import datetime, timedelta

import frappe
from frappe.utils import get_datetime
from frappe.utils.data import now_datetime as nowdatetime  # alias for patch compatibility

# Statutory window constants (Employees' Social Security Act 1969)
BORANG34_DEADLINE_HOURS = 48
BORANG34_ESCALATION_HOURS = 46


def handle_accident_after_insert(doc, method=None):
	"""
	Doc event: after_insert on Workplace Accident.
	1. Compute statutory 48-hour deadline.
	2. Create a high-priority Task assigned to HR Manager role.
	"""
	_compute_and_set_deadline(doc)
	_create_borang34_task(doc)


def _compute_and_set_deadline(doc):
	"""Compute 48-hour statutory deadline from incident_date_time and save."""
	incident_dt = get_datetime(doc.incident_date_time)
	deadline = incident_dt + timedelta(hours=BORANG34_DEADLINE_HOURS)
	frappe.db.set_value("Workplace Accident", doc.name, "statutory_deadline", deadline)


def _create_borang34_task(doc):
	"""Create a high-priority ToDo / Task for HR Manager to submit Borang 34."""
	incident_dt = get_datetime(doc.incident_date_time)
	deadline = incident_dt + timedelta(hours=BORANG34_DEADLINE_HOURS)

	task = frappe.new_doc("ToDo")
	task.status = "Open"
	task.priority = "High"
	task.date = deadline.date()
	task.description = (
		f"[BORANG34-PENDING] Submit PERKESO Borang 34 for workplace accident "
		f"{doc.name} involving employee {doc.employee}. "
		f"Statutory deadline: {deadline.strftime('%Y-%m-%d %H:%M')}. "
		f"Accident location: {doc.accident_location}."
	)
	task.assigned_by_full_name = "System"
	task.reference_type = "Workplace Accident"
	task.reference_name = doc.name
	task.role = "HR Manager"
	task.insert(ignore_permissions=True)
	frappe.db.commit()


def check_overdue_borang34():
	"""
	Scheduled task (hourly): escalate overdue Borang 34 ToDo items.

	At 46 hours after the incident (2 hours before deadline), open tasks linked to
	Workplace Accident records with borang34_status='Draft' are escalated by
	setting their status to 'Overdue' in the description marker.
	"""
	now = get_datetime(nowdatetime())
	escalation_cutoff = now - timedelta(hours=BORANG34_ESCALATION_HOURS)

	# Find Draft accidents older than 46 hours
	overdue_accidents = frappe.get_all(
		"Workplace Accident",
		filters=[
			["borang34_status", "=", "Draft"],
			["incident_date_time", "<=", escalation_cutoff],
		],
		fields=["name", "employee", "incident_date_time", "statutory_deadline"],
	)

	for accident in overdue_accidents:
		# Check if open task still exists for this accident
		open_tasks = frappe.get_all(
			"ToDo",
			filters=[
				["reference_type", "=", "Workplace Accident"],
				["reference_name", "=", accident["name"]],
				["status", "=", "Open"],
				["description", "like", "%[BORANG34-PENDING]%"],
			],
			fields=["name"],
		)

		for task in open_tasks:
			frappe.db.set_value(
				"ToDo",
				task["name"],
				{
					"status": "Open",
					"priority": "High",
					"description": frappe.db.get_value("ToDo", task["name"], "description").replace(
						"[BORANG34-PENDING]", "[BORANG34-OVERDUE]"
					),
				},
			)

		# Send escalation notification to HR Manager
		_send_escalation_notification(accident)

	if overdue_accidents:
		frappe.db.commit()


def _send_escalation_notification(accident):
	"""Send a notification to HR Manager role about overdue Borang 34."""
	try:
		frappe.publish_realtime(
			event="borang34_overdue_alert",
			message={
				"accident": accident["name"],
				"employee": accident["employee"],
				"statutory_deadline": str(accident.get("statutory_deadline", "")),
			},
			room="hr_manager",
		)
	except Exception:
		pass  # Non-critical; notifications should not block the scheduler


def get_six_month_wage_history(employee, incident_date):
	"""
	Return a list of monthly gross wages for the 6 months prior to the accident.

	Required by PERKESO for computing Temporary Disablement Benefit daily rate.

	Returns:
		list[dict]: [{"period": "2025-09", "gross_pay": 3000.00}, ...]
		Ordered from oldest to most recent (6 months back from incident_date).
	"""
	from dateutil.relativedelta import relativedelta

	if isinstance(incident_date, str):
		incident_date = datetime.strptime(incident_date[:10], "%Y-%m-%d").date()
	elif isinstance(incident_date, datetime):
		incident_date = incident_date.date()

	wage_history = []

	for months_back in range(6, 0, -1):
		month_start = (incident_date - relativedelta(months=months_back)).replace(day=1)
		period_str = month_start.strftime("%Y-%m")

		# Fetch submitted salary slips for this month
		slips = frappe.get_all(
			"Salary Slip",
			filters=[
				["employee", "=", employee],
				["docstatus", "=", 1],
				["start_date", ">=", month_start],
				["start_date", "<", month_start + relativedelta(months=1)],
			],
			fields=["gross_pay"],
			order_by="start_date desc",
			limit=1,
		)

		gross_pay = slips[0]["gross_pay"] if slips else 0.0
		wage_history.append({"period": period_str, "gross_pay": float(gross_pay)})

	return wage_history


def get_borang34_data(accident_name):
	"""
	Compile all data required to populate PERKESO Borang 34.

	Returns a dict with:
	  - employee details (name, NRIC, SOCSO number, job title)
	  - employer details (PERKESO code, company name)
	  - accident description, location, witness
	  - statutory_deadline
	  - six_month_wage_history
	  - six_month_average_wage (used for TDB daily rate calculation)
	"""
	accident = frappe.get_doc("Workplace Accident", accident_name)

	employee = frappe.get_doc("Employee", accident.employee)
	company = frappe.get_doc("Company", employee.company)

	wage_history = get_six_month_wage_history(accident.employee, accident.incident_date_time)
	wages_with_data = [w for w in wage_history if w["gross_pay"] > 0]
	avg_wage = (
		sum(w["gross_pay"] for w in wages_with_data) / len(wages_with_data)
		if wages_with_data
		else 0.0
	)

	return {
		"accident_name": accident.name,
		"employee_name": employee.employee_name,
		"employee_nric": getattr(employee, "custom_nric_number", "") or "",
		"employee_socso_number": getattr(employee, "custom_socso_number", "") or "",
		"employee_job_title": employee.designation or "",
		"employer_perkeso_code": getattr(company, "custom_perkeso_employer_code", "") or "",
		"employer_name": company.company_name,
		"incident_date_time": str(accident.incident_date_time),
		"accident_location": accident.accident_location,
		"injury_description": accident.injury_description,
		"supervisor_witness_name": accident.supervisor_witness_name,
		"statutory_deadline": str(accident.statutory_deadline or ""),
		"borang34_status": accident.borang34_status,
		"six_month_wage_history": wage_history,
		"six_month_average_wage": round(avg_wage, 2),
	}
