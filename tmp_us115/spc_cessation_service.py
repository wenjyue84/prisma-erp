"""Service for e-SPC cessation form determination and SPC tracking.

US-115: Auto-Submit CP21/CP22A/CP22B via e-SPC MyTax at Cessation or Departure

From 1 January 2025, CP21 (leaving Malaysia), CP22A (private sector resignation/retirement/death),
and CP22B (public sector) must be submitted via e-SPC on MyTax — manual forms no longer accepted.

Income Tax Act 1967, Section 83(3): employer must withhold final salary until SPC received.
"""
import frappe
from frappe.utils import add_days, date_diff, getdate, today

# Cessation types that trigger CP22A (private sector)
CESSATION_TYPES_CP22A = {"Resignation", "Retirement", "Termination", "Death"}

# Cessation types that trigger CP21 (departure from Malaysia)
CESSATION_TYPES_CP21 = {"Departure from Malaysia"}


def handle_employee_cessation_update(doc, method):
	"""Detect when Cessation Date is set on Employee and auto-create the correct e-SPC form.

	Rules:
	- Departure from Malaysia (or foreign worker): CP21
	- Resignation / Retirement / Termination / Death (private sector): CP22A
	- Initialise SPC Status to 'Pending' if not already set.

	Called on Employee on_update.
	"""
	cessation_date = doc.get("custom_cessation_date")
	if not cessation_date:
		return

	cessation_type = doc.get("custom_cessation_type")
	if not cessation_type:
		return

	# Foreign workers or departures from Malaysia → CP21
	if cessation_type in CESSATION_TYPES_CP21 or doc.get("custom_is_foreign_worker"):
		_ensure_cp21_exists(doc, cessation_date)
	elif cessation_type in CESSATION_TYPES_CP22A:
		_ensure_cp22a_exists(doc, cessation_date, cessation_type)

	# Initialise SPC Status to Pending if not yet set
	if not doc.get("custom_spc_status"):
		frappe.db.set_value("Employee", doc.name, "custom_spc_status", "Pending")


def _ensure_cp21_exists(doc, cessation_date):
	"""Create LHDN CP21 record if one does not already exist for the employee."""
	if frappe.db.exists("LHDN CP21", {"employee": doc.name}):
		return

	cp21 = frappe.new_doc("LHDN CP21")
	cp21.employee = doc.name
	cp21.last_working_date = cessation_date
	cp21.reason = "Departure from Malaysia"
	cp21.insert(ignore_permissions=True)

	frappe.msgprint(
		f"LHDN CP21 record <b>{cp21.name}</b> created for {doc.employee_name}. "
		f"Submit via e-SPC on MyTax at least 30 days before cessation date "
		f"({cessation_date}).",
		title="CP21 Created — e-SPC Submission Required",
		indicator="orange",
	)


def _ensure_cp22a_exists(doc, cessation_date, cessation_type):
	"""Create LHDN CP22A record if one does not already exist for the employee."""
	if frappe.db.exists("LHDN CP22A", {"employee": doc.name}):
		return

	# Calculate age at cessation for CP22A record
	age = 0
	if doc.date_of_birth:
		cessation_dt = getdate(cessation_date)
		dob = getdate(doc.date_of_birth)
		age = cessation_dt.year - dob.year
		if (cessation_dt.month, cessation_dt.day) < (dob.month, dob.day):
			age -= 1

	cp22a = frappe.new_doc("LHDN CP22A")
	cp22a.employee = doc.name
	cp22a.date_of_birth = doc.date_of_birth
	cp22a.cessation_date = cessation_date
	cp22a.reason = cessation_type
	cp22a.status = "Pending"
	cp22a.insert(ignore_permissions=True)

	frappe.msgprint(
		f"LHDN CP22A record <b>{cp22a.name}</b> created for {doc.employee_name} "
		f"(age {age} at cessation). "
		f"Submit via e-SPC on MyTax at least 30 days before cessation date "
		f"({cessation_date}).",
		title="CP22A Created — e-SPC Submission Required",
		indicator="orange",
	)


def check_pending_spc_alerts():
	"""Daily scheduler: alert HR Manager 35 days before cessation if SPC still Pending.

	The 35-day trigger ensures the employer has a 30-day advance submission window
	(14 working days processing time + 5-day buffer) per LHDN e-SPC requirements.

	Called daily by the scheduler.
	"""
	alert_cutoff = add_days(today(), 35)

	employees = frappe.get_all(
		"Employee",
		filters={
			"custom_cessation_date": ["between", [today(), alert_cutoff]],
			"custom_spc_status": "Pending",
		},
		fields=[
			"name",
			"employee_name",
			"custom_cessation_date",
			"custom_cessation_type",
			"company",
		],
	)

	for emp in employees:
		days_remaining = date_diff(emp["custom_cessation_date"], today())

		frappe.log_error(
			title="SPC Submission Alert — 35-Day Warning",
			message=(
				f"Employee {emp['employee_name']} ({emp['name']}) has cessation date "
				f"{emp['custom_cessation_date']} ({days_remaining} days remaining). "
				f"Cessation type: {emp.get('custom_cessation_type', 'N/A')}. "
				f"SPC Status is still Pending — submit via e-SPC on MyTax immediately "
				f"to meet the 30-day advance filing requirement."
			),
		)

		_notify_hr_manager(emp, days_remaining)

	if employees:
		frappe.db.commit()


def _notify_hr_manager(emp, days_remaining):
	"""Send Notification Log to users with HR Manager role."""
	hr_managers = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
	)

	for hr in hr_managers:
		try:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": hr["parent"],
					"type": "Alert",
					"document_type": "Employee",
					"document_name": emp["name"],
					"subject": (
						f"SPC Alert: {emp['employee_name']} cessation in "
						f"{days_remaining} days — action required"
					),
					"email_content": (
						f"Employee <b>{emp['employee_name']}</b> has cessation date "
						f"<b>{emp['custom_cessation_date']}</b> ({days_remaining} days remaining). "
						f"SPC Status is still <b>Pending</b>. "
						f"Please submit the required form via e-SPC on MyTax portal "
						f"(mytax.hasil.gov.my) to comply with the 30-day advance filing rule. "
						f"Failure to obtain SPC exposes the employer to liability for unpaid tax "
						f"under Income Tax Act 1967 Section 83(3)."
					),
				}
			).insert(ignore_permissions=True)
		except Exception:
			pass  # Don't fail the scheduler if notification delivery fails


def block_salary_slip_if_spc_pending(doc, method):
	"""Block Salary Slip before_submit if employee has cessation date but SPC not cleared.

	Per Income Tax Act 1967 Section 83(3), the employer must withhold the final
	payment until the Surat Penyelesaian Cukai (tax clearance letter) is received.

	Called on Salary Slip before_submit.
	"""
	employee = doc.get("employee")
	if not employee:
		return

	emp_data = frappe.db.get_value(
		"Employee",
		employee,
		["custom_cessation_date", "custom_spc_status"],
		as_dict=True,
	)

	if not emp_data or not emp_data.get("custom_cessation_date"):
		return

	spc_status = emp_data.get("custom_spc_status") or "Pending"

	if spc_status not in ("Cleared", "Not Required"):
		frappe.throw(
			f"Cannot submit Salary Slip for <b>{doc.get('employee_name')}</b>.<br><br>"
			f"Employee has cessation date <b>{emp_data['custom_cessation_date']}</b> "
			f"and SPC Status is <b>{spc_status}</b>.<br><br>"
			f"Per Income Tax Act 1967 Section 83(3), the employer must withhold final "
			f"salary until the Surat Penyelesaian Cukai (SPC / tax clearance letter) "
			f"is obtained via e-SPC on MyTax.<br><br>"
			f"Update <b>SPC Status</b> to <em>Cleared</em> (after SPC received) or "
			f"<em>Not Required</em> on the Employee record before submitting.",
			title="SPC Clearance Required",
		)
