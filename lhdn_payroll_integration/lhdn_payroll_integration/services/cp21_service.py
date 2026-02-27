import frappe
from frappe.utils import today


def handle_employee_left(doc, method):
	"""Auto-create LHDN CP21 when employee is set to Left and is a foreign worker.

	CP21 must be filed with LHDN at least 30 days before the employee leaves Malaysia
	or ceases employment. This hook fires on Employee on_update.
	"""
	if doc.status != "Left":
		return

	if not doc.get("custom_is_foreign_worker"):
		return

	# Avoid duplicate CP21 for the same employee
	if frappe.db.exists("LHDN CP21", {"employee": doc.name}):
		return

	cp21 = frappe.new_doc("LHDN CP21")
	cp21.employee = doc.name
	cp21.last_working_date = doc.relieving_date or today()
	cp21.reason = "Departure from Malaysia"
	cp21.insert(ignore_permissions=True)

	frappe.msgprint(
		f"LHDN CP21 record <b>{cp21.name}</b> created automatically for {doc.employee_name}.",
		title="CP21 Created",
		indicator="blue",
	)
