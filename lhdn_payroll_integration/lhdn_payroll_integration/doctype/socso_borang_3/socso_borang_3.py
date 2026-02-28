import frappe
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, today


class SOCSOBorang3(Document):
	def validate(self):
		self.set_filing_deadline()
		self.set_days_until_deadline()
		self.warn_if_overdue()

	def set_filing_deadline(self):
		if self.date_of_employment:
			self.filing_deadline = add_days(self.date_of_employment, 30)

	def set_days_until_deadline(self):
		if self.filing_deadline:
			self.days_until_deadline = date_diff(self.filing_deadline, today())

	def warn_if_overdue(self):
		if self.filing_deadline and self.status == "Pending":
			days = date_diff(self.filing_deadline, today())
			if days < 0:
				self.status = "Overdue"
				frappe.msgprint(
					f"SOCSO Borang 3 filing deadline has passed by {abs(days)} day(s). "
					f"Please submit to PERKESO immediately (SOCSO Act 1969 S.19).",
					title="Overdue SOCSO Borang 3 Filing",
					indicator="red",
				)
			elif days <= 7:
				frappe.msgprint(
					f"SOCSO Borang 3 filing deadline is in {days} day(s). "
					f"Please submit to PERKESO soon.",
					title="SOCSO Borang 3 Filing Deadline Approaching",
					indicator="orange",
				)
