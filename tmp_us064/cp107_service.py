"""CP107 service — Foreign Employee Tax Clearance Workflow.

When a non-citizen employee (custom_is_foreign_worker=1) has their
status set to Left, employer must:
  1. Withhold the final month remuneration.
  2. Apply for Tax Clearance Letter via CP107.
  3. Wait up to 30 working days for LHDN response.
  4. Release payment only after Clearance Received.

ITA Section 107A(4): employer becomes jointly liable if final payment
released without clearance.
"""
import frappe
from frappe.utils import getdate, today


def handle_foreign_employee_left(doc, method):
	"""Auto-create LHDN CP107 when a foreign worker status is set to Left.

	Triggered by Employee on_update hook.
	"""
	if doc.status != "Left":
		return

	# Only applies to foreign workers
	if not doc.get("custom_is_foreign_worker"):
		return

	# Avoid duplicate
	if frappe.db.exists("LHDN CP107", {"employee": doc.name, "status": ["in", ["Draft", "Submitted to LHDN"]]}):
		return

	last_working_date = doc.relieving_date or today()

	cp107 = frappe.new_doc("LHDN CP107")
	cp107.employee = doc.name
	cp107.last_working_date = last_working_date
	cp107.status = "Draft"
	cp107.insert(ignore_permissions=True)

	frappe.msgprint(
		f"LHDN CP107 Tax Clearance record <b>{cp107.name}</b> created for foreign employee "
		f"{doc.employee_name}. Final month salary must be withheld until clearance received.",
		title="CP107 Tax Clearance Required",
		indicator="orange",
	)


def get_open_cp107_for_employee(employee):
	"""Return the name of an open (Draft or Submitted) CP107 for the employee, or None."""
	return frappe.db.get_value(
		"LHDN CP107",
		{"employee": employee, "status": ["in", ["Draft", "Submitted to LHDN"]]},
		"name",
	)


def check_salary_slip_cp107_warning(doc, method):
	"""Emit a warning on a Salary Slip if the employee has an open CP107 record.

	Triggered by Salary Slip before_save / validate hook.
	Warns payroll staff that this is the final month salary for a foreign employee
	with a pending Tax Clearance — payment must not be released until clearance received.
	"""
	if not doc.employee:
		return

	is_foreign = frappe.db.get_value("Employee", doc.employee, "custom_is_foreign_worker")
	if not is_foreign:
		return

	open_cp107 = get_open_cp107_for_employee(doc.employee)
	if not open_cp107:
		return

	frappe.msgprint(
		f"⚠️ <b>Tax Clearance Warning:</b> Employee {doc.employee_name} has an open CP107 "
		f"Tax Clearance application (<b>{open_cp107}</b>). "
		f"The final month salary must be withheld until LHDN issues a Tax Clearance Letter "
		f"(ITA Section 107A(4)).",
		title="Foreign Employee Tax Clearance Pending",
		indicator="orange",
		alert=True,
	)
