"""Annual Leave Carry-Forward Cap and Cash-Out Enforcement Service (US-206).

Employment Act 1955 S.60A governs annual leave entitlements for Malaysian employees:
- S.60A(3): Employer must pay for unused annual leave on termination at basic rate.
- S.60A(4): Leave should be utilized within 12 months of entitlement year.
- EA 2022 Amendment: Employers cannot unilaterally forfeit unused leave without
  documented employee consent.

At year-end, HR must:
1. Generate a Leave Expiry Notice showing expiring days, carry-forward option, and
   cash-out amount.
2. Record the employee's decision: Carry Forward | Cash Out | Mutual Forfeiture Agreement.
3. Block leave year close-off until all employees have recorded decisions.
4. Audit-log all decisions with HR manager and employee acknowledgement timestamps.

Cash-out formula (EA S.60A basic rate):
    Daily Rate = Monthly Basic Salary / 26
    Cash-out Amount = Daily Rate x Leave Days
"""

import frappe
from frappe.utils import now_datetime

# ── Constants ─────────────────────────────────────────────────────────────────

ANNUAL_LEAVE_TYPE_EA = "Annual Leave"          # Default EA leave type name
CASH_OUT_DIVISOR = 26                          # EA S.60A basic rate divisor
MAX_CARRY_FORWARD_MULTIPLIER = 1               # Default: 1x annual entitlement
VALID_DECISIONS = frozenset({
    "Carry Forward",
    "Cash Out",
    "Mutual Forfeiture Agreement",
})


# ── Pure Business Logic ───────────────────────────────────────────────────────

def get_max_carry_forward_days(entitlement_days, multiplier=MAX_CARRY_FORWARD_MULTIPLIER):
    """Return the maximum number of days an employee may carry forward.

    EA S.60A default: 1x annual entitlement (so all unused leave may be
    carried to the next year by agreement).  Employers may configure a
    stricter cap via the ``multiplier`` parameter (e.g. 0.5 for half
    entitlement).

    Args:
        entitlement_days (int | float): Total annual leave entitlement.
        multiplier (float): Carry-forward cap as a fraction of entitlement.
            Default 1.0 (100% — full entitlement may carry over).

    Returns:
        int: Maximum carry-forward days (floored).
    """
    if entitlement_days < 0:
        raise ValueError("entitlement_days cannot be negative")
    if multiplier < 0:
        raise ValueError("multiplier cannot be negative")
    return int(entitlement_days * multiplier)


def calculate_expiring_days(balance_days, max_carry_forward_days):
    """Return the number of leave days that will expire at year-end.

    If balance <= max_carry_forward, nothing expires.
    Otherwise, days beyond the cap will expire unless cashed out.

    Args:
        balance_days (int | float): Unused leave balance at year-end.
        max_carry_forward_days (int): Maximum days allowed to carry over.

    Returns:
        float: Days that would expire (>= 0).
    """
    if balance_days < 0:
        raise ValueError("balance_days cannot be negative")
    return max(0.0, balance_days - max_carry_forward_days)


def calculate_cash_out_amount(monthly_basic_salary, leave_days, divisor=CASH_OUT_DIVISOR):
    """Compute cash-out amount for unused annual leave at EA basic daily rate.

    Formula: (Monthly Basic Salary / 26) x leave_days

    Args:
        monthly_basic_salary (float): Employee's monthly basic salary (MYR).
        leave_days (float): Number of leave days to cash out.
        divisor (int): Working-days divisor (default 26 per EA).

    Returns:
        float: Cash-out amount in MYR (2 decimal places).
    """
    if monthly_basic_salary < 0:
        raise ValueError("monthly_basic_salary cannot be negative")
    if leave_days < 0:
        raise ValueError("leave_days cannot be negative")
    if divisor <= 0:
        raise ValueError("divisor must be positive")
    daily_rate = monthly_basic_salary / divisor
    return round(daily_rate * leave_days, 2)


def build_leave_expiry_notice(
    employee_id,
    leave_year,
    entitlement_days,
    balance_days,
    monthly_basic_salary,
    max_carry_forward_multiplier=MAX_CARRY_FORWARD_MULTIPLIER,
):
    """Build a Leave Expiry Notice dictionary for an employee.

    The notice summarises the leave position at year-end and shows the
    available options (carry forward, cash out) for informed decision-making.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): The leave year closing (e.g. 2025).
        entitlement_days (float): Total annual leave entitlement.
        balance_days (float): Unused days remaining at year-end.
        monthly_basic_salary (float): Employee's monthly basic salary.
        max_carry_forward_multiplier (float): Carry-forward cap multiplier.

    Returns:
        dict: Notice with keys: employee_id, leave_year, entitlement_days,
              balance_days, max_carry_forward_days, expiring_days,
              carry_forward_days, daily_rate, cash_out_amount, valid_decisions.
    """
    max_cf = get_max_carry_forward_days(entitlement_days, max_carry_forward_multiplier)
    expiring = calculate_expiring_days(balance_days, max_cf)
    carry_forward_days = min(balance_days, max_cf)
    cash_out_amount = calculate_cash_out_amount(monthly_basic_salary, balance_days)
    daily_rate = round(monthly_basic_salary / CASH_OUT_DIVISOR, 2)

    return {
        "employee_id": employee_id,
        "leave_year": leave_year,
        "entitlement_days": entitlement_days,
        "balance_days": balance_days,
        "max_carry_forward_days": max_cf,
        "expiring_days": expiring,
        "carry_forward_days": carry_forward_days,
        "daily_rate": daily_rate,
        "cash_out_amount": cash_out_amount,
        "valid_decisions": sorted(VALID_DECISIONS),
    }


def validate_decision(decision):
    """Raise ValueError if decision is not one of the three valid choices.

    Args:
        decision (str): Employee's leave expiry decision.

    Raises:
        ValueError: If decision is invalid.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision '{decision}'. "
            f"Must be one of: {', '.join(sorted(VALID_DECISIONS))}"
        )


def build_audit_entry(employee_id, leave_year, decision, hr_manager_id, acknowledged_at=None):
    """Build an audit log entry dict for a leave expiry decision.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): The leave year.
        decision (str): One of VALID_DECISIONS.
        hr_manager_id (str): HR manager who approved the decision.
        acknowledged_at (datetime | None): Employee acknowledgement timestamp.
            Defaults to now() if None.

    Returns:
        dict: Audit entry with approval and acknowledgement timestamps.
    """
    validate_decision(decision)
    ts = now_datetime()
    return {
        "employee_id": employee_id,
        "leave_year": leave_year,
        "decision": decision,
        "hr_manager_id": hr_manager_id,
        "approved_at": str(ts),
        "employee_acknowledged_at": str(acknowledged_at or ts),
    }


# ── Frappe DB Helpers ─────────────────────────────────────────────────────────

def get_annual_leave_entitlement(employee_id, leave_year, leave_type=ANNUAL_LEAVE_TYPE_EA):
    """Fetch total annual leave entitlement from Leave Allocation.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): Calendar year.
        leave_type (str): Leave type name.

    Returns:
        float: Total new leaves allocated; 0.0 if not found.
    """
    result = frappe.db.get_value(
        "Leave Allocation",
        {
            "employee": employee_id,
            "leave_type": leave_type,
            "docstatus": 1,
            "from_date": [">=", f"{leave_year}-01-01"],
            "to_date": ["<=", f"{leave_year}-12-31"],
        },
        "total_leaves_allocated",
    )
    return float(result or 0.0)


def get_leave_balance_at_year_end(employee_id, leave_year, leave_type=ANNUAL_LEAVE_TYPE_EA):
    """Calculate unused leave balance at the end of the leave year.

    Uses frappe.db to sum allocated minus taken leaves.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): Calendar year.
        leave_type (str): Leave type name.

    Returns:
        float: Unused leave days (>= 0).
    """
    alloc = frappe.db.get_value(
        "Leave Allocation",
        {
            "employee": employee_id,
            "leave_type": leave_type,
            "docstatus": 1,
            "from_date": [">=", f"{leave_year}-01-01"],
            "to_date": ["<=", f"{leave_year}-12-31"],
        },
        ["total_leaves_allocated", "total_leaves_encashed"],
        as_dict=True,
    ) or {}

    allocated = float(alloc.get("total_leaves_allocated") or 0)
    encashed = float(alloc.get("total_leaves_encashed") or 0)

    taken = frappe.db.sql(
        """
        SELECT COALESCE(SUM(total_leave_days), 0)
        FROM `tabLeave Application`
        WHERE employee = %(employee)s
          AND leave_type = %(leave_type)s
          AND docstatus = 1
          AND from_date >= %(from_date)s
          AND to_date <= %(to_date)s
        """,
        {
            "employee": employee_id,
            "leave_type": leave_type,
            "from_date": f"{leave_year}-01-01",
            "to_date": f"{leave_year}-12-31",
        },
    )[0][0]

    balance = allocated - encashed - float(taken or 0)
    return max(0.0, balance)


def get_employee_monthly_basic(employee_id):
    """Fetch the current monthly basic salary for an employee.

    Looks up the latest active Salary Structure Assignment.

    Args:
        employee_id (str): Frappe Employee docname.

    Returns:
        float: Monthly basic salary; 0.0 if not found.
    """
    result = frappe.db.get_value(
        "Salary Structure Assignment",
        {"employee": employee_id, "docstatus": 1},
        "base",
        order_by="from_date desc",
    )
    return float(result or 0.0)


def has_leave_expiry_decision(employee_id, leave_year):
    """Return True if a leave expiry decision has been recorded for this employee/year.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): Calendar year.

    Returns:
        bool: True if decision exists.
    """
    return bool(
        frappe.db.exists(
            "LHDN Leave Expiry Decision",
            {"employee": employee_id, "leave_year": leave_year},
        )
    )


def can_close_leave_year(employee_id, leave_year):
    """Return True if the leave year may be closed for this employee.

    Blocks closure if unused leave exists and no decision has been recorded.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): Calendar year.

    Returns:
        bool: True if leave year can be closed.
    """
    balance = get_leave_balance_at_year_end(employee_id, leave_year)
    if balance <= 0:
        return True  # No unused leave — no action needed
    return has_leave_expiry_decision(employee_id, leave_year)


def get_employees_without_decision(leave_year, company=None):
    """Return list of employee IDs who have unused leave but no recorded decision.

    Args:
        leave_year (int): Calendar year.
        company (str | None): Filter by company if provided.

    Returns:
        list[str]: Employee docnames needing a decision.
    """
    filters = {"docstatus": 1}
    if company:
        filters["company"] = company

    employees = frappe.get_all("Employee", filters=filters, pluck="name")
    pending = []
    for emp in employees:
        balance = get_leave_balance_at_year_end(emp, leave_year)
        if balance > 0 and not has_leave_expiry_decision(emp, leave_year):
            pending.append(emp)
    return pending


def record_leave_expiry_decision(
    employee_id,
    leave_year,
    decision,
    hr_manager_id,
    employee_acknowledged_at=None,
):
    """Create an LHDN Leave Expiry Decision record in Frappe.

    Args:
        employee_id (str): Frappe Employee docname.
        leave_year (int): Calendar year.
        decision (str): One of VALID_DECISIONS.
        hr_manager_id (str): User who approved the decision.
        employee_acknowledged_at (datetime | None): When employee acknowledged.

    Returns:
        str: Docname of the created LHDN Leave Expiry Decision.

    Raises:
        ValueError: If decision is invalid.
    """
    validate_decision(decision)
    ts = now_datetime()
    doc = frappe.get_doc(
        {
            "doctype": "LHDN Leave Expiry Decision",
            "employee": employee_id,
            "leave_year": leave_year,
            "decision": decision,
            "hr_manager": hr_manager_id,
            "approved_at": ts,
            "employee_acknowledged_at": employee_acknowledged_at or ts,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name
