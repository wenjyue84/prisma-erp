import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, add_days, time_diff_in_hours


class PDPABreachIncident(Document):
	def validate(self):
		self._compute_hours_since_discovery()
		self._compute_commissioner_deadline_status()
		self._compute_employee_notification_deadline()
		self._alert_if_overdue()

	def _compute_hours_since_discovery(self):
		if self.discovery_datetime:
			self.hours_since_discovery = round(
				time_diff_in_hours(now_datetime(), self.discovery_datetime), 2
			)

	def _compute_commissioner_deadline_status(self):
		if not self.discovery_datetime:
			return
		hours = self.hours_since_discovery or 0
		if self.commissioner_notified_datetime:
			notified_hours = round(
				time_diff_in_hours(self.commissioner_notified_datetime, self.discovery_datetime), 2
			)
			self.commissioner_deadline_status = (
				f"Notified to Commissioner after {notified_hours:.1f} hours"
			)
		elif hours >= 72:
			overdue_by = hours - 72
			self.commissioner_deadline_status = (
				f"OVERDUE — Commissioner not notified. {overdue_by:.1f} hours past 72-hour deadline."
			)
		else:
			remaining = 72 - hours
			self.commissioner_deadline_status = (
				f"{remaining:.1f} hours remaining until 72-hour Commissioner notification deadline."
			)

	def _compute_employee_notification_deadline(self):
		if self.commissioner_notified_datetime:
			import frappe.utils
			deadline = frappe.utils.add_to_date(
				self.commissioner_notified_datetime, days=7
			)
			self.employee_notification_deadline = deadline

	def _alert_if_overdue(self):
		if not self.discovery_datetime:
			return
		hours = self.hours_since_discovery or 0
		if hours >= 72 and not self.commissioner_notified_datetime:
			frappe.msgprint(
				f"<b>CRITICAL: 72-Hour Commissioner Notification Deadline Exceeded</b><br>"
				f"This breach was discovered {hours:.1f} hours ago. "
				f"The PDPA Commissioner must be notified within 72 hours of discovery awareness. "
				f"Please complete the notification immediately and record the datetime above.",
				title="PDPA Breach — Commissioner Notification Overdue",
				indicator="red",
			)
		elif hours >= 48 and not self.commissioner_notified_datetime:
			frappe.msgprint(
				f"Warning: {72 - hours:.1f} hours remaining to notify the PDPA Commissioner. "
				f"Ensure notification is completed before the 72-hour deadline.",
				title="PDPA Breach — Commissioner Notification Due Soon",
				indicator="orange",
			)

	def get_commissioner_notification_letter(self):
		"""Generate pre-filled Commissioner Notification Letter content."""
		dpo_name = "N/A"
		dpo_email = "N/A"
		dpo_registry = frappe.db.get_value(
			"PDPA DPO Registry",
			{"company": self.company},
			["dpo_name", "dpo_email"],
			as_dict=1,
		)
		if dpo_registry:
			dpo_name = dpo_registry.get("dpo_name") or "N/A"
			dpo_email = dpo_registry.get("dpo_email") or "N/A"
		letter = (
			f"TO: Personal Data Protection Commissioner\n"
			f"RE: Data Breach Notification\n\n"
			f"Company: {self.company}\n"
			f"Data Protection Officer: {dpo_name} ({dpo_email})\n\n"
			f"We hereby notify you of a personal data breach as required under the "
			f"Personal Data Protection (Amendment) Act 2024.\n\n"
			f"Incident Reference: {self.name}\n"
			f"Discovery Date/Time: {self.discovery_datetime}\n"
			f"Breach Type: {self.breach_type}\n"
			f"Number of Affected Employee Records: {self.affected_records_count}\n"
			f"Data Categories Affected: {self.data_categories_affected}\n\n"
			f"Risk Assessment:\n{self.risk_assessment}\n\n"
			f"Remediation actions are being taken to prevent recurrence. "
			f"We will provide further updates as the investigation progresses.\n"
		)
		return letter

	def get_employee_breach_notification_email(self):
		"""Generate pre-filled Employee Breach Notification email template."""
		email_body = (
			f"Dear Valued Employee,\n\n"
			f"We are writing to inform you that {self.company} has experienced a payroll "
			f"data security incident that may have involved your personal information.\n\n"
			f"Incident Details:\n"
			f"- Date Discovered: {self.discovery_datetime}\n"
			f"- Type of Breach: {self.breach_type}\n"
			f"- Data Potentially Affected: {self.data_categories_affected}\n\n"
			f"What We Are Doing:\n"
			f"We have notified the Personal Data Protection Commissioner as required by law "
			f"and are taking immediate steps to contain this incident and prevent recurrence.\n\n"
			f"What You Can Do:\n"
			f"- Monitor your bank accounts for any unusual activity\n"
			f"- Be alert to phishing emails or calls requesting personal information\n"
			f"- Contact HR immediately if you notice any suspicious activity\n\n"
			f"We sincerely apologise for any concern this may cause and are committed to "
			f"protecting your personal data.\n\n"
			f"HR Department\n{self.company}\n"
		)
		return email_body
