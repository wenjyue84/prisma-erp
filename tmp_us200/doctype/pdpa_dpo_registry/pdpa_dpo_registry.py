import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, today, add_days


class PDPADPORegistry(Document):
	def validate(self):
		self._check_single_registry_per_company()
		self._compute_deadline_status()
		self._alert_if_overdue()

	def _check_single_registry_per_company(self):
		if self.company and self.is_new():
			existing = frappe.db.exists(
				"PDPA DPO Registry", {"company": self.company}
			)
			if existing:
				frappe.throw(
					f"A DPO Registry already exists for {self.company}. "
					f"Please update the existing record: <a href='/app/pdpa-dpo-registry/{existing}'>{existing}</a>",
					title="Duplicate DPO Registry",
				)

	def _compute_deadline_status(self):
		if not self.dpo_appointment_date:
			return
		if self.dpo_commissioner_registration_date:
			reg_days = date_diff(
				self.dpo_commissioner_registration_date, self.dpo_appointment_date
			)
			self.days_until_21day_deadline = 0
			self.registration_deadline_status = (
				f"Registered with Commissioner on day {reg_days} of 21-day deadline. "
				f"{'Compliant.' if reg_days <= 21 else 'LATE — exceeded 21-day deadline.'}"
			)
		else:
			days_elapsed = date_diff(today(), self.dpo_appointment_date)
			remaining = 21 - days_elapsed
			self.days_until_21day_deadline = max(0, remaining)
			if days_elapsed > 21:
				self.registration_deadline_status = (
					f"OVERDUE — {days_elapsed - 21} day(s) past 21-day Commissioner notification deadline."
				)
			else:
				self.registration_deadline_status = (
					f"{remaining} day(s) remaining to notify Commissioner of DPO appointment."
				)

	def _alert_if_overdue(self):
		if not self.dpo_appointment_date:
			return
		if self.dpo_commissioner_registration_date:
			return  # Already registered
		days_elapsed = date_diff(today(), self.dpo_appointment_date)
		if days_elapsed > 21:
			frappe.msgprint(
				f"<b>OVERDUE: DPO Commissioner Notification</b><br>"
				f"The DPO was appointed {days_elapsed} days ago. "
				f"The PDPA Commissioner must be notified within 21 days of appointment. "
				f"Please register immediately and record the date above.",
				title="PDPA DPO Registration Overdue",
				indicator="red",
			)
		elif days_elapsed >= 14:
			frappe.msgprint(
				f"Warning: Only {21 - days_elapsed} day(s) remaining to notify the PDPA Commissioner "
				f"of DPO appointment.",
				title="PDPA DPO Registration Deadline Approaching",
				indicator="orange",
			)
