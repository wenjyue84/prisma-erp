"""Stub for wage_payment_compliance — US-106 not yet implemented."""

NORMAL_WAGE_PAYMENT_DAYS = 7
OT_WAGE_PAYMENT_DAYS = 3
ALERT_DAYS_BEFORE = 2
STATUS_ON_TIME = "On Time"
STATUS_AT_RISK = "At Risk"
STATUS_OVERDUE = "Overdue"


def compute_payment_deadlines(payroll_date, has_overtime=False):
    raise NotImplementedError("US-106 not yet implemented")


def get_payroll_compliance_status(payroll_entry_name):
    raise NotImplementedError("US-106 not yet implemented")


def send_wage_payment_alerts():
    raise NotImplementedError("US-106 not yet implemented")
