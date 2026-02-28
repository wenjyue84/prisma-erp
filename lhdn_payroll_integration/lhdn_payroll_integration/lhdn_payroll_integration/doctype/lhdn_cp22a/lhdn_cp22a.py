import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


class LHDNCP22A(Document):
	def validate(self):
		self.set_age_at_cessation()
		self.calculate_termination_benefits()

	def set_age_at_cessation(self):
		if self.date_of_birth and self.cessation_date:
			dob = getdate(self.date_of_birth)
			cessation = getdate(self.cessation_date)
			age = cessation.year - dob.year
			if (cessation.month, cessation.day) < (dob.month, dob.day):
				age -= 1
			self.age_at_cessation = age

	def calculate_termination_benefits(self):
		"""Auto-populate termination benefit fields using Regulations 1980 calculator."""
		if not (self.employee and self.cessation_date):
			return

		try:
			employee_doc = frappe.get_doc("Employee", self.employee)
		except Exception:
			return

		from lhdn_payroll_integration.utils.employment_compliance import calculate_termination_benefits

		result = calculate_termination_benefits(employee_doc, self.cessation_date)

		self.years_of_service = round(result["years_of_service"], 2)
		self.statutory_minimum_termination_pay = result["statutory_minimum"]

		# Set underpayment warning if actual pay is below statutory minimum
		actual = float(self.actual_termination_pay or 0)
		statutory_min = result["statutory_minimum"]

		if actual > 0 and statutory_min > 0 and actual < statutory_min:
			self.underpayment_warning = (
				f"Actual termination pay (RM{actual:,.2f}) is below the statutory minimum "
				f"of RM{statutory_min:,.2f} calculated under Employment (Termination and "
				f"Lay-Off Benefits) Regulations 1980 ({result['rate_days']} days/year × "
				f"{self.years_of_service:.2f} years). Shortfall: RM{statutory_min - actual:,.2f}."
			)
		else:
			self.underpayment_warning = ""
