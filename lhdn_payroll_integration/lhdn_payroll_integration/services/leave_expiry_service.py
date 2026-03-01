"""
Employment Act S.60A: Annual Leave Carry-Forward Cap and Cash-Out Service
US-206: EA S.60A Annual Leave Year-End Enforcement

EA S.60E Annual Leave Entitlements (minimum per Employment Act 1955):
  < 2 years: 8 days
  2-5 years: 12 days
  > 5 years: 16 days

Carry-forward cap defaults to 1× annual entitlement (employer may allow more by agreement).
Cash-out rate: (Monthly Basic Salary / 26) × leave days
EA 2022 Amendment: Employers cannot unilaterally forfeit unused leave without employee agreement.

Reference: Employment Act 1955 S.60A, S.60E; EA 2022 Amendment
"""

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.utils.data import now_datetime as nowdatetime  # alias for patch compatibility

EA_LEAVE_TYPE = "Annual Leave (EA)"
CARRY_FORWARD_DEFAULT_MULTIPLIER = 1  # 1× annual entitlement
WORKING_DAYS_PER_MONTH = 26  # Standard EA divisor for daily rate

# EA S.60E minimum annual leave entitlements
EA_ANNUAL_LEAVE_TIERS = {
    "< 2 years": 8,
    "2-5 years": 12,
    "> 5 years": 16,
}

# Decision options per S.60A(4) and EA 2022 Amendment
DECISION_CARRY_FORWARD = "Carry Forward"
DECISION_CASH_OUT = "Cash Out"
DECISION_MUTUAL_FORFEITURE = "Mutual Forfeiture Agreement"

VALID_DECISIONS = {DECISION_CARRY_FORWARD, DECISION_CASH_OUT, DECISION_MUTUAL_FORFEITURE}

EA_LEAVE_EXPIRY_NOTICE_DOCTYPE = "EA Leave Expiry Notice"


def get_ea_leave_entitlement(years_of_service: float) -> int:
    """Return EA minimum annual leave days based on years of service (S.60E)."""
    if years_of_service < 2:
        return EA_ANNUAL_LEAVE_TIERS["< 2 years"]
    elif years_of_service <= 5:
        return EA_ANNUAL_LEAVE_TIERS["2-5 years"]
    else:
        return EA_ANNUAL_LEAVE_TIERS["> 5 years"]


def get_carry_forward_cap(annual_entitlement: int, multiplier: int = CARRY_FORWARD_DEFAULT_MULTIPLIER) -> int:
    """Return maximum days that may be carried forward (default: 1× entitlement)."""
    return annual_entitlement * multiplier


def calculate_cash_out(monthly_basic: float, leave_days: float) -> float:
    """
    Calculate cash-out amount for unused annual leave.

    Rate: Monthly Basic Salary / 26 (working days) × leave_days
    Consistent with EA S.60A(3) termination pay formula.
    """
    if monthly_basic < 0:
        raise ValueError("monthly_basic must be >= 0")
    if leave_days < 0:
        raise ValueError("leave_days must be >= 0")
    daily_rate = monthly_basic / WORKING_DAYS_PER_MONTH
    return round(daily_rate * leave_days, 2)


def generate_leave_expiry_notices(year: int, employees: list = None) -> list:
    """
    Generate Leave Expiry Notice records for all employees at year-end.

    Returns list of notice dicts:
        {employee, leave_year, expiring_days, carry_forward_cap,
         cash_out_days, cash_out_amount, decision}

    Only employees with unused leave (> 0) get a notice.
    """
    if employees is None:
        employees = frappe.db.get_all(
            "Employee",
            filters={"status": "Active"},
            pluck="name",
        )

    notices = []
    for employee in employees:
        unused = _get_unused_annual_leave(employee, year)
        if unused <= 0:
            continue

        entitlement = _get_annual_entitlement(employee, year)
        cap = get_carry_forward_cap(entitlement)
        monthly_basic = _get_monthly_basic(employee)
        cash_out_days = max(0.0, unused - cap)
        cash_out_amount = calculate_cash_out(monthly_basic, cash_out_days)

        existing_decision = frappe.db.get_value(
            EA_LEAVE_EXPIRY_NOTICE_DOCTYPE,
            {"employee": employee, "leave_year": year},
            "decision",
        )

        notices.append({
            "employee": employee,
            "leave_year": year,
            "expiring_days": unused,
            "carry_forward_cap": cap,
            "cash_out_days": cash_out_days,
            "cash_out_amount": cash_out_amount,
            "decision": existing_decision or None,
        })

    return notices


def record_leave_decision(
    employee: str,
    year: int,
    decision: str,
    hr_manager: str,
    carry_forward_days: int = 0,
    cash_out_days: float = 0.0,
) -> str:
    """
    Record employee's leave decision and create/update audit entry.

    Returns the name of the created/updated EA Leave Expiry Notice.
    Raises frappe.ValidationError for invalid decision values.
    """
    if decision not in VALID_DECISIONS:
        frappe.throw(
            _(
                "Invalid leave decision '{0}'. Must be one of: {1}"
            ).format(decision, ", ".join(sorted(VALID_DECISIONS))),
            title=_("Invalid Decision"),
        )

    existing_name = frappe.db.get_value(
        EA_LEAVE_EXPIRY_NOTICE_DOCTYPE,
        {"employee": employee, "leave_year": year},
        "name",
    )

    if existing_name:
        doc = frappe.get_doc(EA_LEAVE_EXPIRY_NOTICE_DOCTYPE, existing_name)
    else:
        doc = frappe.new_doc(EA_LEAVE_EXPIRY_NOTICE_DOCTYPE)
        doc.employee = employee
        doc.leave_year = year

    doc.decision = decision
    doc.hr_manager = hr_manager
    doc.carry_forward_days = carry_forward_days
    doc.cash_out_days = cash_out_days
    doc.decision_timestamp = nowdatetime()
    doc.save(ignore_permissions=True)

    return doc.name


def validate_year_close_readiness(year: int, employees: list = None) -> list:
    """
    Return list of employees WITHOUT a recorded leave decision for the given year.

    Callers should block year close-off if the returned list is non-empty,
    ensuring compliance with EA 2022 Amendment (no unilateral forfeiture).
    """
    if employees is None:
        employees = frappe.db.get_all(
            "Employee",
            filters={"status": "Active"},
            pluck="name",
        )

    pending = []
    for employee in employees:
        unused = _get_unused_annual_leave(employee, year)
        if unused <= 0:
            continue  # No unused leave — no decision needed

        has_decision = frappe.db.exists(
            EA_LEAVE_EXPIRY_NOTICE_DOCTYPE,
            {"employee": employee, "leave_year": year, "decision": ["!=", ""]},
        )
        if not has_decision:
            pending.append(employee)

    return pending


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_unused_annual_leave(employee: str, year: int) -> float:
    """Query total unused (remaining) annual leave days for the employee in the given year."""
    allocated_result = frappe.db.get_value(
        "Leave Allocation",
        {
            "employee": employee,
            "leave_type": EA_LEAVE_TYPE,
            "from_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
            "docstatus": 1,
        },
        "new_leaves_allocated",
    )
    allocated = float(allocated_result or 0)

    used_result = frappe.db.get_value(
        "Leave Ledger Entry",
        {
            "employee": employee,
            "leave_type": EA_LEAVE_TYPE,
            "transaction_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
            "docstatus": 1,
        },
        "sum(leaves)",
        as_dict=False,
    )
    used = abs(float(used_result)) if used_result else 0.0

    return max(0.0, allocated - used)


def _get_annual_entitlement(employee: str, year: int) -> int:
    """Compute EA annual leave entitlement based on years of service at year start."""
    date_of_joining = frappe.db.get_value("Employee", employee, "date_of_joining")
    if not date_of_joining:
        return EA_ANNUAL_LEAVE_TIERS["> 5 years"]  # Assume long-service if unknown

    year_start = getdate(f"{year}-01-01")
    years = (year_start - getdate(date_of_joining)).days / 365.25
    return get_ea_leave_entitlement(max(0.0, years))


def _get_monthly_basic(employee: str) -> float:
    """Return latest monthly basic salary for the employee."""
    result = frappe.db.get_value(
        "Salary Structure Assignment",
        {"employee": employee, "docstatus": 1},
        "base",
        order_by="from_date desc",
    )
    return float(result or 0)
