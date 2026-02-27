import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


class LHDNCP22A(Document):
	def validate(self):
		self.set_age_at_cessation()

	def set_age_at_cessation(self):
		if self.date_of_birth and self.cessation_date:
			dob = getdate(self.date_of_birth)
			cessation = getdate(self.cessation_date)
			age = cessation.year - dob.year
			if (cessation.month, cessation.day) < (dob.month, dob.day):
				age -= 1
			self.age_at_cessation = age
