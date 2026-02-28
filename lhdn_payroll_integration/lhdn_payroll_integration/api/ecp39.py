"""Whitelisted API for e-CP39 submission to LHDN MyTax / e-PCB Plus.

Called from the CP39 PCB Remittance report page via frappe.call().
"""
import frappe


@frappe.whitelist()
def submit_cp39(company_name, month, year):
	"""Submit CP39 PCB remittance data to LHDN e-PCB Plus API.

	Args:
		company_name (str): ERPNext Company name
		month (str|int): Month 01-12
		year (int): 4-digit year

	Returns:
		dict: {success, log_name, reference, message}
	"""
	# Only HR Manager or System Manager may trigger API submission
	if not (
		"HR Manager" in frappe.get_roles()
		or "System Manager" in frappe.get_roles()
	):
		frappe.throw("Only HR Manager or System Manager can submit CP39.", frappe.PermissionError)

	from lhdn_payroll_integration.lhdn_payroll_integration.services.ecp39_service import (
		submit_cp39_to_lhdn,
	)

	return submit_cp39_to_lhdn(company_name, month, int(year))
