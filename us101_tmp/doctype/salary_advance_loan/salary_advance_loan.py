"""Salary Advance Loan DocType controller (US-101).

Employment Act 1955 S.22/24 compliance:
- S.22: Employer may advance wages interest-free.
- S.24(2): Total deductions cannot exceed 50% of wages earned in that period.
"""
import frappe
from frappe.model.document import Document
from frappe.utils import add_months, getdate, nowdate
import math


class SalaryAdvanceLoan(Document):

    def before_save(self):
        """Recompute outstanding_balance and projected_clearance_date on save."""
        if self.outstanding_balance is None:
            self.outstanding_balance = self.amount or 0.0
        self._update_projected_clearance_date()

    def _update_projected_clearance_date(self):
        """Estimate clearance date based on outstanding balance and monthly repayment."""
        if not self.repayment_amount_per_period or self.repayment_amount_per_period <= 0:
            self.projected_clearance_date = None
            return
        if not self.outstanding_balance or self.outstanding_balance <= 0:
            self.projected_clearance_date = nowdate()
            return
        months_remaining = math.ceil(
            float(self.outstanding_balance) / float(self.repayment_amount_per_period)
        )
        self.projected_clearance_date = add_months(nowdate(), months_remaining)

    def apply_repayment(self, actual_deducted, salary_slip_name, period_label, deduction_date=None):
        """Record a repayment entry and update outstanding balance.

        Called by salary_advance_service after deduction is applied to Salary Slip.

        Args:
            actual_deducted (float): Amount actually deducted (may be less than scheduled
                                     due to 50% cap).
            salary_slip_name (str): Name of the linked Salary Slip.
            period_label (str): Human-readable period, e.g. "Jan 2025".
            deduction_date (str|None): Date of deduction (defaults to today).
        """
        new_balance = max(0.0, float(self.outstanding_balance or 0) - float(actual_deducted))
        self.outstanding_balance = new_balance

        self.append("repayment_history", {
            "salary_slip": salary_slip_name,
            "period": period_label,
            "amount_deducted": actual_deducted,
            "balance_after": new_balance,
            "deduction_date": deduction_date or nowdate(),
        })

        if new_balance <= 0:
            self.status = "Fully Repaid"

        self._update_projected_clearance_date()
        self.save(ignore_permissions=True)
