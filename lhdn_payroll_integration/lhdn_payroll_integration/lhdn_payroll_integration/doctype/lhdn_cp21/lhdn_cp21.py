import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, today


class LHDNCP21(Document):
	def validate(self):
		self.set_days_notice()
		self.warn_if_late_filing()

	def set_days_notice(self):
		if self.last_working_date:
			self.days_notice = date_diff(self.last_working_date, today())

	def warn_if_late_filing(self):
		if self.last_working_date:
			days = date_diff(self.last_working_date, today())
			if days < 30:
				frappe.msgprint(
					f"Warning: CP21 should be filed at least 30 days before the employee's "
					f"last working date. Only {days} day(s) remaining.",
					title="Late CP21 Filing Alert",
					indicator="orange",
				)
