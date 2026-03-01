# Copyright (c) 2026, Prisma Technology and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeOutgoingTP3(Document):
	"""Borang TP3 (Outgoing) — YTD Income Statement for Departing Employees.

	When an employee leaves mid-year, the employer must generate a TP3
	document containing the full YTD earnings, statutory deductions, and
	PCB paid so the employee can hand it to their next employer.

	Regulatory basis: LHDN Borang TP3 (employer-to-employee document only;
	NOT submitted to LHDN — retained for 7 years per LHDN audit requirements).

	US-143: Auto-Generate TP3 YTD Income Statement for Departing Employees.
	"""

	def validate(self):
		if self.tax_year and (int(self.tax_year) < 2000 or int(self.tax_year) > 2100):
			frappe.throw("Tax Year must be a valid 4-digit year between 2000 and 2100.")

		if self.ytd_pcb is not None and float(self.ytd_pcb) < 0:
			frappe.throw("YTD PCB Deducted cannot be negative.")

		if self.ytd_epf_employee is not None and float(self.ytd_epf_employee) < 0:
			frappe.throw("YTD EPF Employee Contribution cannot be negative.")
