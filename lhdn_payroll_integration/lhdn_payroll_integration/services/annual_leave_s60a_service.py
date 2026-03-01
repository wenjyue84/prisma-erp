"""
Annual Leave Carry-Forward and Cash-Out Service — Employment Act 1955 S.60A
US-206: Annual Leave Carry-Forward Cap and Cash-Out Enforcement at Year-End

EA S.60A rules:
  S.60A(3): Employer must pay for unused annual leave on termination at basic rate.
  S.60A(4): Leave should be utilised within 12 months of entitlement year.
  EA 2022 Amendment: Employer cannot unilaterally forfeit unused leave — employee
    must consent or enter a Mutual Forfeiture Agreement.

Cash-out formula: (Monthly Basic Salary / 26) x unused leave days
  (26 = EA default working days per month; adjustable by contract)
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, date_diff

# Statutory constants
WORKING_DAYS_PER_MONTH = 26  # EA default; may be overridden by employment contract
ANNUAL_LEAVE_TYPE = "Annual Leave (EA)"

VALID_DECISIONS = ("Carry Forward", "Cash Out", "Mutual Forfeiture Agreement")


# ── Public API ──────────────────────────────────────────────────────────────────


def compute_carry_forward_cap(annual_entitlement, custom_cap=None):
    """
    Return the maximum days an employee may carry forward.

    Default: 1× annual entitlement (EA-compliant; employer can restrict further
    by setting a custom_cap).  Returns an integer ≥ 0.

    Args:
        annual_entitlement (int|float): Days allocated for the leave year.
        custom_cap (int|float|None): Override cap; must not exceed annual_entitlement.

    Returns:
        int: Maximum carry-forward days allowed.
    """
    entitlement = int(annual_entitlement or 0)
    if entitlement < 0:
        entitlement = 0

    if custom_cap is not None:
        cap = int(custom_cap)
        if cap < 0:
            cap = 0
        # Cap cannot exceed entitlement
        return min(cap, entitlement)

    # Default: 1× entitlement (S.60A(4) — must be taken within 12 months)
    return entitlement


def calculate_cashout_amount(days, monthly_basic_salary, working_days_per_month=None):
    """
    Calculate cash-out amount for unused annual leave.

    Formula (EA S.60A): (Monthly Basic Salary / working_days_per_month) × days

    Args:
        days (int|float): Number of leave days to encash.
        monthly_basic_salary (float): Employee's current monthly basic salary.
        working_days_per_month (int|None): Defaults to WORKING_DAYS_PER_MONTH (26).

    Returns:
        float: Cash-out amount in MYR, rounded to 2 decimal places.
    """
    if days is None or days < 0:
        days = 0
    if monthly_basic_salary is None or monthly_basic_salary < 0:
        monthly_basic_salary = 0.0
    wdpm = working_days_per_month if working_days_per_month else WORKING_DAYS_PER_MONTH
    if wdpm <= 0:
        return 0.0
    daily_rate = float(monthly_basic_salary) / float(wdpm)
    return round(daily_rate * float(days), 2)


def generate_leave_expiry_notice(
    employee,
    leave_year_end,
    annual_allocation,
    days_taken,
    monthly_basic_salary,
    carry_forward_cap=None,
    working_days_per_month=None,
):
    """
    Generate a Leave Expiry Notice for one employee at year-end.

    Returns a dict with:
      - employee
      - leave_year_end
      - annual_entitlement   (int)
      - days_taken           (float)
      - days_unused          (float)
      - carry_forward_cap    (int)
      - days_expiring        (float)  — days that cannot be carried forward
      - days_to_carry_forward (float) — days eligible to carry forward
      - cash_out_amount      (float)
      - options              (list[str])

    Args:
        employee (str): Employee ID.
        leave_year_end (str): ISO date string of last day of leave year.
        annual_allocation (int|float): Allocated annual leave days.
        days_taken (int|float): Leave days already consumed in the year.
        monthly_basic_salary (float): Employee basic salary.
        carry_forward_cap (int|None): Override cap; default = 1× entitlement.
        working_days_per_month (int|None): Override; default 26.

    Returns:
        dict: Leave expiry notice data.
    """
    entitlement = int(annual_allocation or 0)
    taken = float(days_taken or 0)
    unused = max(0.0, float(entitlement) - taken)

    cf_cap = compute_carry_forward_cap(entitlement, carry_forward_cap)
    days_to_cf = min(unused, cf_cap)
    days_expiring = max(0.0, unused - days_to_cf)

    cash_amount = calculate_cashout_amount(
        days_expiring, monthly_basic_salary, working_days_per_month
    )

    options = list(VALID_DECISIONS)
    if days_expiring == 0:
        # Nothing to decide — all unused days are within carry-forward cap
        options = []

    return {
        "employee": employee,
        "leave_year_end": leave_year_end,
        "annual_entitlement": entitlement,
        "days_taken": taken,
        "days_unused": unused,
        "carry_forward_cap": cf_cap,
        "days_to_carry_forward": days_to_cf,
        "days_expiring": days_expiring,
        "cash_out_amount": cash_amount,
        "options": options,
    }


def record_leave_expiry_decision(
    employee,
    leave_year_end,
    decision,
    hr_manager,
    employee_acknowledged=False,
    days_decided=0,
    cash_out_amount=0.0,
):
    """
    Record an employee's leave expiry decision in the audit log.

    Validates:
      - decision is one of VALID_DECISIONS
      - EA 2022 Amendment: "Mutual Forfeiture Agreement" requires employee_acknowledged = True

    Args:
        employee (str): Employee ID.
        leave_year_end (str): ISO date of leave year end.
        decision (str): One of 'Carry Forward', 'Cash Out', 'Mutual Forfeiture Agreement'.
        hr_manager (str): HR Manager who recorded the decision.
        employee_acknowledged (bool): Employee has consented.
        days_decided (float): Number of days affected by this decision.
        cash_out_amount (float): Cash-out value (relevant for 'Cash Out' decisions).

    Returns:
        dict: Recorded log entry.

    Raises:
        frappe.ValidationError: On invalid decision or missing consent for forfeiture.
    """
    if decision not in VALID_DECISIONS:
        frappe.throw(
            _(
                "Invalid leave expiry decision '{0}'. Must be one of: {1}"
            ).format(decision, ", ".join(VALID_DECISIONS)),
            title=_("Invalid Decision"),
        )

    if decision == "Mutual Forfeiture Agreement" and not employee_acknowledged:
        frappe.throw(
            _(
                "EA 2022 Amendment requires documented employee consent for any leave forfeiture. "
                "Please obtain and record employee acknowledgement before selecting "
                "'Mutual Forfeiture Agreement'."
            ),
            title=_("Employee Consent Required"),
        )

    log_entry = {
        "employee": employee,
        "leave_year_end": leave_year_end,
        "decision": decision,
        "hr_manager": hr_manager,
        "employee_acknowledged": employee_acknowledged,
        "days_decided": float(days_decided or 0),
        "cash_out_amount": float(cash_out_amount or 0.0),
        "recorded_at": today(),
    }

    # Persist to Frappe DB via cache key pattern used by other services
    _upsert_leave_decision_log(log_entry)
    return log_entry


def check_leave_year_close_eligibility(employee, leave_year_end):
    """
    Check whether the leave year can be closed for this employee.

    An employee blocks leave year close if they have expiring days
    (days_expiring > 0) and no decision has been recorded yet.

    This function looks up the Decision Log doctype for a recorded decision.

    Args:
        employee (str): Employee ID.
        leave_year_end (str): ISO date of leave year end.

    Returns:
        dict: {'eligible': bool, 'reason': str}
    """
    existing = _get_leave_decision_log(employee, leave_year_end)
    if existing:
        return {
            "eligible": True,
            "reason": "Leave expiry decision recorded: {0}".format(
                existing.get("decision", "")
            ),
        }

    return {
        "eligible": False,
        "reason": (
            "Leave year close-off is blocked for employee {0}. "
            "A leave expiry decision (Carry Forward / Cash Out / Mutual Forfeiture Agreement) "
            "must be recorded before closing the leave year."
        ).format(employee),
    }


def get_leave_audit_log(employee, leave_year_end=None):
    """
    Return all recorded leave expiry decisions for an employee.

    Args:
        employee (str): Employee ID.
        leave_year_end (str|None): Filter by specific leave year end date.

    Returns:
        list[dict]: Log entries ordered by recorded_at descending.
    """
    filters = {"employee": employee}
    if leave_year_end:
        filters["leave_year_end"] = leave_year_end

    if frappe.db.exists("DocType", "Leave Expiry Decision Log"):
        logs = frappe.get_all(
            "Leave Expiry Decision Log",
            filters=filters,
            fields=[
                "employee",
                "leave_year_end",
                "decision",
                "hr_manager",
                "employee_acknowledged",
                "days_decided",
                "cash_out_amount",
                "recorded_at",
            ],
            order_by="recorded_at desc",
        )
        return [dict(log) for log in logs]

    # Fallback: use frappe cache store (unit-test friendly)
    return _get_all_cached_decisions(employee, leave_year_end)


# ── Internal helpers ────────────────────────────────────────────────────────────


def _cache_key(employee, leave_year_end):
    return "leave_expiry_decision::{0}::{1}".format(employee, leave_year_end)


def _upsert_leave_decision_log(entry):
    """Persist to DocType if exists, otherwise to frappe cache."""
    if frappe.db.exists("DocType", "Leave Expiry Decision Log"):
        existing = frappe.db.get_value(
            "Leave Expiry Decision Log",
            {
                "employee": entry["employee"],
                "leave_year_end": entry["leave_year_end"],
            },
            "name",
        )
        if existing:
            doc = frappe.get_doc("Leave Expiry Decision Log", existing)
            doc.update(entry)
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc({"doctype": "Leave Expiry Decision Log", **entry})
            doc.insert(ignore_permissions=True)
        frappe.db.commit()
    else:
        # Cache fallback for unit tests
        frappe.cache().set(
            _cache_key(entry["employee"], entry["leave_year_end"]),
            frappe.as_json(entry),
            expires_in_sec=3600,
        )


def _get_leave_decision_log(employee, leave_year_end):
    """Return a single decision log entry or None."""
    if frappe.db.exists("DocType", "Leave Expiry Decision Log"):
        name = frappe.db.get_value(
            "Leave Expiry Decision Log",
            {"employee": employee, "leave_year_end": leave_year_end},
            "name",
        )
        if name:
            doc = frappe.get_doc("Leave Expiry Decision Log", name)
            return doc.as_dict()
        return None
    # Cache fallback
    raw = frappe.cache().get(_cache_key(employee, leave_year_end))
    if raw:
        import json
        return json.loads(raw)
    return None


def _get_all_cached_decisions(employee, leave_year_end=None):
    """Retrieve cached decisions for unit-test environments."""
    # In real Frappe, the DocType handles persistence.
    # This is a lightweight stub for environments without the DocType.
    return []
