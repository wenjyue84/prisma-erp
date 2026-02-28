import frappe
from frappe.utils import add_days, date_diff, today


def handle_new_employee_socso(doc, method):
	"""Auto-create SOCSO Borang 3 when a new eligible employee is inserted.

	Eligibility (SOCSO Act 1969 S.19):
	- Not a foreign worker (custom_is_foreign_worker = 0/falsy)
	- Employment type is Permanent or Contract

	PERKESO requires notification within 30 days of employment commencement.
	Foreign workers are ineligible for Category II (Invalidity Pension).
	"""
	# Skip foreign workers — they are not eligible for Category II SOCSO
	if doc.get("custom_is_foreign_worker"):
		return

	# Only Permanent and Contract employees require SOCSO registration
	employment_type = doc.get("custom_employment_type") or ""
	if employment_type not in ("Permanent", "Contract"):
		return

	if not doc.date_of_joining:
		return

	# Avoid duplicate
	if frappe.db.exists("SOCSO Borang 3", {"employee": doc.name}):
		return

	borang3 = frappe.new_doc("SOCSO Borang 3")
	borang3.employee = doc.name
	borang3.date_of_employment = doc.date_of_joining
	borang3.filing_deadline = add_days(doc.date_of_joining, 30)
	borang3.socso_scheme_category = "Category II"
	borang3.status = "Pending"
	borang3.insert(ignore_permissions=True)

	frappe.msgprint(
		f"SOCSO Borang 3 record <b>{borang3.name}</b> created for {doc.employee_name}. "
		f"Must be submitted to PERKESO by {borang3.filing_deadline}.",
		title="SOCSO Borang 3 Created",
		indicator="blue",
	)


def check_overdue_socso_borang3():
	"""Check for overdue SOCSO Borang 3 filings and update status.

	Called by daily scheduler to flag records that have passed their
	30-day filing deadline.
	"""
	overdue = frappe.get_all(
		"SOCSO Borang 3",
		filters={"status": "Pending", "filing_deadline": ["<", today()]},
		fields=["name", "employee_name", "filing_deadline"],
	)
	for record in overdue:
		frappe.db.set_value("SOCSO Borang 3", record["name"], "status", "Overdue")
		days_overdue = abs(date_diff(record["filing_deadline"], today()))
		frappe.log_error(
			title="Overdue SOCSO Borang 3 Filing",
			message=(
				f"SOCSO Borang 3 {record['name']} for {record['employee_name']} "
				f"is {days_overdue} day(s) overdue. Failure to register is a criminal "
				f"offence under SOCSO Act 1969."
			),
		)
	if overdue:
		frappe.db.commit()


def handle_employee_termination_socso(doc, method):
	"""Auto-create SOCSO Borang 4 when an eligible employee's status is set to Left.

	SOCSO Act 1969 Section 19 requires employers to notify PERKESO within 30 days
	of employee termination via Borang 4.

	Eligibility:
	- Employee status is 'Left'
	- Not a foreign worker (custom_is_foreign_worker = 0/falsy)
	- Employment type is Permanent or Contract
	"""
	# Only trigger when employee is marked as Left
	if doc.status != "Left":
		return

	# Skip foreign workers
	if doc.get("custom_is_foreign_worker"):
		return

	# Only Permanent and Contract employees
	employment_type = doc.get("custom_employment_type") or ""
	if employment_type not in ("Permanent", "Contract"):
		return

	# Use date_of_leaving if set, otherwise today
	termination_date = doc.date_of_leaving or today()

	# Avoid duplicate
	if frappe.db.exists("SOCSO Borang 4", {"employee": doc.name}):
		return

	borang4 = frappe.new_doc("SOCSO Borang 4")
	borang4.employee = doc.name
	borang4.date_of_termination = termination_date
	borang4.filing_deadline = add_days(termination_date, 30)
	borang4.status = "Pending"
	borang4.insert(ignore_permissions=True)

	frappe.msgprint(
		f"SOCSO Borang 4 record <b>{borang4.name}</b> created for {doc.employee_name}. "
		f"Must be submitted to PERKESO by {borang4.filing_deadline}.",
		title="SOCSO Borang 4 Created",
		indicator="blue",
	)


def check_overdue_socso_borang4():
	"""Check for overdue SOCSO Borang 4 filings and update status.

	Called by daily scheduler to flag termination notifications that have
	passed their 30-day filing deadline.
	"""
	overdue = frappe.get_all(
		"SOCSO Borang 4",
		filters={"status": "Pending", "filing_deadline": ["<", today()]},
		fields=["name", "employee_name", "filing_deadline"],
	)
	for record in overdue:
		frappe.db.set_value("SOCSO Borang 4", record["name"], "status", "Overdue")
		days_overdue = abs(date_diff(record["filing_deadline"], today()))
		frappe.log_error(
			title="Overdue SOCSO Borang 4 Filing",
			message=(
				f"SOCSO Borang 4 {record['name']} for {record['employee_name']} "
				f"is {days_overdue} day(s) overdue. Failure to notify PERKESO within 30 days "
				f"of employee termination is an offence under SOCSO Act 1969 S.19."
			),
		)
	if overdue:
		frappe.db.commit()
