# Copyright (c) 2026, Prisma Technology and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from lhdn_payroll_integration.lhdn_payroll_integration.services.ep_internship_service import (
    validate_intern_stipend,
)


class InternshipPlacement(Document):
    def validate(self):
        self._validate_stipend()
        self._validate_dates()

    def _validate_stipend(self):
        if self.qualification_level and self.monthly_stipend is not None:
            result = validate_intern_stipend(self.qualification_level, self.monthly_stipend)
            if not result["valid"]:
                frappe.throw(result["message"])

    def _validate_dates(self):
        if self.start_date and self.end_date:
            from frappe.utils import date_diff
            days = date_diff(self.end_date, self.start_date)
            min_days = 10 * 7  # 10 weeks
            if days < min_days:
                frappe.throw(
                    f"Internship duration must be at least 10 weeks "
                    f"(70 days). Current: {days} days."
                )
