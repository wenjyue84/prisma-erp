"""
PDPA 2024 Amendment Payroll Data Protection Compliance Service.

Provides:
  - Salary Slip access audit logging (view, print, email)
  - Employee payroll data export for Data Subject Requests
  - Salary Slip retention enforcement (flag slips older than configured period)
"""
import frappe
from frappe.utils import now_datetime, add_years, today, date_diff


# ---------------------------------------------------------------------------
# Audit Logging
# ---------------------------------------------------------------------------

def _create_access_log(event_type, doc_type, doc_name, employee=None):
	"""Insert a Payroll Data Access Log entry. Silently swallows errors to
	avoid blocking normal Frappe operations."""
	try:
		log = frappe.get_doc({
			"doctype": "Payroll Data Access Log",
			"event_type": event_type,
			"document_type": doc_type,
			"document_name": doc_name,
			"employee": employee,
			"user": frappe.session.user or "Guest",
			"timestamp": now_datetime(),
			"data_categories_accessed": "Salary, Bank Account, NRIC, EPF Number, SOCSO Number, Tax File Number",
			"ip_address": frappe.local.request_ip if getattr(frappe.local, "request_ip", None) else "",
		})
		log.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "PDPA Access Log Creation Failed")


def log_salary_slip_view(doc, method=None):
	"""Hook: Salary Slip after_load — log a View access event."""
	if not getattr(doc, "employee", None):
		return
	_create_access_log("View", "Salary Slip", doc.name, doc.employee)


def log_salary_slip_print(doc, method=None):
	"""Hook: Salary Slip before_print — log a Print access event."""
	if not getattr(doc, "employee", None):
		return
	_create_access_log("Print", "Salary Slip", doc.name, doc.employee)


def log_salary_slip_email(doc, method=None):
	"""Hook: Salary Slip before_send_email — log an Email access event."""
	if not getattr(doc, "employee", None):
		return
	_create_access_log("Email", "Salary Slip", doc.name, doc.employee)


# ---------------------------------------------------------------------------
# Data Subject Request — employee payroll data export
# ---------------------------------------------------------------------------

def export_employee_payroll_data(employee, company=None):
	"""Return a dict of all payroll-related data for an employee.

	Called by HR Manager to fulfil a PDPA data portability request.
	"""
	if not frappe.db.exists("Employee", employee):
		frappe.throw(f"Employee {employee!r} not found.")

	emp_doc = frappe.get_doc("Employee", employee)
	filters = {"employee": employee}
	if company:
		filters["company"] = company

	salary_slips = frappe.get_all(
		"Salary Slip",
		filters=filters,
		fields=["name", "posting_date", "gross_pay", "net_pay", "total_deduction", "company"],
		order_by="posting_date desc",
	)

	consent_records = frappe.get_all(
		"Employee Payroll Consent",
		filters={"employee": employee},
		fields=["consent_version", "consent_date", "status", "data_categories", "consent_withdrawn_date"],
	)

	access_logs = frappe.get_all(
		"Payroll Data Access Log",
		filters={"employee": employee},
		fields=["event_type", "document_name", "user", "timestamp"],
		order_by="timestamp desc",
		limit=200,
	)

	def _to_str(v):
		"""Convert non-JSON-serializable values to strings."""
		if v is None or isinstance(v, (str, int, float, bool)):
			return v
		return str(v)

	def _row_to_dict(row):
		return {k: _to_str(v) for k, v in dict(row).items()}

	return {
		"employee": employee,
		"employee_name": emp_doc.employee_name,
		"company": emp_doc.company,
		"export_generated_at": str(now_datetime()),
		"salary_slips": [_row_to_dict(s) for s in salary_slips],
		"consent_records": [_row_to_dict(c) for c in consent_records],
		"access_log_summary": [_row_to_dict(a) for a in access_logs],
	}


# ---------------------------------------------------------------------------
# Retention Enforcement
# ---------------------------------------------------------------------------

def flag_old_salary_slips(company=None, retention_years=7):
	"""Return a list of Salary Slips older than `retention_years` that may
	be archived. Does NOT delete anything — flags for HR review only."""
	cutoff_date = add_years(today(), -retention_years)

	filters = {"posting_date": ["<", cutoff_date], "docstatus": 1}
	if company:
		filters["company"] = company

	old_slips = frappe.get_all(
		"Salary Slip",
		filters=filters,
		fields=["name", "employee", "posting_date", "company", "net_pay"],
		order_by="posting_date asc",
		limit=1000,
	)
	return {
		"retention_years": retention_years,
		"cutoff_date": cutoff_date,
		"count": len(old_slips),
		"salary_slips": [dict(s) for s in old_slips],
	}
