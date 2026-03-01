import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class EmployeePayrollConsent(Document):
	def validate(self):
		if self.consent_withdrawn_date and self.status != "Withdrawn":
			self.status = "Withdrawn"
		if not self.consent_withdrawn_date and self.status == "Withdrawn":
			self.consent_withdrawn_date = now_datetime()
