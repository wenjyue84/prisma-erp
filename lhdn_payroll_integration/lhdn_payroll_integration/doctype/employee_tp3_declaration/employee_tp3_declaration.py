# Copyright (c) 2026, Prisma Technology and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmployeeTP3Declaration(Document):
	"""Borang TP3 — Prior Employer Year-to-Date Declaration for New Hires.

	When an employee joins mid-year having worked for a previous employer,
	the new employer must account for prior income and PCB already deducted
	to correctly compute the remaining PCB obligation for the year.

	Regulatory basis: LHDN Borang TP3 (prior employment income declaration).
	"""

	def validate(self):
		if self.joining_month is not None:
			if not (1 <= int(self.joining_month) <= 12):
				frappe.throw("Joining Month must be between 1 (January) and 12 (December).")

		if self.prior_gross_income is not None and float(self.prior_gross_income) < 0:
			frappe.throw("Prior Gross Income cannot be negative.")

		if self.prior_pcb_deducted is not None and float(self.prior_pcb_deducted) < 0:
			frappe.throw("Prior PCB Deducted cannot be negative.")

		if self.prior_epf_deducted is not None and float(self.prior_epf_deducted) < 0:
			frappe.throw("Prior EPF Deducted cannot be negative.")
