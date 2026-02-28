import frappe
from frappe.utils import add_days, date_diff, getdate, today


def handle_employee_after_insert(doc, method):
	"""Auto-create LHDN CP22 when a new employee is created with custom_requires_self_billed_invoice = 1.

	CP22 must be filed within 30 days of date_of_joining per LHDN requirements.
	"""
	if not doc.get("custom_requires_self_billed_invoice"):
		return

	if not doc.date_of_joining:
		return

	# Avoid duplicate
	if frappe.db.exists("LHDN CP22", {"employee": doc.name}):
		return

	cp22 = frappe.new_doc("LHDN CP22")
	cp22.employee = doc.name
	cp22.date_of_joining = doc.date_of_joining
	cp22.date_of_birth = doc.date_of_birth
	cp22.filing_deadline = add_days(doc.date_of_joining, 30)
	cp22.status = "Pending"
	cp22.insert(ignore_permissions=True)

	frappe.msgprint(
		f"LHDN CP22 record <b>{cp22.name}</b> created for {doc.employee_name}. "
		f"Must be filed by {cp22.filing_deadline}.",
		title="CP22 Created",
		indicator="blue",
	)

	# TP3 reminder: if employee joins in February or later they may have prior employer income
	_maybe_remind_tp3_collection(doc)


def handle_employee_status_change(doc, method):
	"""Auto-create LHDN CP22A when employee age >=55 is set to Left.

	CP22A covers retirement, resignation, or cessation for employees
	aged 55 and above.
	"""
	if doc.status != "Left":
		return

	if not doc.date_of_birth:
		return

	# Calculate age at cessation
	cessation_date = getdate(doc.relieving_date) if doc.relieving_date else getdate(today())
	dob = getdate(doc.date_of_birth)
	age = cessation_date.year - dob.year
	if (cessation_date.month, cessation_date.day) < (dob.month, dob.day):
		age -= 1

	if age < 55:
		return

	# Avoid duplicate
	if frappe.db.exists("LHDN CP22A", {"employee": doc.name}):
		return

	cp22a = frappe.new_doc("LHDN CP22A")
	cp22a.employee = doc.name
	cp22a.date_of_birth = doc.date_of_birth
	cp22a.cessation_date = str(cessation_date)
	cp22a.reason = "Retirement"
	cp22a.status = "Pending"
	cp22a.insert(ignore_permissions=True)

	frappe.msgprint(
		f"LHDN CP22A record <b>{cp22a.name}</b> created for {doc.employee_name} "
		f"(age {age} at cessation).",
		title="CP22A Created",
		indicator="blue",
	)


def _maybe_remind_tp3_collection(doc):
	"""Display TP3 collection reminder when an employee joins mid-year.

	If an employee joins in February (month 2) or later, they may have received
	income and had PCB deducted by a previous employer in the same calendar year.
	The new employer must collect Borang TP3 to ensure correct PCB computation.

	Args:
		doc: Employee document being inserted.
	"""
	if not doc.date_of_joining:
		return

	joining_date = getdate(doc.date_of_joining)
	if joining_date.month == 1:
		# January joiner — no prior employer income in this tax year
		return

	frappe.msgprint(
		f"<b>Action Required — Borang TP3 Collection</b><br/>"
		f"{doc.employee_name} joined in month {joining_date.month} ({joining_date.year}). "
		f"Please request and record the employee's prior employer YTD income and PCB details "
		f"via <b>Employee TP3 Declaration</b> to ensure accurate PCB deduction for the year.",
		title="TP3 Required",
		indicator="orange",
	)


def check_overdue_cp22():
	"""Check for overdue CP22 filings and update status.

	Called by scheduler or manually to flag CP22 records that have
	passed their 30-day filing deadline.
	"""
	overdue = frappe.get_all(
		"LHDN CP22",
		filters={"status": "Pending", "filing_deadline": ["<", today()]},
		fields=["name", "employee_name", "filing_deadline"],
	)
	for record in overdue:
		frappe.db.set_value("LHDN CP22", record["name"], "status", "Overdue")
		days_overdue = abs(date_diff(record["filing_deadline"], today()))
		frappe.log_error(
			title="Overdue CP22 Filing",
			message=f"CP22 {record['name']} for {record['employee_name']} is {days_overdue} day(s) overdue.",
		)
	if overdue:
		frappe.db.commit()
