"""LHDN Contract Stamp Duty DocType controller.

Auto-sets stamp_duty_exempt flag based on gross_monthly_salary and contract_signing_date.

US-190: Date-sensitive threshold — contracts signed before 1 Jan 2026 use old RM300
threshold; contracts signed on/after 1 Jan 2026 use new RM3,000 threshold.
"""
from frappe.model.document import Document


class LHDNContractStampDuty(Document):
    def before_save(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service import (
            is_stamp_duty_exempt,
        )
        salary = self.gross_monthly_salary or 0
        contract_date = self.contract_signing_date or None
        self.stamp_duty_exempt = 1 if is_stamp_duty_exempt(salary, contract_date) else 0
