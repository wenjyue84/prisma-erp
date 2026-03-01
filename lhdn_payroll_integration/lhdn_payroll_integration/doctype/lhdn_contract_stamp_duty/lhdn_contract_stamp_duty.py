"""LHDN Contract Stamp Duty DocType controller.

Auto-sets stamp_duty_exempt flag based on gross_monthly_salary on save.
"""
from frappe.model.document import Document


class LHDNContractStampDuty(Document):
    def before_save(self):
        from lhdn_payroll_integration.lhdn_payroll_integration.services.stamp_duty_service import (
            is_stamp_duty_exempt,
        )
        salary = self.gross_monthly_salary or 0
        self.stamp_duty_exempt = 1 if is_stamp_duty_exempt(salary) else 0
