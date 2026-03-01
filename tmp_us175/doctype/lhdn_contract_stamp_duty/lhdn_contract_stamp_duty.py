"""LHDN Contract Stamp Duty — DocType controller.

Tracks employment contract stamp duty compliance under the Stamp Duty
Self-Assessment System (SAS) effective 1 January 2026.

Fixed stamp duty: RM10 per contract (Item 4, First Schedule, Stamp Act 1949).
Exemption threshold: RM3,000/month gross salary (Finance Bill 2025, eff. 1 Jan 2026).
30-day stamping window via e-Duti Setem portal on MyTax.
"""

from datetime import date, timedelta

import frappe
from frappe.model.document import Document

EXEMPTION_THRESHOLD = 3000.0


class LHDNContractStampDuty(Document):
    def validate(self):
        self._auto_set_exemption()
        self._compute_deadline()
        self._compute_days_overdue()
        self._set_compliance_status()

    def _auto_set_exemption(self):
        gross = float(self.gross_monthly_salary or 0)
        self.stamp_duty_exempt = 1 if gross <= EXEMPTION_THRESHOLD and gross > 0 else 0

    def _compute_deadline(self):
        if self.contract_signing_date:
            signing = self.contract_signing_date
            if isinstance(signing, str):
                from datetime import datetime
                signing = datetime.strptime(signing, "%Y-%m-%d").date()
            self.stamping_deadline = signing + timedelta(days=30)

    def _compute_days_overdue(self):
        if not self.stamping_deadline:
            return
        deadline = self.stamping_deadline
        if isinstance(deadline, str):
            from datetime import datetime
            deadline = datetime.strptime(deadline, "%Y-%m-%d").date()
        self.days_overdue = (date.today() - deadline).days

    def _set_compliance_status(self):
        if self.stamp_duty_exempt:
            self.compliance_status = "Exempt"
            return

        if self.eduti_stamp_reference and self.contract_stamping_date:
            self.compliance_status = "Stamped"
            return

        days = self.days_overdue or 0
        if days < 0:
            self.compliance_status = "Pending (within 30 days)"
        elif days == 0:
            self.compliance_status = "Due Today"
        elif days <= 60:
            self.compliance_status = "Overdue — RM50 penalty risk"
        else:
            self.compliance_status = "Overdue — RM100 penalty risk"
